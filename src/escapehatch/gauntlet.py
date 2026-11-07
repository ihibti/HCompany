"""Gauntlet ground truth: load levels.json, verify journeys, score pattern recall."""

import json
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from escapehatch.models import Finding, Journey

VerifyResult = Literal["cancelled", "trapped", "incomplete"]


class GauntletLevel(BaseModel):
    level: int
    title: str
    start_path: str
    signup_path: str
    success_path: str
    trap_paths: list[str] = Field(default_factory=list)
    min_leave_interactions: int
    min_enter_interactions: int
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


def verify_gauntlet(journey: Journey, level: GauntletLevel) -> VerifyResult:
    """Latest known page wins: final_url first, then step urls newest to oldest."""
    hit = _classify_url(journey.final_url, level)
    if hit:
        return hit
    for step in reversed(journey.steps):
        hit = _classify_url(step.url, level)
        if hit:
            return hit
    return "incomplete"


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
