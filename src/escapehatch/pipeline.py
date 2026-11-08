"""Audit pipeline: run leave (+enter) journeys, classify screenshots, score, store.

Emits normalized UI messages through ``on_update`` (the server forwards them as
SSE); every message is a plain dict so callers can serialize freely.
"""

import asyncio
import inspect
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse

import httpx
from hai_agents import AsyncClient
from openai import AsyncOpenAI

from escapehatch.agent import ConfirmFn, EventFn, fetch_screenshot, run_journey
from escapehatch.events import _parse_ts, step_from_policy_event
from escapehatch.keys import KeyPool
from escapehatch.legal import applicable_refs
from escapehatch.models import Audit, Finding, Journey
from escapehatch.patterns import classify_step, merge_findings, select_key_steps
from escapehatch.prompts import ENTER_COUNTERPART, Task
from escapehatch.report import render_report_html
from escapehatch.scoring import effort_steps, score
from escapehatch.store import RunStore

logger = logging.getLogger(__name__)

UpdateFn = Callable[[dict], Awaitable[None]]
# user-facing confirm: (action_description, request_id) -> "approved" | "denied"
ConfirmRequestFn = Callable[[str, str], Awaitable[str]]

_MODELS_BASE_URL = "https://api.hcompany.ai/v1"
_CLASSIFY_MODEL = "holo4-27b"


class _Emitter:
    """Sends on_update messages; never lets a UI callback break the pipeline."""

    def __init__(self, on_update: UpdateFn | None) -> None:
        self._fn = on_update

    async def send(self, msg: dict) -> None:
        if self._fn is None:
            return
        try:
            res = self._fn(msg)
            if inspect.isawaitable(res):
                await res
        except Exception:
            logger.exception("on_update callback failed for %s", msg.get("type"))


def _slug_host(url: str) -> str:
    host = urlparse(url).netloc or urlparse(url).path
    host = host.split(":")[0].removeprefix("www.")
    return host.replace(".", "-") or "site"


def _audit_id(site_url: str, task: Task, store: RunStore) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    base = f"{ts}-{_slug_host(site_url)}-{task.value}"
    audit_id, n = base, 2
    while (store.root / audit_id).exists():
        audit_id = f"{base}-{n}"
        n += 1
    return audit_id


def _make_event_tap(
    journey_name: str,
    emitter: _Emitter,
    on_shot: Callable[[str | None], None] | None = None,
) -> EventFn:
    """Live tap: tracks the last observation and emits step/status messages."""
    state: dict[str, Any] = {"last_obs": None, "steps": []}

    async def tap(event: dict) -> None:
        etype = event.get("type")
        data = event.get("data") or {}
        if etype == "AgentEvent":
            kind = data.get("kind")
            if kind == "observation_event":
                state["last_obs"] = data
                if on_shot is not None:
                    try:
                        on_shot((data.get("image") or {}).get("source"))
                    except Exception:
                        pass
            elif kind == "policy_event":
                ts = _parse_ts(event.get("timestamp"))
                new_steps = step_from_policy_event(data, state["last_obs"], len(state["steps"]), ts)
                for s in new_steps:
                    state["steps"].append(s)
                    await emitter.send({
                        "type": "step",
                        "journey": journey_name,
                        "step": s.model_dump(mode="json"),
                        "effort_so_far": effort_steps(state["steps"]).total,
                    })
            elif kind == "flow_event" and data.get("state"):
                await emitter.send({"type": "status", "journey": journey_name, "status": data["state"]})
        elif etype == "ActiveStateChangeEvent":
            state_name = (data or {}).get("state")
            if state_name:
                await emitter.send({"type": "status", "journey": journey_name, "status": state_name})
        elif etype == "AgentCompletionEvent":
            await emitter.send({"type": "status", "journey": journey_name, "status": "completed"})

    return tap


def _confirm_wrapper(
    journey_name: str,
    emitter: _Emitter,
    confirm: ConfirmRequestFn | None,
) -> ConfirmFn:
    """Emit confirm_request, delegate to the user confirm (auto-approve default)."""

    async def wrapped(action: str) -> str:
        req_id = uuid.uuid4().hex[:12]
        await emitter.send({
            "type": "confirm_request",
            "journey": journey_name,
            "id": req_id,
            "action": action,
        })
        if confirm is None:
            return "approved"
        try:
            res = await confirm(action, req_id)
        except Exception:
            logger.exception("confirm callback failed")
            return "denied"
        return "approved" if res == "approved" else "denied"

    return wrapped


async def _download_key_screenshots(
    http: httpx.AsyncClient,
    journey: Journey,
    store: RunStore,
) -> list[tuple[Any, Path]]:
    """Fetch + downscale screenshots for select_key_steps; returns (step, local_path)."""
    pairs: list[tuple[Any, Path]] = []
    for step in select_key_steps(journey):
        url = step.screenshot_url
        if not url:
            continue
        local = store.local_shot(url)
        if local is not None:
            pairs.append((step, local))
            continue
        try:
            data = await fetch_screenshot(http, url)
            path = store.save_screenshot(url, data)
            pairs.append((step, path))
        except Exception:
            logger.exception("screenshot download failed: %s", url)
    return pairs


async def _classify_pairs(
    openai_client: AsyncOpenAI,
    pairs: list[tuple[Any, Path]],
    task: Task,
) -> list[list[Finding]]:
    """Classify each screenshot concurrently; per-shot finding lists."""
    sem = asyncio.Semaphore(4)

    async def one(step: Any, path: Path) -> list[Finding]:
        async with sem:
            try:
                image_bytes = path.read_bytes()
                return await classify_step(
                    openai_client,
                    image_bytes,
                    task,
                    step.url,
                    step.element or step.action,
                    step.index,
                    step.screenshot_url,
                    model=_CLASSIFY_MODEL,
                )
            except Exception:
                logger.exception("classify_step failed for step %s", step.index)
                return []

    results = await asyncio.gather(*(one(s, p) for s, p in pairs))
    return results


def shot_resolver(store: RunStore, audit_dir: Path):
    """Map a platform screenshot URL to a path relative to the audit dir."""

    def resolve(url: str | None) -> str | None:
        if not url:
            return None
        local = store.local_shot(url)
        if local is None:
            return None
        return Path(os.path.relpath(local, audit_dir)).as_posix()

    return resolve


async def run_audit(
    *,
    site_url: str,
    task: Task,
    store: RunStore,
    agent: str = "h/web-surfer-pro",
    with_enter: bool = True,
    credentials: str | None = None,
    confirm: ConfirmRequestFn | None = None,
    on_update: UpdateFn | None = None,
    on_journey_started: Callable[[str, Any], None] | None = None,
    classify: bool = True,
    enter_url: str | None = None,
    audit_id: str | None = None,
    client: AsyncClient | None = None,
    openai_client: AsyncOpenAI | None = None,
    pool: KeyPool | None = None,
    max_steps: int = 35,
    max_time_s: int = 480,
) -> Audit:
    """Run leave (+enter counterpart) journeys, classify, score and persist an Audit."""
    emitter = _Emitter(on_update)
    audit_id = audit_id or _audit_id(site_url, task, store)

    legs: list[tuple[str, Task, str]] = [("leave", task, site_url)]
    counterpart = ENTER_COUNTERPART.get(task)
    if with_enter and counterpart is not None:
        legs.append(("enter", counterpart, enter_url or site_url))

    journeys: dict[str, Journey] = {}
    raw_events: dict[str, list[dict]] = {}

    # live screenshot downloads: bounded, deduped across both journeys, best-effort
    shot_sem = asyncio.Semaphore(4)
    shot_seen: set[str] = set()
    shot_tasks: set[asyncio.Task] = set()
    shot_http = httpx.AsyncClient(timeout=30)

    async def _live_shot(url: str) -> None:
        async with shot_sem:
            try:
                data = await fetch_screenshot(shot_http, url)
                store.save_screenshot(url, data)
            except Exception:
                logger.debug("live screenshot download failed: %s", url[:90])

    def _schedule_shot(url: str | None) -> None:
        if not url or url in shot_seen:
            return
        shot_seen.add(url)
        task = asyncio.create_task(_live_shot(url))
        shot_tasks.add(task)
        task.add_done_callback(shot_tasks.discard)

    async def _run_leg(side: str, leg_task: Task, url: str) -> None:
        tap = _make_event_tap(side, emitter, on_shot=_schedule_shot)
        side_name = side

        def _on_started(run: Any) -> None:
            if on_journey_started is not None:
                try:
                    on_journey_started(side_name, run)
                except Exception:
                    logger.exception("on_journey_started callback failed")

        async def _on_status(status: str, reason: str | None) -> None:
            await emitter.send({
                "type": "status", "journey": side_name,
                "status": status, "reason": reason,
            })

        kwargs = dict(
            site_url=url,
            task=leg_task,
            agent=agent,
            credentials=credentials,
            confirm=_confirm_wrapper(side, emitter, confirm),
            on_event=tap,
            on_started=_on_started,
            on_status=_on_status,
            max_steps=max_steps,
            max_time_s=max_time_s,
        )
        if pool is not None:
            async with pool.acquire() as leg_client:
                journey, events = await run_journey(leg_client, **kwargs)
        elif client is not None:
            journey, events = await run_journey(client, **kwargs)
        else:
            async with AsyncClient() as leg_client:
                journey, events = await run_journey(leg_client, **kwargs)
        journeys[side] = journey
        raw_events[side] = events
        await emitter.send({
            "type": "status",
            "journey": side,
            "status": journey.session_status,
            "session_id": journey.session_id,
            "outcome": journey.outcome.value,
        })

    try:
        await asyncio.gather(*(_run_leg(side, t, url) for side, t, url in legs))
    except Exception:
        logger.exception("run_audit journeys failed for %s", site_url)
        await emitter.send({"type": "error", "audit_id": audit_id, "message": "journey run failed"})

    if shot_tasks:
        try:
            await asyncio.wait_for(
                asyncio.gather(*tuple(shot_tasks), return_exceptions=True), timeout=90
            )
        except Exception:
            pass
    await shot_http.aclose()

    leave = journeys.get("leave")
    if leave is None:
        # run_journey never raises, but be defensive: fabricate a failed journey
        from escapehatch.models import Outcome

        leave = Journey(
            session_id="unknown", site_url=site_url, task=task, agent=agent,
            steps=[], answer=None, session_status="failed", outcome=Outcome.FAILED,
        )
        journeys["leave"] = leave
    enter = journeys.get("enter")

    for side, events in raw_events.items():
        try:
            store.save_events(audit_id, side, events)  # type: ignore[arg-type]
        except Exception:
            logger.exception("save_events failed for %s/%s", audit_id, side)

    findings: list[Finding] = []
    if classify:
        try:
            async with httpx.AsyncClient() as http:
                pairs = await _download_key_screenshots(http, leave, store)
            await emitter.send({
                "type": "phase",
                "phase": "classifying",
                "screenshots": len(pairs),
            })
            owns_openai = openai_client is None
            oai = openai_client or AsyncOpenAI(
                base_url=_MODELS_BASE_URL,
                api_key=os.environ.get("HAI_API_KEY", ""),
            )
            try:
                per_shot = await _classify_pairs(oai, pairs, task)
                findings = merge_findings(per_shot)
            finally:
                if owns_openai:
                    try:
                        await oai.close()
                    except Exception:
                        pass
        except Exception:
            logger.exception("classification stage failed for %s", site_url)
            await emitter.send({"type": "error", "audit_id": audit_id, "message": "classification failed"})

    for f in findings:
        await emitter.send({"type": "finding", "finding": f.model_dump(mode="json")})

    audit_score = score(leave, enter, findings)
    legal = applicable_refs(task, [f.pattern for f in findings])
    audit = Audit(
        id=audit_id,
        created_at=datetime.now(timezone.utc),
        site_url=site_url,
        task=task,
        leave=leave,
        enter=enter,
        findings=findings,
        score=audit_score,
        legal=legal,
    )

    try:
        store.save_audit(audit)
        audit_dir = store.root / audit_id
        html = render_report_html(audit, shot_resolver(store, audit_dir))
        (audit_dir / "report.html").write_text(html)
    except Exception:
        logger.exception("report save failed for %s", audit_id)
        await emitter.send({"type": "error", "audit_id": audit_id, "message": "report save failed"})

    await emitter.send({
        "type": "done",
        "audit_id": audit_id,
        "grade": audit_score.grade,
        "friction": audit_score.friction,
        "headline": audit_score.headline,
        "outcome": leave.outcome.value,
    })
    return audit
