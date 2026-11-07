"""Dark-pattern classification: pick key screenshots, merge findings, call Holo.

select_key_steps and merge_findings are pure; classify_step talks to the
OpenAI-compatible Models API (https://api.hcompany.ai/v1).
"""

import base64
import json
from datetime import datetime, timezone

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from escapehatch.models import Finding, Journey, Step
from escapehatch.events import ACTION_KIND
from escapehatch.prompts import PATTERN_DEFINITIONS, Task, build_classifier_system_prompt, build_classifier_user_prompt

_INTERESTING_KINDS = {"interaction", "navigation"}


def select_key_steps(journey: Journey, max_shots: int = 6) -> list[Step]:
    """Steps worth screenshotting: the observation behind each real action,
    plus the journey's final screenshot. Dedupes identical screenshot urls and
    evenly samples down to max_shots, always keeping first and last."""
    candidates: list[Step] = []
    seen: set[str] = set()
    for step in journey.steps:
        if ACTION_KIND.get(step.action, "other") not in _INTERESTING_KINDS:
            continue
        url = step.screenshot_url
        if not url or url in seen:
            continue
        seen.add(url)
        candidates.append(step)

    if journey.final_screenshot_url and journey.final_screenshot_url not in seen:
        # represent the final observation as a synthetic step-like entry
        candidates.append(
            Step(
                index=len(journey.steps),
                action="final_observation",
                args={},
                url=journey.final_url,
                screenshot_url=journey.final_screenshot_url,
                timestamp=journey.steps[-1].timestamp if journey.steps else datetime.min.replace(tzinfo=timezone.utc),
            )
        )

    if len(candidates) <= max_shots:
        return candidates

    # keep first and last, sample the rest evenly
    keep_idx = {0, len(candidates) - 1}
    if max_shots > 2:
        for i in range(1, max_shots - 1):
            keep_idx.add(round(i * (len(candidates) - 1) / (max_shots - 1)))
    return [candidates[i] for i in sorted(keep_idx)]


def merge_findings(per_shot: list[list[Finding]]) -> list[Finding]:
    """Keep the strongest severity per pattern id (evidence from that finding),
    sorted by severity desc then pattern id."""
    best: dict[str, Finding] = {}
    for findings in per_shot:
        for f in findings:
            cur = best.get(f.pattern)
            if cur is None or f.severity > cur.severity:
                best[f.pattern] = f
    return sorted(best.values(), key=lambda f: (-f.severity, f.pattern))


class _RawFinding(BaseModel):
    pattern: str
    severity: int
    evidence: str
    explanation: str


class _ClassifierOutput(BaseModel):
    findings: list[_RawFinding] = Field(default_factory=list)


def _image_data_uri(image_bytes: bytes, media_type: str = "image/png") -> str:
    return f"data:{media_type};base64,{base64.b64encode(image_bytes).decode()}"


async def classify_step(
    client: AsyncOpenAI,
    image_bytes: bytes,
    task: Task,
    url: str | None,
    step_note: str | None,
    step_index: int,
    screenshot_url: str | None,
    model: str = "holo4-27b",
) -> list[Finding]:
    """Classify dark patterns in one screenshot. Invalid entries are dropped."""
    # strict-mode wire schema: pattern constrained to the taxonomy enum
    wire_schema = {
        "type": "object",
        "properties": {
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string", "enum": list(PATTERN_DEFINITIONS)},
                        "severity": {"type": "integer", "minimum": 1, "maximum": 3},
                        "evidence": {"type": "string"},
                        "explanation": {"type": "string"},
                    },
                    "required": ["pattern", "severity", "evidence", "explanation"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["findings"],
        "additionalProperties": False,
    }

    resp = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": build_classifier_system_prompt()},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": _image_data_uri(image_bytes)}},
                    {"type": "text", "text": build_classifier_user_prompt(task, url, step_note)},
                ],
            },
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "dark_pattern_findings", "schema": wire_schema, "strict": True},
        },
        temperature=0.0,
        max_tokens=2048,
    )
    content = resp.choices[0].message.content or "{}"
    try:
        parsed = _ClassifierOutput.model_validate(json.loads(content))
    except Exception:
        return []

    out: list[Finding] = []
    for f in parsed.findings:
        if f.pattern not in PATTERN_DEFINITIONS:
            continue
        if not 1 <= f.severity <= 3:
            continue
        out.append(
            Finding(
                pattern=f.pattern,
                severity=f.severity,
                evidence=f.evidence,
                explanation=f.explanation,
                step_index=step_index,
                screenshot_url=screenshot_url,
            )
        )
    return out
