"""Agent orchestration: run one journey on the H Agents API.

Wraps AsyncClient.start_session + handle.stream(until="terminal") so custom
tools execute in-process and every raw event is forwarded live. The complete
event list is re-fetched at the end and converted by events.journey_from_events.
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import httpx
from hai_agents import AsyncClient

from escapehatch.events import journey_from_events
from escapehatch.models import AgentAnswer, Journey
from escapehatch.prompts import Task, build_task_prompt

logger = logging.getLogger(__name__)

ConfirmFn = Callable[[str], Awaitable[str]]
EventFn = Callable[[dict], Awaitable[None]]

# request_confirmation is only meaningful where an irreversible action exists.
_CONFIRM_TASKS = {Task.CANCEL_SUBSCRIPTION, Task.UNSUBSCRIBE}

_STREAM_SLACK_S = 90
_TERMINAL_POLL_S = 30
_EVENTS_PAGE_SIZE = 200


@dataclass
class JourneyRun:
    """Live handle to a running session, exposed for user control."""

    session_id: str | None = None
    handle: Any | None = None

    async def pause(self) -> None:
        if self.handle is not None:
            await self.handle.pause()

    async def resume(self) -> None:
        if self.handle is not None:
            await self.handle.resume()

    async def cancel(self) -> None:
        if self.handle is not None:
            await self.handle.cancel()

    async def send_message(self, text: str) -> None:
        if self.handle is not None:
            await self.handle.send_message(text)


def _confirmation_tool(confirm: ConfirmFn | None):
    """request_confirmation(action) -> 'approved' | 'denied'; auto-approves by default."""

    async def request_confirmation(action: str) -> str:
        """Ask the user to approve an irreversible action before performing it. Returns 'approved' or 'denied'."""
        if confirm is None:
            return "approved"
        try:
            result = await confirm(action)
        except Exception:
            logger.exception("confirm callback failed")
            return "denied"
        return "approved" if result == "approved" else "denied"

    return request_confirmation


def _to_dict(event: Any) -> dict:
    if hasattr(event, "model_dump"):
        return event.model_dump(mode="json", exclude_none=False)
    if hasattr(event, "dict"):
        return event.dict()
    return dict(event)


async def _list_all_events(client: AsyncClient, session_id: str) -> list[dict]:
    events: list[dict] = []
    page = 1
    while True:
        p = await client.sessions.list_session_events(session_id, page=page, size=_EVENTS_PAGE_SIZE)
        items = p.items or []
        events.extend(_to_dict(e) for e in items)
        if not items or page * _EVENTS_PAGE_SIZE >= (p.total or 0):
            break
        page += 1
    return events


async def _wait_terminal(client: AsyncClient, session_id: str, cap_s: float) -> str:
    """Poll status until terminal; returns last seen status string."""
    deadline = time.monotonic() + cap_s
    status = "unknown"
    while time.monotonic() < deadline:
        try:
            st = await client.sessions.get_session_status(session_id)
            status = st.status
        except Exception:
            logger.exception("status poll failed for %s", session_id)
            break
        if status in {"completed", "failed", "timed_out", "interrupted"}:
            return status
        await asyncio.sleep(2)
    return status


async def _safe_cancel(run: JourneyRun) -> None:
    try:
        if run.handle is not None:
            await run.handle.cancel()
    except Exception:
        logger.exception("cancel failed for session %s", run.session_id)


async def run_journey(
    client: AsyncClient,
    *,
    site_url: str,
    task: Task,
    agent: str = "h/web-surfer-pro",
    credentials: str | None = None,
    confirm: ConfirmFn | None = None,
    on_event: EventFn | None = None,
    on_started: Callable[[JourneyRun], None] | None = None,
    max_steps: int = 35,
    max_time_s: int = 480,
) -> tuple[Journey, list[dict]]:
    """Run one agent journey; returns (Journey, raw events). Never raises."""
    prompt = build_task_prompt(task, site_url, credentials)
    tools = [_confirmation_tool(confirm)] if task in _CONFIRM_TASKS else None
    run = JourneyRun()
    streamed: list[dict] = []
    session_status = "failed"
    answer: dict | None = None
    t0 = time.monotonic()

    try:
        handle = await client.start_session(
            agent=agent,
            messages=prompt,
            answer_schema=AgentAnswer,
            tools=tools,
            max_steps=max_steps,
            max_time_s=max_time_s,
        )
        run.handle = handle
        run.session_id = handle.id
        if on_started is not None:
            on_started(run)

        try:
            async for event in handle.stream(
                until="terminal",
                wait_for_seconds=20,
                timeout_seconds=max_time_s + _STREAM_SLACK_S,
            ):
                d = _to_dict(event)
                streamed.append(d)
                if on_event is not None:
                    await on_event(d)
        except TimeoutError:
            logger.warning("stream timed out for session %s; cancelling", run.session_id)
            await _safe_cancel(run)
        except Exception:
            logger.exception("stream failed for session %s", run.session_id)
            await _safe_cancel(run)

        session_status = await _wait_terminal(client, run.session_id, _TERMINAL_POLL_S)

        try:
            session = await client.sessions.get_session(run.session_id)
            if session.status is not None and session.status.status:
                session_status = session.status.status
            latest = session.latest_answer
            if isinstance(latest, dict):
                answer = latest
            elif hasattr(latest, "model_dump"):
                answer = latest.model_dump(mode="json")
        except Exception:
            logger.exception("session fetch failed for %s", run.session_id)

        try:
            events = await _list_all_events(client, run.session_id)
        except Exception:
            logger.exception("event listing failed for %s", run.session_id)
            events = streamed
    except Exception:
        logger.exception("run_journey failed for %s task=%s", site_url, task)
        events = streamed
        session_status = "failed"

    journey = journey_from_events(
        events,
        session_id=run.session_id or "unknown",
        site_url=site_url,
        task=task,
        agent=agent,
        session_status=session_status,
        answer=answer,
        duration_s=round(time.monotonic() - t0, 1),
    )
    logger.info(
        "journey %s task=%s status=%s outcome=%s steps=%d cost=%s dur=%.0fs",
        run.session_id, task.value, session_status, journey.outcome.value,
        len(journey.steps), journey.cost_usd, journey.duration_s or 0,
    )
    return journey, events


async def fetch_screenshot(http: httpx.AsyncClient, url: str) -> bytes:
    """Download a platform screenshot URL with the API key as bearer token."""
    api_key = os.environ.get("HAI_API_KEY")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    resp = await http.get(url, headers=headers, follow_redirects=True, timeout=60)
    resp.raise_for_status()
    return resp.content
