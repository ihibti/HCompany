"""Gauntlet ground truth: load levels.json, verify journeys, score pattern recall."""

import json
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from escapehatch.models import Finding, Journey
from escapehatch.prompts import Task

VerifyResult = Literal["cancelled", "trapped", "incomplete", "shortcut"]


class GauntletLevel(BaseModel):
    level: int
    task: Task = Task.CANCEL_SUBSCRIPTION
    title: str
    start_path: str
    signup_path: str | None = None
    success_path: str
    trap_paths: list[str] = Field(default_factory=list)
    min_leave_interactions: int
    min_enter_interactions: int | None = None
    patterns: list[str] = Field(default_factory=list)


def load_levels(path: str | Path) -> list[GauntletLevel]:
    data = json.loads(Path(path).read_text())
    items = data["levels"] if isinstance(data, dict) else data
    return [GauntletLevel.model_validate(item) for item in items]


def _norm_path(url: str | None) -> str:
    """URL -> normalized absolute path; directory-ish paths get index.html."""
    if not url:
        return ""
    path = urlparse(url).path or "/"
    path = "/" + path.lstrip("/")
    last = path.rsplit("/", 1)[-1]
    if path.endswith("/") or "." not in last:
        path = path.rstrip("/") + "/index.html"
    return path


def _matches(url_path: str, rel: str) -> bool:
    rel = "/" + rel.lstrip("/")
    last = rel.rsplit("/", 1)[-1]
    if rel.endswith("/") or "." not in last:
        rel = rel.rstrip("/") + "/index.html"
    return url_path == rel or url_path.endswith(rel)


def _classify_url(url: str | None, level: GauntletLevel) -> VerifyResult | None:
    path = _norm_path(url)
    if not path:
        return None
    if _matches(path, level.success_path):
        return "cancelled"
    for trap in level.trap_paths:
        if _matches(path, trap):
            return "trapped"
    return None


def _within_base(url: str | None, base: str) -> bool:
    if not url:
        return True
    b, u = urlparse(base), urlparse(url)
    if (u.scheme, u.netloc) != (b.scheme, b.netloc):
        return False
    return u.path.startswith(b.path.rstrip("/") + "/")


def detect_shortcut(journey: Journey, level: GauntletLevel, base_url: str) -> str | None:
    """Reason the leave journey took an off-path shortcut, else None.

    Flags off-site research tools (web_search/web_fetch), direct URL jumps to
    non-start pages inside the gauntlet (e.g. confirm.html), and any visited
    URL outside the gauntlet base.
    """
    start_seen = False
    for i, step in enumerate(journey.steps):
        act = step.action
        args = step.args or {}
        if act in ("web_search", "web_fetch"):
            what = args.get("query") or args.get("url") or act
            return f"{act}: {what}"
        if act == "go_to_web":
            target = args.get("url")
            if not start_seen:
                start_seen = True
            elif target:
                if not _within_base(target, base_url):
                    return f"navigated outside gauntlet: {target}"
                if not _matches(_norm_path(target), level.start_path):
                    return f"direct jump to {_norm_path(target)}"
        launchpad = i == 0 and act == "go_to_web"
        if step.url and not launchpad and not _within_base(step.url, base_url):
            return f"visited outside gauntlet: {step.url}"
    return None


def verify_gauntlet(
    journey: Journey, level: GauntletLevel, base_url: str | None = None
) -> VerifyResult:
    """Latest known page wins: final_url first, then step urls newest to oldest.

    A run that reached the success page via a shortcut (off-site tools or a
    direct URL jump) is reported as ``shortcut``, not ``cancelled``.
    The legacy ``cancelled`` verdict also denotes a verified email unsubscribe.
    """
    hit = _classify_url(journey.final_url, level)
    if hit is None:
        for step in reversed(journey.steps):
            hit = _classify_url(step.url, level)
            if hit:
                break
    if hit == "cancelled" and base_url:
        reason = detect_shortcut(journey, level, base_url)
        if reason:
            return "shortcut"
    return hit or "incomplete"


def pattern_recall(findings: list[Finding], level: GauntletLevel) -> tuple[float, float]:
    """(precision, recall) of detected pattern ids vs the level's ground truth."""
    predicted = {f.pattern for f in findings}
    truth = set(level.patterns)
    if not predicted and not truth:
        return 1.0, 1.0
    tp = len(predicted & truth)
    precision = tp / len(predicted) if predicted else 1.0
    recall = tp / len(truth) if truth else 1.0
    return precision, recall
