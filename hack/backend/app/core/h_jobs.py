"""H Agents job queue — one worker, cloud browser with the default profile."""
from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Awaitable, Callable

from pydantic import BaseModel

from app.config import get_settings
from app.models import Job

QUEUE: asyncio.Queue[Job] = asyncio.Queue()
JOBS: dict[str, Job] = {}

AGENT_SPEC = {
    "name": "tomate-trainer",
    "description": "Agit dans le navigateur du feed pour entraîner les recommandations.",
    "environments": [{"id": "feed-browser", "kind": "web", "use_default_browser_profile": True}],
}

SESSION_FACTORY: Callable[..., Awaitable[Any]] | None = None  # injectable for tests


def _client():
    import os
    from hai_agents import AsyncClient
    key = get_settings().hai_api_key
    if key:
        os.environ.setdefault("HAI_API_KEY", key)
    return AsyncClient()


def enqueue(kind: str, platform: str, profile_id: str, payload: dict) -> Job:
    job = Job(id=uuid.uuid4().hex[:10], kind=kind, platform=platform,
              profile_id=profile_id, created_at=time.time(), payload=payload)
    JOBS[job.id] = job
    QUEUE.put_nowait(job)
    return job


async def _run_session(instruction: str, schema: type[BaseModel], job: Job):
    """One H session; exposes agent_view_url via job fields as soon as known."""
    if SESSION_FACTORY is not None:
        return await SESSION_FACTORY(instruction, schema, job)
    settings = get_settings()
    spec = dict(AGENT_SPEC)
    if getattr(settings, "h_local", True):
        spec = {"name": "tomate-local", "description": "Entraîne le feed dans le Chrome local.",
                "environments": [{"id": "tomate-local", "kind": "web", "host": "user_device"}]}
    async with _client() as client:
        handle = await client.start_session(
            agent=spec,
            messages=[{"type": "user_message", "message": instruction}],
            answer_schema=schema,
        )
        job.session_id = handle.id
        try:
            sess = await handle.get()
            job.agent_view_url = getattr(sess, "agent_view_url", None)
        except Exception:
            pass
        result = await handle.wait_for_completion(answer_schema=schema)
        job.status = str(result.status)
        return result.answer


async def worker():
    """Single worker: only one default-profile session at a time."""
    while True:
        job = await QUEUE.get()
        job.status = "running"
        try:
            instruction, schema = build_instruction(job)
            if get_settings().fake_ai:
                await asyncio.sleep(0.05)
                job.status = "completed"
                job.result = fake_result(job)
            else:
                answer = await _run_session(instruction, schema, job)
                job.result = answer.model_dump() if hasattr(answer, "model_dump") else answer
                if job.kind == "login" and isinstance(job.result, dict):
                    from app import store
                    store._save("logins.json", {**store._load("logins.json", {}),
                                              job.platform: {"logged_in": job.result.get("logged_in", False),
                                                             "account_label": job.result.get("account_label", "")}})
                if job.kind == "train" and isinstance(job.result, dict) and job.result.get("logged_in") is False:
                    job.status = "failed"
                    job.error = f"H n'est pas connecté à ton compte {job.platform} : clique « Ouvrir le Chrome d'entraînement »"
                elif job.status == "running":
                    job.status = "completed"
        except Exception as e:  # noqa: BLE001
            job.status = "failed"
            job.error = str(e)
        finally:
            QUEUE.task_done()


class TrainActions(BaseModel):
    logged_in: bool = True
    account_label: str = ""
    actions: list[dict] = []  # {kind, video_url, title, ok, note}


class LoginReport(BaseModel):
    platform: str = ""
    logged_in: bool = False
    account_label: str = ""


class ScoutItems(BaseModel):
    items: list[dict] = []  # {url, title_or_caption, creator, why}


class _Idle(BaseModel):
    ok: bool = True


FEED_URLS = {
    "youtube": "https://www.youtube.com/",
    "tiktok": "https://www.tiktok.com/foryou",
    "instagram": "https://www.instagram.com/reels/",
    "youtube_shorts": "https://www.youtube.com/shorts",
}
LOGIN_URLS = {
    "youtube": "https://accounts.google.com/",
    "tiktok": "https://www.tiktok.com/login",
    "instagram": "https://www.instagram.com/accounts/login/",
}
NOT_INTERESTED = {
    "youtube": "le menu ⋮ d'une vidéo puis 'Pas intéressé'",
    "tiktok": "appui long ou menu Partager puis 'Pas intéressé'",
    "instagram": "le menu ⋯ d'une publication puis 'Pas intéressé'",
}


def build_instruction(job: Job) -> tuple[str, type[BaseModel]]:
    profile = job.payload.get("profile", {})
    sujets = profile.get("summary", "")
    inc = ", ".join(t.get("topic", "") for t in profile.get("include", []))
    if job.kind == "login":
        return (f"Ouvre {FEED_URLS.get(job.platform, LOGIN_URLS.get(job.platform, 'about:blank'))}. "
                "Si tu vois un bouton de connexion (avatar absent), ouvre la page de connexion et "
                "ATTENDS que l'utilisateur se connecte lui-même via Agent View — ne touche à rien. "
                "Quand l'utilisateur est connecté (avatar visible) ou après 5 minutes, réponds "
                '{"platform": "' + job.platform + '", "logged_in": true|false, "account_label": "nom du compte ou \""} '
                "et termine."), LoginReport
    if job.kind == "train":
        vids = job.payload.get("videos", [])
        acts = job.payload.get("actions", {"not_interested": True, "search_watch": True, "like": True})
        urls = "\n".join(f"- {v.get('url') or v.get('title')}" for v in vids) or "(le fil)"
        steps = [
            "ÉTAPE 0 — vérifie d'abord que tu es CONNECTÉ à un compte YouTube (avatar visible). "
            "Si tu n'es PAS connecté, ARRÊTE-TOI immédiatement et réponds "
            '{"logged_in": false, "account_label": "", "actions": []}.',
            f"Le profil utilisateur : {sujets}. Sujets voulus : {inc}.",
        ]
        n = 1
        if acts.get("not_interested", True):
            steps.append(
                f"ÉTAPE {n} — sur la page d'accueil et pour chacune de ces vidéos hors sujet, "
                f"utilise {NOT_INTERESTED.get(job.platform, 'le bouton Pas intéressé')} UNIQUEMENT "
                f"(jamais 'Ne pas recommander la chaîne') :\n{urls}")
            n += 1
        if acts.get("search_watch", True):
            steps.append(
                f"ÉTAPE {n} — pour chaque sujet voulu ({inc}), fais 1-2 recherches et regarde "
                "30 à 60 secondes de 2-3 résultats clairement dans le sujet.")
            n += 1
        if acts.get("like", True):
            steps.append(
                f"ÉTAPE {n} — aime au maximum 1-2 vidéos clairement dans le sujet par sujet.")
            n += 1
        steps.append(
            "INTERDIT — n'utilise jamais : s'abonner, commenter, 'Ne pas recommander la chaîne', partager.")
        steps.append(
            'Réponds {"logged_in": true, "account_label": "nom du compte", '
            '"actions": [{kind, video_url, title, ok, note}]} '
            '— kind ∈ not_interested|searched|watched|liked.')
        return "\n".join(steps), TrainActions
    # scout
    feed = FEED_URLS.get(job.platform, "https://www.tiktok.com/foryou")
    count = job.payload.get("count", 10)
    return (
        f"Ouvre {feed} et fais défiler le fil. Le profil utilisateur: {sujets}. "
        f"Sujets voulus: {inc}. Repère jusqu'à {count} contenus CLAIREMENT dans le sujet. "
        'Réponds {"items": [{url, title_or_caption, creator, why}]} — why en français.'
    ), ScoutItems


def fake_result(job: Job) -> dict:
    if job.kind == "train":
        return {"actions": [{"video_url": v.get("url", ""), "action": "not_interested", "ok": True,
                             "note": "simulé"} for v in job.payload.get("videos", [])]}
    if job.kind == "scout":
        return {"items": [{"url": "https://example.com/1", "title_or_caption": "Vidéo démo dans le sujet",
                           "creator": "@demo", "why": "simulé"}]}
    return {"ok": True}
