"""Build a TopicProfile from free text: Holo (smart) then Linkup expansion."""
from __future__ import annotations

import asyncio
import json

from pydantic import BaseModel

from app.config import get_settings
import uuid
from app.models import ExcludeSpec, TopicProfile, TopicSpec

PROGRESS: dict[str, str] = {}


class _Parsed(BaseModel):
    summary: str = ""
    include: list[dict] = []  # {topic, keywords[]}
    exclude: list[dict] = []  # {topic, keywords[]}
    languages: list[str] = ["fr"]


class _Expansion(BaseModel):
    keywords: list[str] = []
    creators: list[dict] = []  # {name, platform}


async def build_profile(text: str, holo_fn=None, linkup_fn=None, progress_id: str | None = None) -> TopicProfile:
    def prog(step: str):
        if progress_id:
            PROGRESS[progress_id] = step
    prog("holo")
    s = get_settings()
    pid = uuid.uuid4().hex[:10]

    if s.fake_ai:
        p = TopicProfile(
            id=pid, raw_text=text,
            summary=f"Démo : {text[:80]}",
            include=[{"topic": t.strip(), "keywords": [t.strip()], "example_creators": []}
                     for t in text.replace("pas de", ",").split(",") if t.strip()][:3],
            exclude=[{"topic": "drama", "keywords": ["drama", "célébrité"]},
                     {"topic": "gaming", "keywords": ["gaming"]}],
            languages=["fr"], sources=[])
        return p

    if holo_fn is None:
        from app.core.holo import chat_structured
        holo_fn = lambda schema, messages: chat_structured(  # noqa: E731
            s.holo_smart_model, schema, messages, reasoning_effort=None)

    parsed: _Parsed = await asyncio.to_thread(holo_fn, _Parsed, [
        {"role": "system", "content": (
            "Tu transformes une demande utilisateur en profil de curation. "
            "Réponds en JSON {summary (une phrase, français), "
            "include: [{topic, keywords: [termes de recherche associés]}], "
            "exclude: [{topic, keywords}], languages: [codes langue]}.")},
        {"role": "user", "content": text},
    ])

    profile = TopicProfile(id=pid, raw_text=text, summary=parsed.summary,
                           languages=parsed.languages or ["fr"])
    sources: list[dict] = []

    prog("linkup")
    if linkup_fn is None:
        from app.core.linkup import search_structured
        linkup_fn = search_structured

    async def expand(topic: dict) -> dict:
        q = (f"YouTube TikTok Instagram créateurs chaînes de référence et mots-clés "
             f"sur le sujet: {topic['topic']} {' '.join(topic.get('keywords', []))}")
        exp, src = await asyncio.to_thread(linkup_fn, q, _Expansion, "standard")
        sources.extend(src)
        return {"topic": topic["topic"],
                "keywords": sorted(set(topic.get("keywords", [])) | set(exp.keywords))[:15],
                "example_creators": [c.get("name", "") for c in exp.creators if c.get("name")][:8]}

    expanded = await asyncio.gather(*(expand(t) for t in parsed.include)) if parsed.include else []
    profile.include = [TopicSpec.model_validate(e) for e in expanded]
    prog("done")
    profile.exclude = [ExcludeSpec.model_validate({"topic": t["topic"], "keywords": t.get("keywords", [])})
                       for t in parsed.exclude]
    seen = set()
    for src in sources:
        if src.get("url") and src["url"] not in seen:
            seen.add(src["url"])
            profile.sources.append(src)
    return profile
