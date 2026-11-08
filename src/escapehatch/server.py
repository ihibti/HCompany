"""Escape Hatch web app: live race view, reports, hall of shame, benchmark, replay.

FastAPI + Jinja + vanilla JS + SSE. No external CDNs. Live batches run real
agent journeys through pipeline.run_audit; replay batches stream stored events
through the same message protocol.
"""

import asyncio
import json
import logging
import re
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
from escapehatch.events import offsite_help_reason
from escapehatch.gauntlet import detect_shortcut, load_levels, verify_gauntlet
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
GAUNTLET_BASE = "https://ihibti.github.io/HCompany/"

SHONG_HOSTS = {"agp.eu.hcompany.ai", "agp.hcompany.ai"}
_SHOT_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")
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
        rows.append({
            "audit": audit,
            "detour": offsite_help_reason(audit.leave),
            "store": store.name if hasattr(store, "name") else str(store.root),
        })
    # one row per (host, task): keep the most recent audit, older runs stay
    # reachable from their own audit pages
    best: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        a = row["audit"]
        key = (urlparse(a.site_url).netloc, a.task.value)
        cur = best.get(key)
        if cur is None or a.created_at > cur["audit"].created_at:
            best[key] = row
    rows = list(best.values())
    rows.sort(key=lambda r: (-r["audit"].score.friction, r["audit"].site_url))
    return rows


def _home_stats(state: State) -> dict[str, Any]:
    """Headline numbers for the home stats band (conclusive, non-gauntlet audits)."""
    rows = _hall_rows(state)
    hosts = {urlparse(r["audit"].site_url).netloc for r in rows}
    walls = sum(
        1 for r in rows
        if r["audit"].task == Task.REFUSE_COOKIES
        and r["audit"].leave.outcome == Outcome.IMPOSSIBLE
    )
    benches = _load_benchmarks(state)
    pro = next((b for b in benches if b["agent"] == "h/web-surfer-pro"), None) \
        or (benches[0] if benches else None)
    if pro:
        esc_runs = sum(l.get("escapes") or 0 for l in pro["levels"])
        tot_runs = sum(l.get("runs") or 1 for l in pro["levels"])
        netflux = f"{esc_runs}/{tot_runs}"
    else:
        netflux = "–"
    costs = []
    for audit, _ in _all_audits(state):
        if _is_gauntlet(audit) or audit.score.grade in {"?", "N/A"}:
            continue
        total = (audit.leave.cost_usd or 0.0) + ((audit.enter.cost_usd or 0.0) if audit.enter else 0.0)
        if audit.leave.cost_usd is not None or (audit.enter and audit.enter.cost_usd is not None):
            costs.append(total)
    return {
        "sites": len(hosts),
        "walls": walls,
        "netflux": netflux,
        "avg_cost": (sum(costs) / len(costs)) if costs else 0.0,
    }


# ---------------------------------------------------------------- live batches


class BatchIn(BaseModel):
    urls: list[str] = []
    task: str = "refuse_cookies"
    with_enter: bool = True
    credentials: str | None = None
    agent: str = "h/web-surfer-pro"
    replay: list[str] | None = None
    speed: float = 1.0
    at: int | None = None


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
            if step.action == "request_confirmation":
                action = (step.args or {}).get("action") or step.element or "irreversible action"
                _emit(batch, {
                    "type": "confirm_request", "run": run_key, "journey": side,
                    "id": f"replay-{emitted_steps}", "action": action,
                    "replay_auto": True,
                })
                await asyncio.sleep(delay * 1.6)
            if freeze_after is not None and emitted_steps >= freeze_after:
                await asyncio.Event().wait()  # hold frozen state for screenshots
            await asyncio.sleep(delay)
        _emit(batch, {"type": "status", "run": run_key, "journey": side,
                      "status": journey.session_status, "session_id": journey.session_id,
                      "outcome": journey.outcome.value})

    _emit(batch, {"type": "phase", "run": run_key, "phase": "classifying"})
    await asyncio.sleep(delay)
    for f in audit.findings:
        _emit(batch, {"type": "finding", "run": run_key,
                      "finding": f.model_dump(mode="json")})
        await asyncio.sleep(delay * 0.5)
    _emit(batch, {
        "type": "done", "run": run_key, "audit_id": audit.id,
        "grade": audit.score.grade, "friction": audit.score.friction,
        "headline": audit.score.headline,
        "outcome": audit.leave.outcome.value,
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
        # hero number: hardest REAL site (gauntlet excluded), conclusive outcomes only
        hero_pick = max(
            ((a.score.leave_effort.total, a) for a, _ in audits
             if not _is_gauntlet(a)
             and a.score.grade not in {"?", "N/A"}
             and a.leave.outcome in {Outcome.SUCCESS, Outcome.IMPOSSIBLE}),
            key=lambda t: t[0],
            default=(0, None),
        )
        max_effort, hero_audit = hero_pick
        hero = None
        if hero_audit is not None and max_effort > 0:
            hero = {
                "id": hero_audit.id,
                "site": urlparse(hero_audit.site_url).netloc.removeprefix("www."),
                "effort": max_effort,
                "impossible": hero_audit.leave.outcome == Outcome.IMPOSSIBLE,
            }
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
            "hero": hero,
            "stats": _home_stats(state),
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

        html = render_report_html(audit, resolver, home_url="/")
        host = urlparse(audit.site_url).netloc
        prev = [
            a for a, _ in _all_audits(state)
            if a.id != audit.id
            and urlparse(a.site_url).netloc == host
            and a.task == audit.task
        ]
        prev.sort(key=lambda a: a.created_at, reverse=True)

        def _grade_label(a: Audit) -> str:
            g = a.score.grade
            return "inconclusive" if g == "?" else g

        prev_links = "".join(
            f'<a href="/audits/{a.id}" style="color:#14c06a;text-decoration:none;'
            'margin-right:10px">'
            f'{_grade_label(a)} · {a.created_at.strftime("%Y-%m-%d %H:%M")}</a>'
            for a in prev[:5]
        )
        prev_row = (
            f'<div style="margin:14px 0 0;font:500 12px/1.6 -apple-system,sans-serif;'
            f'color:#8fa396">previous runs: {prev_links}</div>'
            if prev_links else ""
        )
        toolbar = (
            '<div class="eh-toolbar" style="position:fixed;top:0;left:0;right:0;z-index:9999;'
            'display:flex;align-items:center;gap:10px;padding:10px 18px;'
            'background:rgba(11,13,12,.92);backdrop-filter:blur(10px);'
            'border-bottom:1px solid rgba(255,255,255,.08)">'
            '<a href="/" style="background:#14c06a;color:#06130c;padding:7px 13px;'
            'border-radius:10px;text-decoration:none;font:700 12.5px/1 -apple-system,sans-serif">'
            "&larr; Escape Hatch</a>"
            '<span style="flex:1"></span>'
            '<button onclick="window.print()" style="background:#18211c;color:#e9f2ec;'
            'padding:7px 13px;border-radius:10px;font:600 12.5px/1 -apple-system,sans-serif;'
            'border:1px solid rgba(255,255,255,.12);cursor:pointer">'
            "Print / PDF</button>"
            f'<a href="/api/audits/{audit.id}" download="audit.json" style="background:#18211c;color:#e9f2ec;'
            'padding:7px 13px;border-radius:10px;text-decoration:none;font:600 12.5px/1 -apple-system,sans-serif;'
            'border:1px solid rgba(255,255,255,.12)">'
            "Download JSON</a></div>"
            '<style>.wrap{padding-top:84px !important}</style>'
        )
        html = html.replace("</body>", toolbar + "</body>")
        # previous runs as a small row right after the hero card
        marker = '<h2>Effort to leave vs enter</h2>'
        if prev_row and marker in html:
            html = html.replace(marker, prev_row + marker, 1)
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
            delay = REPLAY_STEP_DELAY_S / max(0.1, body.speed)
            freeze = body.at if body.at and body.at > 0 else None
            batch.tasks.append(asyncio.create_task(
                _run_replay_batch(state, batch, delay, freeze)))
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
        parsed = urlparse(u)
        if parsed.scheme != "https" or parsed.netloc not in SHONG_HOSTS:
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
        if not (_SHOT_NAME_RE.match(audit_id) and _SHOT_NAME_RE.match(name)):
            raise HTTPException(400, "bad shot path")
        if ".." in audit_id or ".." in name:
            raise HTTPException(400, "bad shot path")
        for s in (state.store, state.demo_store):
            if s is None:
                continue
            root = s.root.resolve() / "shots"
            p = (root / name).resolve()
            if not p.is_relative_to(root):
                continue
            if p.exists() and p.suffix == ".jpg":
                return FileResponse(p)
        raise HTTPException(404, "shot not found")

    return app


def _load_benchmarks(state: State) -> list[dict[str, Any]]:
    """Latest result per (agent, level) across all benchmark files, both stores.

    Also aggregates every recorded run per level (deduped by audit_id) so the
    page can show success counts and mean/range stats when n > 1.
    """
    per_level: dict[tuple[str, int], tuple[str, dict[str, Any]]] = {}
    audit_verdicts: dict[tuple[str, int], dict[str, str]] = {}
    level_runs: dict[tuple[str, int], dict[str, dict[str, Any]]] = {}
    shortcut_reasons: dict[tuple[str, int], dict[str, str]] = {}
    meta: dict[str, dict[str, Any]] = {}
    levels_by_num = {l.level: l for l in load_levels(LEVELS_JSON)}
    audit_cache: dict[str, Any] = {}

    def _recompute(aid: str, level_num: Any, base: str | None):
        """Verdict + shortcut reason from the stored journey, not the row."""
        if aid not in audit_cache:
            audit_cache[aid] = _load_audit_any(state, aid)
        found = audit_cache[aid]
        lvl = levels_by_num.get(level_num)
        if found is None or lvl is None:
            return None, None
        audit, _ = found
        b = base or GAUNTLET_BASE
        verdict = verify_gauntlet(audit.leave, lvl, b)
        reason = (
            detect_shortcut(audit.leave, lvl, b) if verdict == "shortcut" else None
        )
        return verdict, reason

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
            file_ts = data.get("created_at", "")
            file_base = data.get("base")
            meta.setdefault(agent, {"base": data.get("base"), "latest": ""})
            if file_ts > meta[agent]["latest"]:
                meta[agent]["latest"] = file_ts
            for row in data.get("levels", []):
                k = (agent, row.get("level"))
                aid = row.get("audit_id")
                if aid:
                    verdict, reason = _recompute(aid, row.get("level"), file_base)
                    audit_verdicts.setdefault(k, {})[aid] = (
                        verdict if verdict is not None else row.get("verdict")
                    )
                    if reason:
                        shortcut_reasons.setdefault(k, {})[aid] = reason
                    level_runs.setdefault(k, {}).setdefault(aid, row)
                cur = per_level.get(k)
                if cur is None or file_ts > cur[0]:
                    per_level[k] = (file_ts, row)

    def _spread(rows: list[dict[str, Any]], key: str) -> dict[str, float] | None:
        vals = [r[key] for r in rows if isinstance(r.get(key), (int, float))]
        if not vals:
            return None
        return {"mean": sum(vals) / len(vals), "min": min(vals), "max": max(vals), "n": len(vals)}

    by_agent: dict[str, list[dict[str, Any]]] = {}
    for (agent, level), (_, row) in per_level.items():
        k = (agent, level)
        verdicts = audit_verdicts.get(k) or {}
        reasons = shortcut_reasons.get(k) or {}
        n = max(1, len(verdicts))
        escapes = sum(1 for v in verdicts.values() if v == "cancelled")
        runs = list(level_runs.get(k, {}).values())
        aid = row.get("audit_id")
        entry = {**row, "runs": n, "escapes": escapes if verdicts else None}
        if aid and aid in verdicts:
            entry["verdict"] = verdicts[aid]
        if aid and aid in reasons:
            entry["shortcut_reason"] = reasons[aid]
        if len(runs) > 1:
            entry["effort_spread"] = _spread(runs, "leave_effort")
            entry["cost_spread"] = _spread(runs, "cost_usd")
        by_agent.setdefault(agent, []).append(entry)

    out = []
    for agent, levels in by_agent.items():
        levels.sort(key=lambda l: l.get("level") or 0)
        done = [l for l in levels if l.get("verdict") == "cancelled"]
        recalls = [l["recall"] for l in levels if l.get("recall") is not None]
        overheads = [
            l["leave_effort"] - l["min_leave_interactions"]
            for l in levels
            if l.get("leave_effort") is not None and l.get("min_leave_interactions") is not None
        ]
        out.append({
            "agent": agent,
            "base": meta.get(agent, {}).get("base"),
            "latest": meta.get(agent, {}).get("latest"),
            "levels": levels,
            "success_rate": (len(done) / len(levels)) if levels else 0,
            "escaped": len(done),
            "level_count": len(levels),
            "mean_recall": (sum(recalls) / len(recalls)) if recalls else 0,
            "mean_overhead": (sum(overheads) / len(overheads)) if overheads else 0,
            "total_cost": sum(l.get("cost_usd", 0) for l in levels),
            "total_runs": sum(l.get("runs", 1) for l in levels),
        })
    out.sort(key=lambda b: b["agent"])
    return out
