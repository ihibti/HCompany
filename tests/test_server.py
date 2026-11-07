import asyncio
import io
import json
import time
from datetime import datetime, timezone

import httpx
import pytest
from PIL import Image

import escapehatch.server as server
from escapehatch.models import Audit, Outcome
from escapehatch.prompts import Task
from escapehatch.scoring import score
from escapehatch.server import create_app
from escapehatch.store import RunStore

from conftest import make_journey, make_step


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (100, 80), (10, 20, 30)).save(buf, "PNG")
    return buf.getvalue()


class FakeJourneyRun:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def pause(self):
        self.calls.append("pause")

    async def resume(self):
        self.calls.append("resume")

    async def cancel(self):
        self.calls.append("cancel")

    async def send_message(self, text: str):
        self.calls.append(f"msg:{text}")


def _make_fake_run_audit(registry: dict, confirm_result_probe: dict):
    async def fake_run_audit(**kwargs):
        on_update = kwargs["on_update"]
        on_started = kwargs["on_journey_started"]
        confirm = kwargs["confirm"]
        audit_id = kwargs["audit_id"]
        for side in ("leave", "enter"):
            run = FakeJourneyRun()
            registry[(audit_id, side)] = run
            on_started(side, run)
        await on_update({"type": "status", "journey": "leave", "status": "running"})
        await on_update({
            "type": "step", "journey": "leave",
            "step": {"index": 0, "action": "go_to_web", "args": {"url": "https://x.test"},
                     "element": None, "screenshot_url": "https://shots/s1.png",
                     "timestamp": "2026-01-01T00:00:00Z"},
            "effort_so_far": 0,
        })
        await on_update({
            "type": "step", "journey": "leave",
            "step": {"index": 1, "action": "click_web",
                     "args": {"x": 0.5, "y": 0.5, "element": "Cancel"},
                     "screenshot_url": "https://shots/s2.png",
                     "timestamp": "2026-01-01T00:00:01Z"},
            "effort_so_far": 1,
        })
        res = None
        if confirm is not None and kwargs.get("task") == Task.CANCEL_SUBSCRIPTION:
            await on_update({"type": "confirm_request", "journey": "leave",
                             "id": "req-fixed-1", "action": "click Confirm cancellation"})
            res = await confirm("click Confirm cancellation", "req-fixed-1")
            confirm_result_probe["result"] = res
        gate = confirm_result_probe.get("gate")
        if gate is not None:
            await gate.wait()
        await on_update({"type": "status", "journey": "leave",
                         "status": "completed", "outcome": "success"})
        await on_update({"type": "done", "audit_id": audit_id, "grade": "A",
                         "friction": 5, "headline": "easy"})
        return None

    return fake_run_audit


@pytest.fixture
def app_and_state(tmp_path, monkeypatch):
    monkeypatch.setenv("HAI_API_KEY", "test-key")
    monkeypatch.delenv("HCOMPANY_KEY", raising=False)
    store = RunStore(tmp_path / "runs")
    registry: dict = {}
    probe: dict = {}
    monkeypatch.setattr(server, "run_audit", _make_fake_run_audit(registry, probe))
    app = create_app(store, None)
    return app, store, registry, probe


async def _aiter_sse(resp: httpx.Response):
    """Yield parsed SSE data payloads from a streaming response."""
    buf = ""
    async for chunk in resp.aiter_text():
        buf += chunk
        while "\n\n" in buf:
            block, buf = buf.split("\n\n", 1)
            for line in block.splitlines():
                if line.startswith("data:"):
                    yield json.loads(line[5:].strip())
    if buf.strip():
        for line in buf.splitlines():
            if line.startswith("data:"):
                yield json.loads(line[5:].strip())


async def _collect_sse(client: httpx.AsyncClient, url: str, want: int = 500):
    msgs = []
    async with client.stream("GET", url) as resp:
        assert resp.status_code == 200
        async for m in _aiter_sse(resp):
            msgs.append(m)
            if len(msgs) >= want:
                break
    return msgs


@pytest.mark.asyncio
async def test_batch_flow_and_sse(app_and_state):
    app, store, registry, probe = app_and_state
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        res = await client.post("/api/batches", json={
            "urls": ["https://a.test", "https://b.test"],
            "task": "refuse_cookies", "with_enter": False, "agent": "h/web-surfer-pro",
        })
        assert res.status_code == 200
        data = res.json()
        batch_id = data["batch_id"]
        assert data["kind"] == "live"
        assert len(data["audits"]) == 2

        msgs = await _collect_sse(client, f"/api/batches/{batch_id}/events")
        types = [m["type"] for m in msgs]
        assert "batch" in types and "step" in types and "done" in types and "batch_done" in types
        steps = [m for m in msgs if m["type"] == "step"]
        assert steps[0]["journey"] == "leave" and steps[0]["run"].endswith("-00")
        seqs = [m["seq"] for m in msgs if "seq" in m]
        assert seqs == sorted(seqs)
        # batch meta endpoint
        meta = await client.get(f"/api/batches/{batch_id}")
        assert meta.json()["done"] is True


def _sse_messages(text: str) -> list[dict]:
    msgs = []
    for block in text.split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data:"):
                msgs.append(json.loads(line[5:].strip()))
    return msgs


async def _resolve_confirm(client: httpx.AsyncClient, run_key: str,
                           confirm_id: str, approved: bool) -> None:
    """Poll the confirm endpoint until the pending request registers."""
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        r = await client.post(f"/api/audits/{run_key}/confirm/{confirm_id}",
                              json={"approved": approved})
        if r.status_code == 200:
            return
        await asyncio.sleep(0.05)
    raise AssertionError("confirmation never became pending")


@pytest.mark.asyncio
async def test_confirm_endpoint_resolves(app_and_state):
    app, store, registry, probe = app_and_state
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        res = await client.post("/api/batches", json={
            "urls": ["https://a.test"], "task": "cancel_subscription",
            "with_enter": False, "agent": "h/web-surfer-pro",
        })
        batch_id = res.json()["batch_id"]
        run_key = res.json()["audits"][0]["run"]

        # ASGITransport buffers SSE bodies, so the events GET only returns
        # once the batch completes; run it as a task and resolve the
        # confirmation while it is in flight.
        get_task = asyncio.create_task(
            client.get(f"/api/batches/{batch_id}/events"))
        await _resolve_confirm(client, run_key, "req-fixed-1", True)
        resp = await asyncio.wait_for(get_task, 20)
        assert resp.status_code == 200
        msgs = _sse_messages(resp.text)
        types = [m["type"] for m in msgs]
        assert "confirm_request" in types and "batch_done" in types
        assert probe["result"] == "approved"

        r2 = await client.post(f"/api/audits/{run_key}/confirm/req-fixed-1",
                               json={"approved": True})
        assert r2.status_code == 404


@pytest.mark.asyncio
async def test_confirm_deny(app_and_state):
    app, store, registry, probe = app_and_state
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        res = await client.post("/api/batches", json={
            "urls": ["https://a.test"], "task": "cancel_subscription",
            "with_enter": False, "agent": "h/web-surfer-pro",
        })
        batch_id = res.json()["batch_id"]
        run_key = res.json()["audits"][0]["run"]
        get_task = asyncio.create_task(
            client.get(f"/api/batches/{batch_id}/events"))
        await _resolve_confirm(client, run_key, "req-fixed-1", False)
        resp = await asyncio.wait_for(get_task, 20)
        msgs = _sse_messages(resp.text)
        assert any(m["type"] == "batch_done" for m in msgs)
        assert probe["result"] == "denied"


@pytest.mark.asyncio
async def test_control_endpoints(app_and_state):
    app, store, registry, probe = app_and_state
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        probe["gate"] = asyncio.Event()
        res = await client.post("/api/batches", json={
            "urls": ["https://a.test"], "task": "refuse_cookies",
            "with_enter": True, "agent": "h/web-surfer-pro",
        })
        run_key = res.json()["audits"][0]["run"]
        await asyncio.sleep(0.3)
        for action in ("pause", "resume", "stop"):
            r = await client.post(f"/api/audits/{run_key}/leave/{action}")
            assert r.status_code == 200
        r = await client.post(f"/api/audits/{run_key}/enter/pause")
        assert r.status_code == 200
        r = await client.post(f"/api/audits/{run_key}/leave/message",
                              json={"text": "hello agent"})
        assert r.status_code == 200
        assert registry[(run_key, "leave")].calls == ["pause", "resume", "cancel", "msg:hello agent"]
        assert registry[(run_key, "enter")].calls == ["pause"]
        r = await client.post("/api/audits/nope/leave/pause")
        assert r.status_code == 404
        probe["gate"].set()
        msgs = await _collect_sse(client, f"/api/batches/{res.json()['batch_id']}/events")
        assert any(m["type"] == "batch_done" for m in msgs)


@pytest.mark.asyncio
async def test_shot_proxy_allowlist(app_and_state):
    app, store, registry, probe = app_and_state
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        r = await client.get("/api/shot", params={"u": "https://evil.example.com/x.png"})
        assert r.status_code == 400
        r = await client.get("/api/shot", params={"u": "https://ihibti.github.io/x.png"})
        assert r.status_code == 400
        url = "https://agp.eu.hcompany.ai/api/v1/trajectories/s/resources/b/k"
        store.save_screenshot(url, _png())
        r = await client.get("/api/shot", params={"u": url})
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/jpeg"


def _save_test_audit(store: RunStore, audit_id: str, site_url: str,
                     outcome: Outcome = Outcome.SUCCESS) -> None:
    steps = [make_step("click_web", index=0, args={"x": 0.1, "y": 0.2})]
    leave = make_journey(steps=steps, outcome=outcome)
    audit = Audit(
        id=audit_id, created_at=datetime.now(timezone.utc),
        site_url=site_url, task=Task.REFUSE_COOKIES, leave=leave, enter=None,
        findings=[], score=score(leave, None, []),
        legal=[],
    )
    store.save_audit(audit)


@pytest.mark.asyncio
async def test_replay_streams_steps_then_done(tmp_path, monkeypatch):
    monkeypatch.setenv("HAI_API_KEY", "test-key")
    store = RunStore(tmp_path / "runs")
    _save_test_audit(store, "audit-replay-1", "https://example.com/page")
    app = create_app(store, None)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        res = await client.post("/api/batches", json={"replay": ["audit-replay-1"]})
        assert res.status_code == 200
        batch_id = res.json()["batch_id"]
        msgs = await _collect_sse(client, f"/api/batches/{batch_id}/events")
        steps = [m for m in msgs if m["type"] == "step"]
        assert [s["step"]["index"] for s in steps] == [0]
        assert steps[0]["journey"] == "leave"
        dones = [m for m in msgs if m["type"] == "done"]
        assert dones and dones[0]["audit_id"] == "audit-replay-1"
        assert any(m["type"] == "batch_done" for m in msgs)

        r = await client.get("/replay/audit-replay-1")
        assert r.status_code == 200
        assert "REPLAY" in r.text


@pytest.mark.asyncio
async def test_hall_excludes_gauntlet_and_inconclusive(tmp_path, monkeypatch):
    monkeypatch.setenv("HAI_API_KEY", "test-key")
    store = RunStore(tmp_path / "runs")
    _save_test_audit(store, "a-normal", "https://normal.com")
    _save_test_audit(store, "a-gauntlet",
                     "https://ihibti.github.io/HCompany/level2/index.html")
    _save_test_audit(store, "a-inconclusive", "https://lost.com",
                     outcome=Outcome.FAILED)
    app = create_app(store, None)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        r = await client.get("/hall")
        assert r.status_code == 200
        assert "/audits/a-normal" in r.text
        assert "a-gauntlet" not in r.text
        assert "a-inconclusive" not in r.text

        r = await client.get("/")
        assert r.status_code == 200
        assert "Leaving takes" in r.text
