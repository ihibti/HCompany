"""Pure conversion of raw session events into a Journey.

Event envelopes look like {"type": ..., "data": {...}, "timestamp": "..."}.
Agent activity lives in AgentEvent.data with a `kind` discriminator:
policy_event (decision + tool_reqs), observation_event (screenshot + page
metadata), tool_result, answer_event, error_event, message_event, flow_event.
"""

from datetime import datetime
from typing import Any, Literal

from escapehatch.models import AgentAnswer, Journey, Outcome, Step
from escapehatch.prompts import Task

# Tool-name -> effort bucket. Anything unmapped (custom tools, unknowns) is "other".
ACTION_KIND: dict[str, Literal["interaction", "navigation", "detour", "other"]] = {
    # interactions: clicks, typing, keys, drags, selects, hovers, find-in-page
    "click_web": "interaction",
    "write": "interaction",
    "fill_secret_at": "interaction",
    "select_option": "interaction",
    "press_keys_web": "interaction",
    "drag_and_drop_web": "interaction",
    "ctrl_f_web": "interaction",
    "move_mouse_web": "interaction",
    # navigations
    "go_to_web": "navigation",
    "go_back_web": "navigation",
    "refresh_web": "navigation",
    "switch_tab_web": "navigation",
    "close_tab_web": "navigation",
    # detours off the task
    "web_search": "detour",
    "web_fetch": "detour",
    # everything else costs the user nothing measurable
    "scroll_web": "other",
    "wait_web": "other",
    "reader_mode": "other",
    "find_in_page": "other",
    "switch_chunk": "other",
    "request_confirmation": "other",
    "answer": "other",
}

TERMINAL_FAILURES = {"failed", "timed_out", "interrupted"}


def _parse_ts(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _last_observation(events: list[dict]) -> dict[str, Any] | None:
    for e in reversed(events):
        if e.get("type") != "AgentEvent":
            continue
        data = e.get("data") or {}
        if data.get("kind") == "observation_event":
            return data
    return None


def journey_from_events(
    events: list[dict],
    *,
    session_id: str,
    site_url: str,
    task: Task,
    agent: str,
    session_status: str,
    answer: dict | None,
) -> Journey:
    steps: list[Step] = []
    last_obs: dict[str, Any] | None = None
    cost_usd: float | None = None
    timestamps: list[datetime] = []

    for e in events:
        ts = _parse_ts(e.get("timestamp"))
        timestamps.append(ts)
        etype = e.get("type")
        data = e.get("data") or {}

        if etype == "MetricsUpdateEvent":
            metrics = data.get("metrics") or {}
            if metrics.get("total_cost") is not None:
                cost_usd = metrics["total_cost"]
            continue

        if etype != "AgentEvent":
            continue

        kind = data.get("kind")
        if kind == "observation_event":
            last_obs = data
        elif kind == "policy_event":
            meta = (last_obs or {}).get("metadata") or {}
            image = (last_obs or {}).get("image") or {}
            for tr in data.get("tool_reqs") or []:
                tool_name = tr.get("tool_name")
                if tool_name == "answer":
                    continue
                args = tr.get("args") or {}
                steps.append(
                    Step(
                        index=len(steps),
                        action=tool_name or "unknown",
                        args=args if isinstance(args, dict) else {"value": args},
                        element=args.get("element") if isinstance(args, dict) else None,
                        reasoning=data.get("reasoning_content"),
                        message=data.get("content") or None,
                        url=meta.get("url"),
                        title=meta.get("title"),
                        screenshot_url=image.get("source"),
                        timestamp=ts,
                    )
                )

    parsed_answer: AgentAnswer | None = None
    if answer is not None:
        try:
            parsed_answer = AgentAnswer.model_validate(answer)
        except Exception:
            parsed_answer = None

    if session_status in TERMINAL_FAILURES or parsed_answer is None:
        outcome = Outcome.FAILED
    elif parsed_answer.completed:
        outcome = Outcome.SUCCESS
    elif parsed_answer.impossible:
        outcome = Outcome.IMPOSSIBLE
    elif not parsed_answer.flow_found:
        outcome = Outcome.NOT_APPLICABLE
    else:
        outcome = Outcome.FAILED

    duration_s = (timestamps[-1] - timestamps[0]).total_seconds() if len(timestamps) >= 2 else None

    final_obs = _last_observation(events)
    final_meta = (final_obs or {}).get("metadata") or {}
    final_image = (final_obs or {}).get("image") or {}

    return Journey(
        session_id=session_id,
        site_url=site_url,
        task=task,
        agent=agent,
        steps=steps,
        answer=parsed_answer,
        session_status=session_status,
        outcome=outcome,
        cost_usd=cost_usd,
        duration_s=duration_s,
        final_url=final_meta.get("url"),
        final_screenshot_url=final_image.get("source"),
    )
