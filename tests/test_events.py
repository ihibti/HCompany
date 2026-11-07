import json
from pathlib import Path

import pytest

from escapehatch.events import journey_from_events
from escapehatch.models import Outcome
from escapehatch.prompts import Task

FIXTURES = Path(__file__).parent / "fixtures"

ANSWER = {
    "completed": True,
    "impossible": False,
    "flow_found": True,
    "interactions_reported": 1,
    "steps": ["clicked refuse"],
    "obstacles": [],
    "final_state": "cookies refused",
}


def _load(name: str) -> list[dict]:
    return json.loads((FIXTURES / name).read_text())


def _journey(events, **kw):
    params = dict(
        session_id="sid",
        site_url="https://example.com",
        task=Task.REFUSE_COOKIES,
        agent="h/web-surfer-flash",
        session_status="completed",
        answer=ANSWER,
    )
    params.update(kw)
    return journey_from_events(events, **params)


def test_marmiton_fixture_steps_and_cost():
    j = _journey(_load("events_marmiton.json"))
    # policy tool_reqs: go_to_web, click_web, answer -> answer excluded
    assert [s.action for s in j.steps] == ["go_to_web", "click_web"]
    assert j.steps[0].args == {"url": "https://www.marmiton.org"}
    assert j.steps[1].args["element"] is not None
    assert j.steps[1].element == j.steps[1].args["element"]
    # steps bind to the observation seen before the decision
    assert j.steps[0].url == "https://www.bing.com/"
    assert j.steps[1].url == "https://www.marmiton.org/"
    assert j.steps[1].screenshot_url is not None
    assert j.steps[1].reasoning
    assert j.cost_usd == pytest.approx(0.0051979)
    assert j.duration_s is not None and j.duration_s > 0
    assert j.final_url == "https://www.marmiton.org/"
    assert j.final_screenshot_url is not None
    assert j.outcome == Outcome.SUCCESS
    assert j.answer is not None and j.answer.completed is True


def test_leboncoin_fixture_includes_scroll_step():
    j = _journey(_load("events_leboncoin.json"))
    assert [s.action for s in j.steps] == [
        "go_to_web",
        "scroll_web",
        "click_web",
        "click_web",
    ]
    assert j.cost_usd == pytest.approx(0.01042492)
    assert j.steps[2].url == "https://www.leboncoin.fr/"
    assert j.outcome == Outcome.SUCCESS


def _synthetic_events(tool_reqs, *, answer_tool=True, status_events=True):
    return [
        {"type": "RequestStartEvent", "timestamp": "2026-01-01T00:00:00Z", "data": {}},
        {
            "type": "AgentEvent",
            "timestamp": "2026-01-01T00:00:01Z",
            "data": {
                "kind": "observation_event",
                "image": {"source": "https://img/1.png", "type": "url", "media_type": "image/png"},
                "metadata": {"url": "https://site.example/", "title": "Home"},
            },
        },
        {
            "type": "AgentEvent",
            "timestamp": "2026-01-01T00:00:02Z",
            "data": {
                "kind": "policy_event",
                "reasoning_content": "thinking",
                "content": "msg",
                "tool_reqs": tool_reqs,
                "validation_errors": [],
            },
        },
        {
            "type": "MetricsUpdateEvent",
            "timestamp": "2026-01-01T00:00:03Z",
            "data": {"metrics": {"total_cost": 0.5}},
        },
        {
            "type": "AgentEvent",
            "timestamp": "2026-01-01T00:00:04Z",
            "data": {
                "kind": "observation_event",
                "image": {"source": "https://img/2.png", "type": "url", "media_type": "image/png"},
                "metadata": {"url": "https://site.example/done", "title": "Done"},
            },
        },
    ]


def test_request_confirmation_becomes_step():
    events = _synthetic_events(
        [
            {"tool_name": "click_web", "args": {"x": 1, "y": 2, "element": "Cancel"}, "id": "t1"},
            {"tool_name": "request_confirmation", "args": {"action": "click Cancel"}, "id": "t2"},
        ]
    )
    j = _journey(events)
    assert [s.action for s in j.steps] == ["click_web", "request_confirmation"]
    assert j.steps[1].args == {"action": "click Cancel"}
    assert j.steps[1].screenshot_url == "https://img/1.png"
    assert j.final_url == "https://site.example/done"


def test_answer_tool_req_excluded():
    events = _synthetic_events(
        [
            {"tool_name": "click_web", "args": {"x": 1, "y": 2}, "id": "t1"},
            {"tool_name": "answer", "args": {"content": "done", "outcome": "success"}, "id": "t2"},
        ]
    )
    j = _journey(events)
    assert [s.action for s in j.steps] == ["click_web"]


def test_no_answer_is_failed():
    j = _journey(_synthetic_events([{"tool_name": "click_web", "args": {}, "id": "t"}]), answer=None)
    assert j.outcome == Outcome.FAILED
    assert j.answer is None


@pytest.mark.parametrize(
    "status", ["failed", "timed_out", "interrupted"]
)
def test_terminal_failure_status(status):
    j = _journey(_synthetic_events([]), session_status=status)
    assert j.outcome == Outcome.FAILED


def test_impossible_outcome():
    answer = dict(ANSWER, completed=False, impossible=True)
    j = _journey(_synthetic_events([]), answer=answer)
    assert j.outcome == Outcome.IMPOSSIBLE


def test_not_applicable_outcome():
    answer = dict(ANSWER, completed=False, impossible=False, flow_found=False)
    j = _journey(_synthetic_events([]), answer=answer)
    assert j.outcome == Outcome.NOT_APPLICABLE


def test_completed_false_flow_found_is_failed():
    answer = dict(ANSWER, completed=False, impossible=False, flow_found=True)
    j = _journey(_synthetic_events([]), answer=answer)
    assert j.outcome == Outcome.FAILED


def test_non_dict_args_wrapped():
    events = _synthetic_events([{"tool_name": "write", "args": "raw-string", "id": "t"}])
    j = _journey(events)
    assert j.steps[0].args == {"value": "raw-string"}
    assert j.steps[0].element is None


def test_step_from_policy_event_helper():
    from datetime import datetime, timezone

    from escapehatch.events import step_from_policy_event

    obs = {
        "kind": "observation_event",
        "image": {"source": "https://img/x.png"},
        "metadata": {"url": "https://site.test/", "title": "Home"},
    }
    policy = {
        "kind": "policy_event",
        "reasoning_content": "why",
        "content": "msg",
        "tool_reqs": [
            {"tool_name": "click_web", "args": {"x": 1, "y": 2, "element": "OK"}, "id": "a"},
            {"tool_name": "answer", "args": {"content": "done"}, "id": "b"},
            {"tool_name": "scroll_web", "args": {"direction": "down"}, "id": "c"},
        ],
    }
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    steps = step_from_policy_event(policy, obs, index=5, ts=ts)
    assert [s.action for s in steps] == ["click_web", "scroll_web"]
    assert [s.index for s in steps] == [5, 6]
    assert all(s.url == "https://site.test/" for s in steps)
    assert all(s.screenshot_url == "https://img/x.png" for s in steps)
    assert steps[0].element == "OK"
    assert steps[0].reasoning == "why"

    # no observation yet -> null url/title/screenshot
    steps_none = step_from_policy_event(policy, None, 0, ts)
    assert steps_none[0].url is None
    assert steps_none[0].screenshot_url is None


def test_duration_override_wins_over_event_span():
    events = _synthetic_events([{"tool_name": "click_web", "args": {}, "id": "x"}])
    j = _journey(events)
    assert j.duration_s is not None and j.duration_s < 100  # event span
    j2 = _journey(events, duration_s=42.5)
    assert j2.duration_s == 42.5
