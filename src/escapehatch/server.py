"""Escape Hatch web app: live race view, reports, hall of shame, benchmark, replay.

FastAPI + Jinja + vanilla JS + SSE. No external CDNs. Live batches run real
agent journeys through pipeline.run_audit; replay batches stream stored events
through the same message protocol.
"""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from openai import AsyncOpenAI
from pydantic import BaseModel
from sse_starlette.event import ServerSentEvent
from sse_starlette.sse import EventSourceResponse

from escapehatch.agent import JourneyRun
from escapehatch.gauntlet import load_levels
from escapehatch.keys import KeyPool
from escapehatch.models import Audit, Outcome
from escapehatch.pipeline import run_audit
from escapehatch.prompts import PATTERN_DEFINITIONS, Task
from escapehatch.report import audit_to_json, render_report_html
from escapehatch.scoring import effort_steps
from escapehatch.store import RunStore

logger = logging.getLogger(__name__)

APP_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = APP_DIR / "templates" / "app"
STATIC_DIR = APP_DIR / "static"
GAUNTLET_DIR = APP_DIR.parent.parent / "gauntlet"
LEVELS_JSON = GAUNTLET_DIR / "levels.json"

SHONG_HOSTS = {"agp.eu.hcompany.ai", "agp.hcompany.ai"}
CONFIRM_TIMEOUT_S = 120
REPLAY_STEP_DELAY_S = 0.9
SHOT_KEYS_VARS = ("HAI_API_KEY", "HCOMPANY_KEY")

_TASK_LABELS = {
    "refuse_cookies": "Refuse cookies",
    "accept_cookies": "Accept cookies",
    "cancel_subscription": "Cancel subscription",
    "subscribe": "Subscribe",
    "unsubscribe": "Unsubscribe",
}


def _shot_keys() -> list[str]:
    import os

    return [k for k in (os.environ.get(v) for v in SHOT_KEYS_VARS) if k]


class Batch:
    """One race: 1-3 audits streamed to SSE clients."""

    def __init__(self, batch_id: str, kind: str) -> None:
        self.batch_id = batch_id
        self.kind = kind  # "live" | "replay"
        self.audits: list[dict[str, Any]] = []
        self.history: list[dict[str, Any]] = []
        self.queues: list[asyncio.Queue] = []
        self.tasks: list[asyncio.Task] = []
        self.seq = 0
        self.done = asyncio.Event()
        self.created_at = datetime.now(timezone.utc)


class State:
    def __init__(self, store: RunStore, demo_store: RunStore | None) -> None:
        self.store = store
        self.demo_store = demo_store
        self.batches: dict[str, Batch] = {}
        self.pool: KeyPool | None = None
        self.openai: AsyncOpenAI | None = None
        self.pending: dict[str, dict[str, Any]] = {}
        self.controls: dict[tuple[str, str], JourneyRun] = {}
        self.http = httpx.AsyncClient(timeout=30)

    def get_pool(self) -> KeyPool:
        if self.pool is None:
            self.pool = KeyPool()
        return self.pool

    def get_openai(self) -> AsyncOpenAI:
        if self.openai is None:
            import os

            self.openai = AsyncOpenAI(
                base_url="https://api.hcompany.ai/v1",
                api_key=os.environ.get("HAI_API_KEY", ""),
            )
        return self.openai

    async def aclose(self) -> None:
        try:
            await self.http.aclose()
        except Exception:
            pass
        if self.pool is not None:
            await self.pool.aclose()
        if self.openai is not None:
            try:
                await self.openai.close()
            except Exception:
                pass


def _emit(batch: Batch, msg: dict[str, Any]) -> None:
    batch.seq += 1
    full = {"seq": batch.seq, "ts": time.time(), **msg}
    batch.history.append(full)
    for q in list(batch.queues):
        q.put_nowait(full)


def _batch_done(batch: Batch) -> None:
    if not batch.done.is_set():
        _emit(batch, {"type": "batch_done", "batch_id": batch.batch_id})
        batch.done.set()


# ---------------------------------------------------------------- audits listing


def _is_gauntlet(audit: Audit) -> bool:
    host = urlparse(audit.site_url).netloc
    return host.endswith("ihibti.github.io") or "/HCompany/level" in audit.site_url


def _load_audit_any(state: State, audit_id: str) -> tuple[Audit, RunStore] | None:
    for store in (state.store, state.demo_store):
        if store is None:
            continue
        path = store.root / audit_id / "audit.json"
        if path.exists():
            try:
                return Audit.model_validate_json(path.read_text()), store
            except Exception:
                logger.exception("bad audit.json %s", path)
    return None


def _all_audits(state: State) -> list[tuple[Audit, RunStore]]:
    """Unique audits across runs + demo stores (demo copy wins on id clash)."""
    seen: dict[str, tuple[Audit, RunStore]] = {}
    for store in (state.store, state.demo_store):
        if store is None:
            continue
        for audit_id in store.list_audits():
            if audit_id in seen:
                continue
            found = _load_audit_any(state, audit_id)
            if found:
                seen[audit_id] = found
    return list(seen.values())


def _hall_rows(state: State, task: str | None = None) -> list[dict[str, Any]]:
    rows = []
    for audit, store in _all_audits(state):
        if _is_gauntlet(audit):
            continue
        if audit.score.grade in {"?", "N/A"}:
            continue
        if task and audit.task.value != task:
            continue
        rows.append({"audit": audit, "store": store.name if hasattr(store, "name") else str(store.root)})
    rows.sort(key=lambda r: (-r["audit"].score.friction, r["audit"].site_url))
    return rows


# ---------------------------------------------------------------- live batches


class BatchIn(BaseModel):
    urls: list[str] = []
    task: str = "refuse_cookies"
    with_enter: bool = True
    credentials: str | None = None
    agent: str = "h/web-surfer-pro"
    replay: list[str] | None = None


async def _await_confirm(state: State, audit_id: str, action: str, req_id: str) -> str:
    loop = asyncio.get_running_loop()
    fut: asyncio.Future = loop.create_future()
    state.pending[req_id] = {
        "future": fut,
        "audit_id": audit_id,
        "action": action,
        "ts": time.time(),
    }
    try:
        return await asyncio.wait_for(fut, timeout=CONFIRM_TIMEOUT_S)
    except asyncio.TimeoutError:
        return "denied"
    finally:
        state.pending.pop(req_id, None)


async def _run_one_audit(state: State, batch: Batch, spec: dict[str, Any]) -> None:
    run_key = spec["run"]
    task = Task(spec["task"])

    async def on_update(msg: dict) -> None:
        _emit(batch, {"run": run_key, **msg})

    def on_started(side: str, run: JourneyRun) -> None:
        state.controls[(run_key, side)] = run

    async def confirm(action: str, req_id: str) -> str:
        return await _await_confirm(state, run_key, action, req_id)

    try:
        await run_audit(
            site_url=spec["site_url"],
            task=task,
            store=state.store,
            agent=spec["agent"],
            with_enter=spec.get("with_enter", True),
            credentials=spec.get("credentials"),
            enter_url=spec.get("enter_url"),
            confirm=confirm,
            on_update=on_update,
            on_journey_started=on_started,
            audit_id=run_key,
            openai_client=state.get_openai(),
            pool=state.get_pool(),
        )
    except Exception:
        logger.exception("audit %s failed", run_key)
        _emit(batch, {"type": "error", "run": run_key, "message": "audit run failed"})
    finally:
        state.controls = {k: v for k, v in state.controls.items() if k[0] != run_key}


async def _run_live_batch(state: State, batch: Batch, body: BatchIn) -> None:
    _emit(batch, {"type": "batch", "batch_id": batch.batch_id, "kind": "live",
                  "audits": batch.audits})
    await asyncio.gather(*(
        asyncio.create_task(_run_one_audit(state, batch, spec)) for spec in batch.audits
    ))
    _batch_done(batch)


# ---------------------------------------------------------------- replay batches


def _local_shot_url(store: RunStore, audit_id: str, url: str | None) -> str | None:
    if not url:
        return None
    if store.local_shot(url) is not None:
        name = store.local_shot(url).name  # type: ignore[union-attr]
        return f"/shots/{audit_id}/{name}"
    return None


def _rewrite_step(step: dict[str, Any], store: RunStore, audit_id: str) -> dict[str, Any]:
    s = dict(step)
    local = _local_shot_url(store, audit_id, s.get("screenshot_url"))
    if local:
        s["screenshot_url"] = local
    return s


async def _replay_one(state: State, batch: Batch, spec: dict[str, Any], delay: float,
                      freeze_after: int | None) -> None:
    run_key = spec["run"]
    found = _load_audit_any(state, run_key)
    if found is None:
        _emit(batch, {"type": "error", "run": run_key, "message": "audit not found"})
        return
    audit, store = found

    _emit(batch, {"type": "status", "run": run_key, "journey": "audit",
                  "status": "replay", "replay": True})
    emitted_steps = 0

    for side, journey in (("leave", audit.leave), ("enter", audit.enter)):
        if journey is None:
            continue
        _emit(batch, {"type": "status", "run": run_key, "journey": side,
                      "status": "running", "session_id": journey.session_id})
        seen: list[Any] = []
        for step in journey.steps:
            seen.append(step)
            effort = effort_steps(seen).total
            payload = _rewrite_step(step.model_dump(mode="json"), store, run_key)
            _emit(batch, {
                "type": "step", "run": run_key, "journey": side,
                "step": payload, "effort_so_far": effort,
            })
            emitted_steps += 1
            if freeze_after is not None and emitted_steps >= freeze_after:
                await asyncio.Event().wait()  # hold frozen state for screenshots
            await asyncio.sleep(delay)
        _emit(batch, {"type": "status", "run": run_key, "journey": side,
                      "status": journey.session_status, "session_id": journey.session_id,
                      "outcome": journey.outcome.value})

    _emit(batch, {"type": "phase", "run": run_key, "phase": "classifying",
                  "screenshots": 0})
    await asyncio.sleep(delay)
    for f in audit.findings:
        _emit(batch, {"type": "finding", "run": run_key,
                      "finding": f.model_dump(mode="json")})
        await asyncio.sleep(delay * 0.5)
    _emit(batch, {
        "type": "done", "run": run_key, "audit_id": audit.id,
        "grade": audit.score.grade, "friction": audit.score.friction,
        "headline": audit.score.headline,
    })


async def _run_replay_batch(state: State, batch: Batch, delay: float,
                            freeze_after: int | None) -> None:
    _emit(batch, {"type": "batch", "batch_id": batch.batch_id, "kind": "replay",
                  "audits": batch.audits})
    await asyncio.gather(*(
        asyncio.create_task(_replay_one(state, batch, spec, delay, freeze_after))
        for spec in batch.audits
    ))
    _batch_done(batch)


# ---------------------------------------------------------------- app factory


def create_app(store: RunStore, demo_store: RunStore | None = None) -> FastAPI:
    state = State(store, demo_store)
    app = FastAPI(title="Escape Hatch")
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        await state.aclose()

    # ------------------------------------------------------------- pages

    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request):
        audits = _all_audits(state)
        max_effort = max(
            (a.score.leave_effort.total for a, _ in audits
             if a.leave.outcome == Outcome.SUCCESS),
            default=0,
        )
        hall = _hall_rows(state)[:6]
        demo_runs = []
        if state.demo_store is not None:
            for aid in state.demo_store.list_audits():
                found = _load_audit_any(state, aid)
                if found is None:
                    continue
                a, _ = found
                demo_runs.append({
                    "id": a.id,
                    "site_url": a.site_url,
                    "task": a.task.value,
                })
        return templates.TemplateResponse(request, "home.html", {
            "request": request,
            "max_effort": max_effort,
            "hall": hall,
            "demo_runs": demo_runs,
            "tasks": _TASK_LABELS,
        })

    @app.get("/run/{batch_id}", response_class=HTMLResponse)
    async def run_page(request: Request, batch_id: str):
        batch = state.batches.get(batch_id)
        if batch is None:
            raise HTTPException(404, "unknown batch")
        return templates.TemplateResponse(request, "race.html", {
            "request": request,
            "batch_id": batch.batch_id,
            "kind": batch.kind,
            "audits": batch.audits,
        })

    @app.get("/replay/{audit_id}", response_class=HTMLResponse)
    async def replay_page(request: Request, audit_id: str,
                          speed: float = 1.0, at: int | None = None):
        found = _load_audit_any(state, audit_id)
        if found is None:
            raise HTTPException(404, "audit not found")
        audit, _ = found
        batch_id = f"replay-{uuid.uuid4().hex[:10]}"
        batch = Batch(batch_id, "replay")
        state.batches[batch_id] = batch
        host = urlparse(audit.site_url).netloc.removeprefix("www.")
        batch.audits = [{
            "run": audit.id,
            "site_url": audit.site_url,
            "task": audit.task.value,
            "agent": audit.leave.agent,
            "host": host,
        }]
        delay = REPLAY_STEP_DELAY_S / max(0.1, speed)
        freeze = at if at and at > 0 else None
        batch.tasks.append(asyncio.create_task(
            _run_replay_batch(state, batch, delay, freeze)))
        return templates.TemplateResponse(request, "race.html", {
            "request": request,
            "batch_id": batch.batch_id,
            "kind": "replay",
            "audits": batch.audits,
        })

    @app.get("/audits/{audit_id}", response_class=HTMLResponse)
    async def audit_page(audit_id: str):
        found = _load_audit_any(state, audit_id)
        if found is None:
            raise HTTPException(404, "audit not found")
        audit, store = found
        audit_dir = store.root / audit.id

        def resolver(url: str | None) -> str | None:
            if not url:
                return None
            for s in (state.store, state.demo_store):
                if s is not None and s.local_shot(url) is not None:
                    return f"/shots/{audit.id}/{s.local_shot(url).name}"  # type: ignore[union-attr]
            return None

        html = render_report_html(audit, resolver)
        toolbar = (
            '<div style="position:fixed;top:14px;right:14px;z-index:9999;display:flex;gap:8px">'
            f'<a href="/" style="background:#141816;color:#e8f5ee;padding:8px 14px;border-radius:10px;'
            'text-decoration:none;font:600 13px/1 -apple-system,sans-serif;border:1px solid #2a332e">'
            "&larr; Escape Hatch</a>"
            f'<a href="/api/audits/{audit.id}" download="audit.json" style="background:#14c06a;color:#06130c;'
            'padding:8px 14px;border-radius:10px;text-decoration:none;font:700 13px/1 -apple-system,sans-serif">'
            "Download JSON</a></div>"
        )
        html = html.replace("</body>", toolbar + "</body>")
        return HTMLResponse(html)

    @app.get("/api/audits/{audit_id}")
    async def audit_json(audit_id: str):
        found = _load_audit_any(state, audit_id)
        if found is None:
            raise HTTPException(404, "audit not found")
        return JSONResponse(json.loads(audit_to_json(found[0])))

    @app.get("/hall", response_class=HTMLResponse)
    async def hall(request: Request, task: str | None = None):
        rows = _hall_rows(state, task or None)
        return templates.TemplateResponse(request, "hall.html", {
            "request": request,
            "rows": rows,
            "task": task,
            "tasks": _TASK_LABELS,
        })

    @app.get("/benchmark", response_class=HTMLResponse)
    async def benchmark(request: Request):
        benches = _load_benchmarks(state)
        levels = load_levels(LEVELS_JSON)
        level_meta = {l.level: l for l in levels}
        pattern_names = {k: v.split(".")[0] for k, v in PATTERN_DEFINITIONS.items()}
        return templates.TemplateResponse(request, "benchmark.html", {
            "request": request,
            "benches": benches,
            "level_meta": level_meta,
            "pattern_names": pattern_names,
        })

    # ------------------------------------------------------------- api

    @app.post("/api/batches")
    async def create_batch(body: BatchIn):
        if body.replay:
            if not (1 <= len(body.replay) <= 6):
                raise HTTPException(400, "replay needs 1-6 audit ids")
            batch_id = f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
            batch = Batch(batch_id, "replay")
            state.batches[batch_id] = batch
            for aid in body.replay:
                found = _load_audit_any(state, aid)
                if found is None:
                    raise HTTPException(404, f"audit not found: {aid}")
                audit, _ = found
                batch.audits.append({
                    "run": audit.id,
                    "site_url": audit.site_url,
                    "task": audit.task.value,
                    "agent": audit.leave.agent,
                    "host": urlparse(audit.site_url).netloc.removeprefix("www."),
                })
            batch.tasks.append(asyncio.create_task(_run_replay_batch(state, batch, REPLAY_STEP_DELAY_S, None)))
            return {"batch_id": batch_id, "kind": "replay", "audits": batch.audits}

        urls = [u.strip() for u in body.urls if u.strip()]
        if not (1 <= len(urls) <= 3):
            raise HTTPException(400, "provide 1-3 urls")
        if body.task not in {t.value for t in Task}:
            raise HTTPException(400, "bad task")
        if not body.agent.startswith("h/"):
            raise HTTPException(400, "bad agent")
        batch_id = f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        batch = Batch(batch_id, "live")
        state.batches[batch_id] = batch
        for i, url in enumerate(urls):
            batch.audits.append({
                "run": f"{batch_id}-{i:02d}",
                "site_url": url,
                "task": body.task,
                "agent": body.agent,
                "with_enter": body.with_enter,
                "credentials": body.credentials,
                "host": urlparse(url).netloc.removeprefix("www."),
            })
        batch.tasks.append(asyncio.create_task(_run_live_batch(state, batch, body)))
        return {"batch_id": batch_id, "kind": "live", "audits": batch.audits}

    @app.get("/api/batches/{batch_id}")
    async def batch_meta(batch_id: str):
        batch = state.batches.get(batch_id)
        if batch is None:
            raise HTTPException(404, "unknown batch")
        return {
            "batch_id": batch.batch_id,
            "kind": batch.kind,
            "audits": batch.audits,
            "done": batch.done.is_set(),
        }

    @app.get("/api/batches/{batch_id}/events")
    async def batch_events(batch_id: str, request: Request):
        batch = state.batches.get(batch_id)
        if batch is None:
            raise HTTPException(404, "unknown batch")

        async def gen():
            # Buffered history first (survives reloads), then the live tail.
            # The queue is subscribed up front and used only as a wakeup
            # signal: every emitted message lands in batch.history, so the
            # drain below is the single source of truth and reconnects
            # replay exactly what was missed.
            sent = 0
            q: asyncio.Queue = asyncio.Queue()
            batch.queues.append(q)
            try:
                while True:
                    while sent < len(batch.history):
                        msg = batch.history[sent]
                        sent += 1
                        yield ServerSentEvent(data=json.dumps(msg))
                        if msg.get("type") == "batch_done":
                            return
                    if batch.done.is_set():
                        return
                    if await request.is_disconnected():
                        break
                    try:
                        await asyncio.wait_for(q.get(), timeout=15)
                    except asyncio.TimeoutError:
                        yield ServerSentEvent(data=json.dumps({"type": "ping"}))
                        continue
            finally:
                if q in batch.queues:
                    batch.queues.remove(q)

        return EventSourceResponse(gen())

    class ConfirmIn(BaseModel):
        approved: bool

    @app.post("/api/audits/{run}/confirm/{confirm_id}")
    async def resolve_confirm(run: str, confirm_id: str, body: ConfirmIn):
        p = state.pending.get(confirm_id)
        if p is None or p["future"].done():
            raise HTTPException(404, "unknown or expired confirmation")
        p["future"].set_result("approved" if body.approved else "denied")
        return {"ok": True}

    class MessageIn(BaseModel):
        text: str

    @app.post("/api/audits/{run}/{journey}/message")
    async def send_message(run: str, journey: str, body: MessageIn):
        handle = state.controls.get((run, journey))
        if handle is None:
            raise HTTPException(404, "no live session for this journey")
        await handle.send_message(body.text)
        return {"ok": True}

    @app.post("/api/audits/{run}/{journey}/{action}")
    async def control(run: str, journey: str, action: str):
        if action not in {"pause", "resume", "stop"}:
            raise HTTPException(400, "bad action")
        handle = state.controls.get((run, journey))
        if handle is None:
            raise HTTPException(404, "no live session for this journey")
        if action == "pause":
            await handle.pause()
        elif action == "resume":
            await handle.resume()
        else:
            await handle.cancel()
        return {"ok": True}

    @app.get("/api/shot")
    async def shot(u: str):
        host = urlparse(u).netloc
        if host not in SHONG_HOSTS:
            raise HTTPException(400, "host not allowed")
        for s in (state.store, state.demo_store):
            if s is not None:
                p = s.local_shot(u)
                if p is not None:
                    return FileResponse(p)
        last_status = None
        for key in _shot_keys():
            try:
                r = await state.http.get(
                    u, headers={"Authorization": f"Bearer {key}"},
                    follow_redirects=True,
                )
                last_status = r.status_code
                if r.status_code == 200 and r.content:
                    path = state.store.save_screenshot(u, r.content)
                    return FileResponse(path)
            except Exception:
                logger.exception("shot fetch failed")
        raise HTTPException(502, f"screenshot unavailable ({last_status})")

    @app.get("/shots/{audit_id}/{name}")
    async def stored_shot(audit_id: str, name: str):
        for s in (state.store, state.demo_store):
            if s is None:
                continue
            p = s.root / "shots" / name
            if p.exists() and p.suffix == ".jpg":
                return FileResponse(p)
        raise HTTPException(404, "shot not found")

    return app


def _load_benchmarks(state: State) -> list[dict[str, Any]]:
    """Latest benchmark JSON per agent across stores."""
    by_agent: dict[str, dict[str, Any]] = {}
    for store in (state.store, state.demo_store):
        if store is None:
            continue
        bdir = store.root / "benchmarks"
        if not bdir.is_dir():
            continue
        for bp in bdir.glob("*.json"):
            try:
                data = json.loads(bp.read_text())
            except Exception:
                continue
            agent = data.get("agent", "?")
            cur = by_agent.get(agent)
            if cur is None or data.get("created_at", "") > cur.get("created_at", ""):
                by_agent[agent] = data
    out = []
    for agent, data in by_agent.items():
        levels = data.get("levels", [])
        done = [l for l in levels if l.get("verdict") == "cancelled"]
        recalls = [l["recall"] for l in levels if l.get("recall") is not None]
        out.append({
            "agent": agent,
            "created_at": data.get("created_at"),
            "base": data.get("base"),
            "levels": levels,
            "success_rate": (len(done) / len(levels)) if levels else 0,
            "mean_recall": (sum(recalls) / len(recalls)) if recalls else 0,
            "total_cost": sum(l.get("cost_usd", 0) for l in levels),
        })
    out.sort(key=lambda b: b["created_at"] or "", reverse=True)
    return out
