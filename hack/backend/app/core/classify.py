"""Video classification: Holo fast model, cache, unsure -> Linkup re-check."""
from __future__ import annotations

import asyncio
import json

from pydantic import BaseModel

from app import store
from app.config import get_settings
from app.core import fake_verdict
from app.models import TopicProfile, Verdict, VideoMeta

CHUNK = 8
MAX_PARALLEL = 4


class _VerdictItem(BaseModel):
    id: str
    verdict: str  # on | off | unsure
    confidence: float = 0.5
    reason: str = ""


class _VerdictBatch(BaseModel):
    verdicts: list[_VerdictItem]


def _profile_text(p: TopicProfile) -> str:
    inc = "; ".join(f"{t.topic} ({', '.join(t.keywords)})" for t in p.include)
    exc = "; ".join(t.topic for t in p.exclude)
    return f"SUJETS VOULUS: {inc}\nSUJETS REFUSÉS: {exc}\nRésumé: {p.summary}"


def _few_shot(profile_id: str) -> str:
    fb = store.recent_feedback(profile_id, 20)
    if not fb:
        return ""
    lines = []
    for f in fb:
        v = f["video"]
        label = "hors sujet" if f["action"] in ("tomato",) else "dans le sujet (tomate annulée)" if f["action"] == "undo" else "hors sujet (auto)"
        lines.append(f'- "{v.get("title", "")}" [{v.get("channel", "")}] -> {label}')
    return "EXEMPLES DE L'UTILISATEUR (prioritaires):\n" + "\n".join(lines)


def _video_line(v: VideoMeta) -> str:
    tags = " ".join("#" + h.lstrip("#") for h in v.hashtags[:6])
    return f"id={v.id} | titre: {v.title} | chaîne: {v.channel} | desc: {v.description[:200]} | {tags}"


async def _call_holo(videos: list[VideoMeta], profile: TopicProfile, fewshot: str,
                     context: str = "", holo_fn=None) -> list[_VerdictItem]:
    if holo_fn is None:
        from app.core.holo import chat_structured
        s = get_settings()
        holo_fn = lambda schema, messages: chat_structured(  # noqa: E731
            s.holo_fast_model, schema, messages, reasoning_effort="none")
    user = (
        _profile_text(profile) + "\n" + fewshot + "\n" + context +
        "\nVIDÉOS:\n" + "\n".join(_video_line(v) for v in videos) +
        '\nRéponds {"verdicts": [{id, verdict: "on"|"off"|"unsure", confidence, reason}]} '
        '— reason en français, très court, affiché à l\'utilisateur.'
    )
    result = await asyncio.to_thread(holo_fn, _VerdictBatch,
                                     [{"role": "user", "content": user}])
    return result.verdicts


async def classify(videos: list[VideoMeta], profile: TopicProfile,
                   holo_fn=None, linkup_fn=None) -> list[Verdict]:
    s = get_settings()
    out: dict[str, Verdict] = {}
    todo: list[VideoMeta] = []

    for v in videos:
        hit = store.cache_get(profile.id, v.platform, v.id)
        if hit:
            out[v.id] = Verdict.model_validate(hit)
        else:
            todo.append(v)

    if s.fake_ai:
        for v in todo:
            verdict, conf, reason = fake_verdict(v.title + " " + v.description, v.hashtags)
            d = {"id": v.id, "verdict": verdict, "confidence": conf, "reason": reason}
            store.cache_put(profile.id, v.platform, v.id, d)
            out[v.id] = Verdict.model_validate(d)
        return [out[v.id] for v in videos]

    # Holo chunks of CHUNK, up to MAX_PARALLEL concurrent
    fewshot = _few_shot(profile.id)
    sem = asyncio.Semaphore(MAX_PARALLEL)

    async def do_chunk(chunk: list[VideoMeta]) -> None:
        async with sem:
            items = await _call_holo(chunk, profile, fewshot, holo_fn=holo_fn)
        by_id = {it.id: it for it in items}
        for v in chunk:
            it = by_id.get(v.id)
            d = {"id": v.id, "verdict": it.verdict if it else "unsure",
                 "confidence": it.confidence if it else 0.3,
                 "reason": it.reason if it else "pas de réponse"}
            store.cache_put(profile.id, v.platform, v.id, d)
            out[v.id] = Verdict.model_validate(d)

    await asyncio.gather(*(do_chunk(todo[i:i + CHUNK]) for i in range(0, len(todo), CHUNK)))
    return [out[v.id] for v in videos]





async def refine(videos: list[VideoMeta], profile: TopicProfile,
                 holo_fn=None, linkup_fn=None) -> list[Verdict]:
    """Re-check unsure/low-confidence ids via parallel Linkup searches + one Holo call."""
    out: dict[str, Verdict] = {}
    if linkup_fn is None:
        from app.core.linkup import search_results
        linkup_fn = search_results

    async def snippet(v: VideoMeta) -> tuple[str, str]:
        try:
            res = await asyncio.to_thread(linkup_fn, f"{v.title} {v.channel}")
            return v.id, "\n".join(r.get("content", "")[:300] for r in (res or [])[:3])
        except Exception as e:  # noqa: BLE001
            return v.id, f"(recherche impossible: {e})"

    snippets = dict(await asyncio.gather(*(snippet(v) for v in videos[:8])))
    ctx = "\nCONTEXTE WEB:\n" + "\n".join(f"id={k}:\n{t}" for k, t in snippets.items())
    items = await _call_holo(videos, profile, _few_shot(profile.id), context=ctx, holo_fn=holo_fn)
    by_id = {it.id: it for it in items}
    for v in videos:
        it = by_id.get(v.id)
        if it:
            d = {"id": it.id, "verdict": it.verdict, "confidence": it.confidence,
                 "reason": it.reason}
            store.cache_put(profile.id, v.platform, v.id, d)
            out[v.id] = Verdict.model_validate(d)
    return [out[v.id] for v in videos if v.id in out]
