from __future__ import annotations

import asyncio

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app import store
from app.config import get_settings
from app.core import h_jobs
from app.core.classify import classify
from app.core.profile import build_profile
from app.models import FeedbackEntry, Job, TopicProfile, Verdict, VideoMeta

app = FastAPI(title="Tomate — backend")
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"chrome-extension://.*|http://localhost(:[0-9]+)?|http://127\.0\.0\.1(:[0-9]+)?",
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _start_worker():
    asyncio.create_task(h_jobs.worker())


@app.get("/health")
def health():
    s = get_settings()
    return {"status": "ok",
            "keys": {"hai": bool(s.hai_api_key), "linkup": bool(s.linkup_api_key),
                     "gladia": bool(s.gladia_api_key)},
            "models": {"fast": s.holo_fast_model, "smart": s.holo_smart_model},
            "fake_ai": s.fake_ai}


class ProfileReq(BaseModel):
    text: str
    progress_id: str | None = None


@app.post("/profile", response_model=TopicProfile)
async def profile(body: ProfileReq):
    p = await build_profile(body.text, progress_id=body.progress_id)
    store.save_profile(p)
    from app.core.replacements import kickoff
    await kickoff(p)
    return p


@app.get("/profile_progress/{pid}")
def profile_progress(pid: str):
    from app.core.profile import PROGRESS
    return {"step": PROGRESS.get(pid, "holo")}


class ClassifyReq(BaseModel):
    profile_id: str
    videos: list[VideoMeta]


@app.post("/classify")
async def classify_ep(body: ClassifyReq):
    import time
    t0 = time.time()
    p = store.get_profile(body.profile_id)
    if not p:
        raise HTTPException(404, "profil inconnu")
    verdicts = await classify(body.videos, p)
    ms = int((time.time() - t0) * 1000)
    print(f"[classify] {len(body.videos)} videos in {ms}ms")
    return {"verdicts": verdicts, "timing_ms": {"total": ms, "holo": ms, "linkup": 0}}


class RefineReq(BaseModel):
    profile_id: str
    videos: list[VideoMeta]


@app.post("/classify/refine")
async def refine_ep(body: RefineReq):
    import time
    from app.core.classify import refine
    t0 = time.time()
    p = store.get_profile(body.profile_id)
    if not p:
        raise HTTPException(404, "profil inconnu")
    verdicts = await refine(body.videos, p)
    ms = int((time.time() - t0) * 1000)
    print(f"[refine] {len(body.videos)} videos in {ms}ms")
    return {"verdicts": verdicts, "timing_ms": {"total": ms, "holo": ms, "linkup": ms}}


class FeedbackReq(BaseModel):
    profile_id: str
    video: VideoMeta
    action: str


@app.post("/feedback")
async def feedback(body: FeedbackReq):
    if body.action not in ("tomato", "undo", "auto_tomato"):
        raise HTTPException(422, "action inconnue")
    store.add_feedback(FeedbackEntry(profile_id=body.profile_id, video=body.video,
                                     action=body.action))
    store.cache_invalidate(body.profile_id, body.video.platform, body.video.id)
    return {"ok": True}


class TrainReq(BaseModel):
    profile_id: str
    platform: str


@app.post("/train", status_code=201)
async def train(body: TrainReq):
    p = store.get_profile(body.profile_id)
    if not p:
        raise HTTPException(404, "profil inconnu")
    videos = store.pending_tomatoes(body.profile_id, body.platform)
    job = h_jobs.enqueue("train", body.platform, body.profile_id,
                         {"videos": videos, "profile": p.model_dump()})
    return job


class ScoutReq(BaseModel):
    profile_id: str
    platform: str
    count: int = 10


@app.post("/scout", status_code=201)
async def scout(body: ScoutReq):
    p = store.get_profile(body.profile_id)
    if not p:
        raise HTTPException(404, "profil inconnu")
    job = h_jobs.enqueue("scout", body.platform, body.profile_id,
                         {"count": body.count, "profile": p.model_dump()})
    return job


class LoginReq(BaseModel):
    platform: str


@app.post("/login", status_code=201)
async def login(body: LoginReq):
    job = h_jobs.enqueue("login", body.platform, "", {})
    return job


class ReplReq(BaseModel):
    profile_id: str
    platform: str
    exclude_ids: list[str] = []
    count: int = 5


@app.post("/replacements")
async def replacements(body: ReplReq):
    p = store.get_profile(body.profile_id)
    if not p:
        raise HTTPException(404, "profil inconnu")
    from app.core.replacements import PATTERNS, get_replacements
    if body.platform not in PATTERNS:
        raise HTTPException(422, "platform inconnue")
    return await get_replacements(p, body.platform, body.exclude_ids, body.count)


@app.post("/local/open-browser")
async def open_browser():
    """Launch the dedicated training Chrome WITHOUT remote debugging so the user can sign in."""
    import os, signal, subprocess
    profile = os.path.expanduser("~/.hai/chrome-profile")
    chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    # close any debugging-launched instance on this profile first
    subprocess.run(["pkill", "-f", "remote-debugging-port=9222"], capture_output=True)
    subprocess.Popen([chrome, f"--user-data-dir={profile}",
                      "https://accounts.google.com/ServiceLogin?service=youtube"])
    return {"ok": True, "profile": profile}


@app.post("/local/attach-browser")
async def attach_browser():
    """Relaunch the training Chrome WITH remote debugging so H can attach."""
    import os, subprocess
    profile = os.path.expanduser("~/.hai/chrome-profile")
    chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    subprocess.run(["pkill", "-f", f"user-data-dir={profile}"], capture_output=True)
    import time as _t; _t.sleep(1)
    subprocess.Popen([chrome, f"--user-data-dir={profile}", "--remote-debugging-port=9222",
                      "https://www.youtube.com/"])
    return {"ok": True, "debug_port": 9222}


@app.get("/jobs")
def jobs() -> list[Job]:
    return list(h_jobs.JOBS.values())


@app.get("/jobs/{job_id}")
def job(job_id: str) -> Job:
    j = h_jobs.JOBS.get(job_id)
    if not j:
        raise HTTPException(404, "job inconnu")
    return j
