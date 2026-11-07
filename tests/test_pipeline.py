import io
import json
from datetime import datetime, timezone

import pytest
from PIL import Image

import escapehatch.pipeline as pipeline
from escapehatch.models import Finding, Journey, Outcome
from escapehatch.prompts import Task
from escapehatch.store import RunStore

from conftest import make_journey, make_step


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (100, 80), (10, 20, 30)).save(buf, "PNG")
    return buf.getvalue()


def _events_for(journey: Journey) -> list[dict]:
    events = [
        {"type": "RequestStartEvent", "timestamp": "2026-01-01T00:00:00Z", "data": {}},
        {
            "type": "AgentEvent",
            "timestamp": "2026-01-01T00:00:01Z",
            "data": {
                "kind": "observation_event",
                "image": {"source": "https://shots/final.png"},
                "metadata": {"url": journey.final_url or "https://site.test/", "title": "T"},
            },
        },
    ]
    for s in journey.steps:
        events.append(
            {
                "type": "AgentEvent",
                "timestamp": s.timestamp.isoformat(),
                "data": {
                    "kind": "policy_event",
                    "reasoning_content": s.reasoning,
                    "content": s.message,
                    "tool_reqs": [{"tool_name": s.action, "args": s.args, "id": "t"}],
                },
            }
        )
        events.append(
            {
                "type": "MetricsUpdateEvent",
                "timestamp": s.timestamp.isoformat(),
                "data": {"metrics": {"total_cost": journey.cost_usd or 0.01}},
            }
        )
    return events


def _make_fake_run_journey():
    calls = []

    async def fake_run_journey(client, *, site_url, task, **kwargs):
        calls.append({"site_url": site_url, "task": task})
        on_event = kwargs.get("on_event")
        if task == Task.CANCEL_SUBSCRIPTION:
            steps = [
                make_step("go_to_web", index=0, args={"url": site_url}, screenshot_url="https://shots/a.png"),
                make_step("click_web", index=1, args={"x": 1, "y": 2, "element": "Cancel"},
                          screenshot_url="https://shots/b.png"),
                make_step("click_web", index=2, args={"x": 3, "y": 4, "element": "Confirm"},
                          screenshot_url="https://shots/c.png"),
            ]
            journey = make_journey(
                steps=steps, final_url="https://site.test/cancelled",
                final_screenshot_url="https://shots/final.png",
            )
        else:
            journey = make_journey(
                ["click_web"], task=task, final_url="https://site.test/welcome",
            )
        events = _events_for(journey)
        if on_event:
            for e in events:
                await on_event(e)
        # simulate the agent calling request_confirmation on the leave leg
        confirm_fn = kwargs.get("confirm")
        if confirm_fn is not None and task == Task.CANCEL_SUBSCRIPTION:
            result = await confirm_fn("click 'Confirm cancellation'")
            calls[-1]["confirm_result"] = result
        return journey, events

    fake_run_journey.calls = calls
    return fake_run_journey


class _FakeAgentClient:
    async def aclose(self):
        pass


@pytest.mark.asyncio
async def test_run_audit_end_to_end_with_fakes(tmp_path, monkeypatch):
    fake_rj = _make_fake_run_journey()
    monkeypatch.setattr(pipeline, "run_journey", fake_rj)

    async def fake_fetch(http, url):
        return _png()

    monkeypatch.setattr(pipeline, "fetch_screenshot", fake_fetch)

    canned = json.dumps({
        "findings": [
            {"pattern": "asymmetric_choice", "severity": 2,
             "evidence": "small grey link", "explanation": "weak option"}
        ]
    })

    async def fake_classify(client, image_bytes, task, url, step_note, step_index, screenshot_url, model="m"):
        return [
            Finding(pattern="asymmetric_choice", severity=2,
                    evidence="small grey link", explanation="weak option",
                    step_index=step_index, screenshot_url=screenshot_url)
        ]

    monkeypatch.setattr(pipeline, "classify_step", fake_classify)

    store = RunStore(tmp_path / "runs")
    updates = []

    async def on_update(msg):
        updates.append(msg)

    audit = await pipeline.run_audit(
        site_url="https://site.test/manage",
        task=Task.CANCEL_SUBSCRIPTION,
        store=store,
        client=_FakeAgentClient(),
        openai_client=object(),
        on_update=on_update,
    )

    # both legs ran
    assert {c["task"] for c in fake_rj.calls} == {Task.CANCEL_SUBSCRIPTION, Task.SUBSCRIBE}
    assert audit.enter is not None

    # files persisted
    audit_dir = store.root / audit.id
    assert (audit_dir / "audit.json").exists()
    assert (audit_dir / "events_leave.json").exists()
    assert (audit_dir / "events_enter.json").exists()
    assert (audit_dir / "report.html").exists()
    assert len(list((store.root / "shots").glob("*.jpg"))) >= 1

    # audit content
    assert audit.leave.outcome == Outcome.SUCCESS
    assert audit.score.grade in {"A", "B", "C", "D", "F"}
    assert audit.findings and audit.findings[0].pattern == "asymmetric_choice"
    assert audit.legal  # legal refs mapped

    # on_update sequence: steps -> status -> finding -> done
    types = [m["type"] for m in updates]
    assert "step" in types
    assert "status" in types
    assert "finding" in types
    assert types[-1] == "done"
    step_msgs = [m for m in updates if m["type"] == "step"]
    assert step_msgs[0]["journey"] == "leave"
    assert "effort_so_far" in step_msgs[0]
    done = updates[-1]
    assert done["audit_id"] == audit.id
    assert done["grade"] == audit.score.grade


@pytest.mark.asyncio
async def test_run_audit_no_enter_and_classify_off(tmp_path, monkeypatch):
    fake_rj = _make_fake_run_journey()
    monkeypatch.setattr(pipeline, "run_journey", fake_rj)

    store = RunStore(tmp_path / "runs")
    audit = await pipeline.run_audit(
        site_url="https://site.test/x",
        task=Task.REFUSE_COOKIES,
        store=store,
        with_enter=False,
        classify=False,
        client=_FakeAgentClient(),
        openai_client=object(),
    )
    assert len(fake_rj.calls) == 1
    assert audit.enter is None
    assert audit.findings == []


@pytest.mark.asyncio
async def test_run_audit_confirm_request_emitted(tmp_path, monkeypatch):
    fake_rj = _make_fake_run_journey()
    monkeypatch.setattr(pipeline, "run_journey", fake_rj)

    store = RunStore(tmp_path / "runs")
    updates = []

    async def on_update(msg):
        updates.append(msg)

    confirm_calls = []

    async def user_confirm(action: str) -> str:
        confirm_calls.append(action)
        return "approved"

    await pipeline.run_audit(
        site_url="https://site.test/x",
        task=Task.CANCEL_SUBSCRIPTION,
        store=store,
        with_enter=False,
        classify=False,
        confirm=user_confirm,
        client=_FakeAgentClient(),
        openai_client=object(),
        on_update=on_update,
    )
    reqs = [m for m in updates if m["type"] == "confirm_request"]
    assert len(reqs) == 1
    assert reqs[0]["journey"] == "leave"
    assert reqs[0]["action"] == "click 'Confirm cancellation'"
    assert reqs[0]["id"]
    assert confirm_calls == ["click 'Confirm cancellation'"]
    # wrapper mapped the user result through
    assert fake_rj.calls[0]["confirm_result"] == "approved"


@pytest.mark.asyncio
async def test_run_audit_confirm_denied_propagates(tmp_path, monkeypatch):
    fake_rj = _make_fake_run_journey()
    monkeypatch.setattr(pipeline, "run_journey", fake_rj)

    store = RunStore(tmp_path / "runs")

    async def deny(action: str) -> str:
        return "denied"

    await pipeline.run_audit(
        site_url="https://site.test/x",
        task=Task.CANCEL_SUBSCRIPTION,
        store=store,
        with_enter=False,
        classify=False,
        confirm=deny,
        client=_FakeAgentClient(),
        openai_client=object(),
    )
    assert fake_rj.calls[0]["confirm_result"] == "denied"
