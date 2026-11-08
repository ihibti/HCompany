"""Tests for agent.run_journey stall watchdog and retry behaviour."""

import asyncio
from types import SimpleNamespace

import pytest

from escapehatch.agent import run_journey
from escapehatch.models import Outcome
from escapehatch.prompts import Task


def _ev(kind: str, **data) -> dict:
    return {"type": "AgentEvent", "timestamp": "2026-01-01T00:00:00Z",
            "data": {"kind": kind, **data}}


def _done() -> dict:
    return {"type": "AgentCompletionEvent", "timestamp": "2026-01-01T00:00:01Z",
            "data": {}}


_ANSWER = {
    "completed": True, "impossible": False, "flow_found": True,
    "interactions_reported": 1, "steps": ["clicked"], "obstacles": [],
    "final_state": "done",
}


class _Handle:
    def __init__(self, session_id: str, script):
        self.id = session_id
        self._script = script
        self.cancelled = False

    async def stream(self, **kwargs):
        for item in self._script:
            if isinstance(item, BaseException):
                raise item
            if item == "HANG":
                await asyncio.sleep(3600)
            yield item

    async def cancel(self):
        self.cancelled = True

    async def pause(self): ...
    async def resume(self): ...
    async def send_message(self, text): ...


class _Sessions:
    def __init__(self, statuses: dict[str, str], answers: dict[str, dict], events: dict[str, list[dict]]):
        self._statuses = statuses
        self._answers = answers
        self._events = events

    async def get_session_status(self, session_id: str):
        return SimpleNamespace(status=self._statuses.get(session_id, "completed"))

    async def get_session(self, session_id: str):
        return SimpleNamespace(
            status=SimpleNamespace(status=self._statuses.get(session_id, "completed")),
            latest_answer=self._answers.get(session_id),
        )

    async def list_session_events(self, session_id: str, page: int = 1, size: int = 200):
        items = self._events.get(session_id, [])
        return SimpleNamespace(items=items, total=len(items))


class _Client:
    """Fake AsyncClient: each start_session pops the next scripted handle."""

    def __init__(self, handles: list[_Handle], sessions: _Sessions):
        self._handles = list(handles)
        self.sessions = sessions
        self.started: list[str] = []

    async def start_session(self, **kwargs):
        h = self._handles.pop(0)
        self.started.append(h.id)
        return h


def _terminal_events() -> list[dict]:
    return [
        _ev("observation_event", image={"source": "https://x/1.png"}),
        _ev("policy_event", action="click_web", args={"element": "Accept"}),
        _done(),
    ]


@pytest.mark.asyncio
async def test_stall_cancels_and_retries_once():
    good_events = _terminal_events()
    h1 = _Handle("sess-stalled", ["HANG"])  # first event never arrives... use hang directly
    h1._script = [_ev("observation_event", image={"source": "https://x/0.png"}), "HANG"]
    h2 = _Handle("sess-retry", good_events)
    sessions = _Sessions(
        statuses={"sess-stalled": "interrupted", "sess-retry": "completed"},
        answers={"sess-retry": _ANSWER},
        events={"sess-stalled": [], "sess-retry": good_events},
    )
    client = _Client([h1, h2], sessions)
    statuses: list[tuple[str, str | None]] = []

    async def on_status(status, reason):
        statuses.append((status, reason))

    journey, events = await run_journey(
        client, site_url="https://example.com", task=Task.REFUSE_COOKIES,
        on_status=on_status, stall_timeout_s=0.05,
    )

    assert client.started == ["sess-stalled", "sess-retry"]
    assert h1.cancelled and not h2.cancelled
    assert statuses == [("retrying", "agent stalled")]
    assert journey.session_id == "sess-retry"
    assert journey.retried_from == "sess-stalled"
    assert journey.outcome == Outcome.SUCCESS
    assert events == good_events


@pytest.mark.asyncio
async def test_no_retry_when_session_completes():
    events = _terminal_events()
    h = _Handle("sess-ok", events)
    sessions = _Sessions(
        statuses={"sess-ok": "completed"},
        answers={"sess-ok": _ANSWER},
        events={"sess-ok": events},
    )
    client = _Client([h], sessions)
    statuses: list = []

    journey, _ = await run_journey(
        client, site_url="https://example.com", task=Task.REFUSE_COOKIES,
        on_status=lambda s, r: statuses.append((s, r)), stall_timeout_s=0.05,
    )

    assert client.started == ["sess-ok"]
    assert statuses == []
    assert journey.retried_from is None
    assert journey.outcome == Outcome.SUCCESS


@pytest.mark.asyncio
async def test_max_retries_exhausted_keeps_last_attempt():
    h1 = _Handle("sess-a", ["HANG"])
    h2 = _Handle("sess-b", ["HANG"])
    sessions = _Sessions(
        statuses={"sess-a": "interrupted", "sess-b": "interrupted"},
        answers={},
        events={"sess-a": [], "sess-b": []},
    )
    client = _Client([h1, h2], sessions)
    statuses: list = []

    journey, _ = await run_journey(
        client, site_url="https://example.com", task=Task.REFUSE_COOKIES,
        on_status=lambda s, r: statuses.append((s, r)),
        stall_timeout_s=0.05, max_retries=1,
    )

    assert client.started == ["sess-a", "sess-b"]
    assert statuses == [("retrying", "agent stalled")]
    assert journey.session_id == "sess-b"
    assert journey.retried_from == "sess-a"
    assert journey.outcome == Outcome.FAILED


@pytest.mark.asyncio
async def test_stall_timeout_does_not_fire_between_events():
    """Events spaced under stall_timeout keep the session alive."""
    events = []

    async def slow_stream(**kwargs):
        for i in range(3):
            await asyncio.sleep(0.02)
            yield _ev("observation_event", image={"source": f"https://x/{i}.png"})
        for e in _terminal_events()[1:]:
            yield e

    h = _Handle("sess-slow", [])
    h.stream = slow_stream
    sessions = _Sessions(
        statuses={"sess-slow": "completed"},
        answers={"sess-slow": _ANSWER},
        events={"sess-slow": _terminal_events()},
    )
    client = _Client([h], sessions)

    journey, _ = await run_journey(
        client, site_url="https://example.com", task=Task.REFUSE_COOKIES,
        stall_timeout_s=0.2,
    )

    assert client.started == ["sess-slow"]
    assert journey.retried_from is None
    assert journey.outcome == Outcome.SUCCESS
