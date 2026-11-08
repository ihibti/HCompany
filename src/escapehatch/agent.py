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
StatusFn = Callable[[str, str | None], Awaitable[None]]

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


_STREAM_END = object()


async def _stream_next(stream_it: Any, timeout_s: float) -> tuple[Any, bool]:
    """Pull one item from an async iterator.

    Returns (event, False), (_STREAM_END, False) on exhaustion, or
    (None, True) when nothing arrives within ``timeout_s``.
    """
    task = asyncio.ensure_future(stream_it.__anext__())
    done, _pending = await asyncio.wait({task}, timeout=timeout_s)
    if not done:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
        return None, True
    try:
        return task.result(), False
    except StopAsyncIteration:
        return _STREAM_END, False


@dataclass
class _Attempt:
    run: JourneyRun
    events: list[dict]
    session_status: str
    answer: dict | None
    stalled: bool


async def _run_attempt(
    client: AsyncClient,
    *,
    site_url: str,
    task: Task,
    agent: str,
    credentials: str | None,
    confirm: ConfirmFn | None,
    on_event: EventFn | None,
    on_started: Callable[[JourneyRun], None] | None,
    max_steps: int,
    max_time_s: int,
    stall_timeout_s: float,
) -> _Attempt:
    """One session attempt; returns raw events plus stall/terminal metadata."""
    prompt = build_task_prompt(task, site_url, credentials)
    tools = [_confirmation_tool(confirm)] if task in _CONFIRM_TASKS else None
    run = JourneyRun()
    streamed: list[dict] = []
    session_status = "failed"
    answer: dict | None = None
    stalled = False

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

        stream_it = handle.stream(
            until="terminal",
            wait_for_seconds=20,
            timeout_seconds=max_time_s + _STREAM_SLACK_S,
        ).__aiter__()
        while True:
            try:
                ev, is_stall = await _stream_next(stream_it, stall_timeout_s)
            except TimeoutError:
                logger.warning("stream timed out for session %s; cancelling", run.session_id)
                await _safe_cancel(run)
                break
            except Exception:
                logger.exception("stream failed for session %s", run.session_id)
                await _safe_cancel(run)
                break
            if is_stall:
                stalled = True
                logger.warning(
                    "no events for %.0fs; session %s treated as stalled",
                    stall_timeout_s, run.session_id,
                )
                await _safe_cancel(run)
                break
            if ev is _STREAM_END:
                break
            d = _to_dict(ev)
            streamed.append(d)
            if on_event is not None:
                await on_event(d)

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
        logger.exception("run attempt failed for %s task=%s", site_url, task)
        events = streamed
        session_status = "failed"

    return _Attempt(run, events, session_status, answer, stalled)


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
    on_status: StatusFn | None = None,
    max_steps: int = 35,
    max_time_s: int = 480,
    stall_timeout_s: float = 75,
    max_retries: int = 1,
) -> tuple[Journey, list[dict]]:
    """Run one agent journey; returns (Journey, raw events). Never raises.

    A session that goes silent for ``stall_timeout_s`` is cancelled and the
    journey restarted once (``max_retries``) in a fresh session.
    """
    t0 = time.monotonic()
    retried_from: str | None = None
    attempt_no = 0
    attempt: _Attempt | None = None

    while True:
        attempt = await _run_attempt(
            client,
            site_url=site_url,
            task=task,
            agent=agent,
            credentials=credentials,
            confirm=confirm,
            on_event=on_event,
            on_started=on_started,
            max_steps=max_steps,
            max_time_s=max_time_s,
            stall_timeout_s=stall_timeout_s,
        )
        if not attempt.stalled or attempt_no >= max_retries:
            break
        attempt_no += 1
        retried_from = attempt.run.session_id
        if on_status is not None:
            try:
                await on_status("retrying", "agent stalled")
            except Exception:
                logger.exception("on_status callback failed")

    assert attempt is not None
    run = attempt.run
    journey = journey_from_events(
        attempt.events,
        session_id=run.session_id or "unknown",
        site_url=site_url,
        task=task,
        agent=agent,
        session_status=attempt.session_status,
        answer=attempt.answer,
        duration_s=round(time.monotonic() - t0, 1),
    )
    if retried_from:
        journey.retried_from = retried_from
    logger.info(
        "journey %s task=%s status=%s outcome=%s steps=%d cost=%s dur=%.0fs retried_from=%s",
        run.session_id, task.value, attempt.session_status, journey.outcome.value,
        len(journey.steps), journey.cost_usd, journey.duration_s or 0, retried_from,
    )
    return journey, attempt.events


async def fetch_screenshot(http: httpx.AsyncClient, url: str) -> bytes:
    """Download a platform screenshot URL with the API key as bearer token."""
    api_key = os.environ.get("HAI_API_KEY")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    resp = await http.get(url, headers=headers, follow_redirects=True, timeout=60)
    resp.raise_for_status()
    return resp.content
