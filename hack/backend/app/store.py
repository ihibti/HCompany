"""Tiny JSON-file persistence for profiles, feedback and the classify cache."""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from app.config import get_settings
from app.models import FeedbackEntry, TopicProfile


def _dir() -> Path:
    d = get_settings().data_dir
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load(name: str, default):
    p = _dir() / name
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return default
    return default


def _save(name: str, data) -> None:
    (_dir() / name).write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def save_profile(p: TopicProfile) -> None:
    profiles = _load("profiles.json", {})
    profiles[p.id] = p.model_dump()
    _save("profiles.json", profiles)


def get_profile(pid: str) -> TopicProfile | None:
    d = _load("profiles.json", {}).get(pid)
    return TopicProfile.model_validate(d) if d else None


def list_profiles() -> list[dict]:
    return list(_load("profiles.json", {}).values())


def add_feedback(e: FeedbackEntry) -> None:
    e.ts = time.time()
    fb = _load("feedback.json", [])
    fb.append(e.model_dump())
    _save("feedback.json", fb[-500:])


def recent_feedback(profile_id: str, n: int = 20) -> list[dict]:
    fb = [f for f in _load("feedback.json", []) if f.get("profile_id") == profile_id]
    return fb[-n:]


def pending_tomatoes(profile_id: str, platform: str) -> list[dict]:
    """Videos tomatoed by the user, not undone, for /train."""
    fb = [f for f in _load("feedback.json", []) if f.get("profile_id") == profile_id]
    by_id: dict[str, dict] = {}
    for f in fb:
        key = f["video"]["id"]
        if f["action"] in ("tomato", "auto_tomato"):
            by_id[key] = f["video"]
        elif f["action"] == "undo":
            by_id.pop(key, None)
    return [v for v in by_id.values() if v.get("platform") == platform]


# ---- verdict cache: in-memory dict, write-behind (debounced ~2s)

_CACHE: dict | None = None
_DIRTY = False
_FLUSH_HANDLE: asyncio.TimerHandle | None = None


def _cache() -> dict:
    global _CACHE
    if _CACHE is None:
        _CACHE = _load("cache.json", {})
    return _CACHE


def _flush_later() -> None:
    global _FLUSH_HANDLE
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        _write_cache()
        return
    if _FLUSH_HANDLE is not None:
        _FLUSH_HANDLE.cancel()
    _FLUSH_HANDLE = loop.call_later(2.0, _write_cache)


def _write_cache() -> None:
    global _DIRTY, _FLUSH_HANDLE
    _FLUSH_HANDLE = None
    if _CACHE is None or not _DIRTY:
        return
    c = _CACHE
    if len(c) > 5000:
        c = dict(list(c.items())[-3000:])
        _CACHE.clear()
        _CACHE.update(c)
    (_dir() / "cache.json").write_text(json.dumps(c, ensure_ascii=False, default=str))
    _DIRTY = False


def cache_get(profile_id: str, platform: str, vid: str):
    return _cache().get(f"{profile_id}|{platform}|{vid}")


def cache_put(profile_id: str, platform: str, vid: str, verdict: dict) -> None:
    global _DIRTY
    _cache()[f"{profile_id}|{platform}|{vid}"] = verdict
    _DIRTY = True
    _flush_later()


def cache_invalidate(profile_id: str, platform: str, vid: str) -> None:
    global _DIRTY
    if _cache().pop(f"{profile_id}|{platform}|{vid}", None) is not None:
        _DIRTY = True
        _flush_later()


def flush_all() -> None:
    _write_cache()
