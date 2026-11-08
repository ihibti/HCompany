"""Replacement-video pool: Linkup candidates + oEmbed enrich + classifier gate."""
from __future__ import annotations

import asyncio
import re
from typing import Any

import httpx
from pydantic import BaseModel

from app import store
from app.config import get_settings
from app.core.classify import classify
from app.models import TopicProfile, VideoMeta

MIN_POOL = 6

PATTERNS = {
    "youtube": (re.compile(r"[?&]v=([\w-]{6,})"), "video"),
    "youtube_shorts": (re.compile(r"/shorts/([\w-]{6,})"), "short"),
    "tiktok": (re.compile(r"/video/(\d{6,})"), "video"),
    "instagram": (re.compile(r"/reel/([\w-]{4,})"), "short"),
}

SITE_HINTS = {
    "youtube": "site:youtube.com",
    "youtube_shorts": "site:youtube.com/shorts",
    "tiktok": "site:tiktok.com",
    "instagram": "site:instagram.com/reel",
}


class _Candidates(BaseModel):
    videos: list[dict] = []  # {url, title, channel}


def normalize_id(platform: str, url: str) -> tuple[str, str] | None:
    pat, kind = PATTERNS.get(platform, (None, None))
    if not pat:
        return None
    m = pat.search(url or "")
    return (m.group(1), kind) if m else None


async def _oembed(platform: str, url: str, http: httpx.AsyncClient | None = None) -> dict | None:
    ep = {"youtube": "https://www.youtube.com/oembed",
          "youtube_shorts": "https://www.youtube.com/oembed",
          "tiktok": "https://www.tiktok.com/oembed"}.get(platform)
    if not ep:
        return None  # instagram: no public oembed without token
    own = http is None
    http = http or httpx.AsyncClient(timeout=10)
    try:
        r = await http.get(ep, params={"url": url, "format": "json"})
        if r.status_code >= 400:
            return None  # removed/private
        d = r.json()
        return {"title": d.get("title", ""), "channel": d.get("author_name", ""),
                "thumbnail_url": d.get("thumbnail_url", "")}
    except Exception:
        return None
    finally:
        if own:
            await http.aclose()


POOLS: dict[str, list[dict]] = {}       # profile|platform -> ready items
SERVED: dict[str, set[str]] = {}        # profile -> served ids
BUILDING: set[str] = set()


def _key(profile_id: str, platform: str) -> str:
    return f"{profile_id}|{platform}"


def _excluded_ids(profile_id: str, platform: str) -> set[str]:
    out = set(SERVED.get(profile_id, set()))
    for f in store.recent_feedback(profile_id, 500):
        if f["action"] in ("tomato", "auto_tomato") and f["video"].get("platform") == platform:
            out.add(f["video"]["id"])
    return out


async def _collect(profile: TopicProfile, platform: str, linkup_fn=None) -> list[dict]:
    s = get_settings()
    cand: dict[str, dict] = {}
    if s.fake_ai:
        for i in range(10):
            cand[f"fake-{platform}-{i}"] = {
                "platform": platform, "id": f"fx{i}", "url": f"http://localhost:8899/{platform}/{i}",
                "title": f"Vidéo {platform} dans le sujet #{i}", "channel": "@tomate",
                "thumbnail_url": "", "kind": "video", "reason": "démo", "source": "linkup"}
        return list(cand.values())
    if linkup_fn is None:
        from app.core.linkup import search_structured
        linkup_fn = search_structured
    for t in profile.include:
        for kw in (t.keywords or [t.topic])[:3]:
            q = f"{SITE_HINTS[platform]} {kw} video"
            try:
                res, _src = await asyncio.to_thread(linkup_fn, q, _Candidates, "standard")
            except Exception:
                continue
            for v in res.videos:
                url = v.get("url", "")
                norm = normalize_id(platform, url)
                if norm and norm[0] not in cand:
                    cand[norm[0]] = {"platform": platform, "id": norm[0], "url": url,
                                     "title": v.get("title", ""), "channel": v.get("channel", ""),
                                     "kind": norm[1], "source": "linkup"}
    # oEmbed enrich (drops removed/private)
    http = httpx.AsyncClient(timeout=10)
    try:
        for vid, c in list(cand.items()):
            meta = await _oembed(platform, c["url"], http)
            if platform in ("youtube", "youtube_shorts", "tiktok") and meta is None:
                del cand[vid]
                continue
            if meta:
                c.update({k: v for k, v in meta.items() if v})
    finally:
        await http.aclose()
    # scout results for the platform
    from app.core import h_jobs
    for j in h_jobs.JOBS.values():
        if j.kind == "scout" and j.platform == platform and j.status == "completed":
            for it in (j.result or {}).get("items", []):
                norm = normalize_id(platform, it.get("url", ""))
                if norm and norm[0] not in cand:
                    cand[norm[0]] = {"platform": platform, "id": norm[0], "url": it["url"],
                                     "title": it.get("title_or_caption", ""), "channel": it.get("creator", ""),
                                     "kind": norm[1], "source": "scout", "reason": it.get("why", "")}
    return list(cand.values())


async def _filter_on_topic(profile: TopicProfile, items: list[dict]) -> list[dict]:
    if get_settings().fake_ai:
        return items
    metas = [VideoMeta(platform=i["platform"], id=i["id"], url=i["url"],
                       title=i.get("title", ""), channel=i.get("channel", ""))
             for i in items]
    verdicts = await classify(metas, profile)
    by_id = {v.id: v for v in verdicts}
    return [i for i in items
            if by_id.get(i["id"]) and by_id[i["id"]].verdict == "on" and by_id[i["id"]].confidence >= 0.7]


async def build_pool(profile: TopicProfile, platform: str, linkup_fn=None):
    key = _key(profile.id, platform)
    if key in BUILDING:
        return
    BUILDING.add(key)
    try:
        items = await _collect(profile, platform, linkup_fn)
        excluded = _excluded_ids(profile.id, platform)
        items = [i for i in items if i["id"] not in excluded]
        on = await _filter_on_topic(profile, items)
        POOLS[key] = [i for i in on if i["id"] not in {x["id"] for x in POOLS.get(key, [])}]
    finally:
        BUILDING.discard(key)


async def kickoff(profile: TopicProfile, platforms: list[str] | None = None):
    for p in platforms or list(PATTERNS):
        asyncio.create_task(build_pool(profile, p))


async def get_replacements(profile: TopicProfile, platform: str,
                           exclude_ids: list[str], count: int) -> list[dict]:
    key = _key(profile.id, platform)
    pool = POOLS.setdefault(key, [])
    served = SERVED.setdefault(profile.id, set())
    excluded = _excluded_ids(profile.id, platform) | set(exclude_ids)
    out = []
    while pool and len(out) < count:
        item = pool.pop(0)
        if item["id"] in excluded:
            continue
        served.add(item["id"])
        out.append(item)
    if len(pool) < MIN_POOL and key not in BUILDING:
        asyncio.create_task(build_pool(profile, platform))
    return out
