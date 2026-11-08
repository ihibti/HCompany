from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class TopicSpec(BaseModel):
    topic: str
    keywords: list[str] = Field(default_factory=list)
    example_creators: list[str] = Field(default_factory=list)


class ExcludeSpec(BaseModel):
    topic: str
    keywords: list[str] = Field(default_factory=list)


class Source(BaseModel):
    name: str = ""
    url: str = ""


class TopicProfile(BaseModel):
    id: str
    raw_text: str = ""
    summary: str = ""
    include: list[TopicSpec] = Field(default_factory=list)
    exclude: list[ExcludeSpec] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=lambda: ["fr"])
    sources: list[Source] = Field(default_factory=list)


class VideoMeta(BaseModel):
    platform: str = ""
    id: str
    url: str = ""
    title: str = ""
    channel: str = ""
    description: str = ""
    hashtags: list[str] = Field(default_factory=list)
    duration: str | None = None


class Verdict(BaseModel):
    id: str
    verdict: Literal["on", "off", "unsure"]
    confidence: float = 0.5
    reason: str = ""


class FeedbackEntry(BaseModel):
    profile_id: str
    video: VideoMeta
    action: Literal["tomato", "undo", "auto_tomato"]
    ts: float = 0.0


class Job(BaseModel):
    id: str
    kind: str  # train | scout | login
    platform: str = ""
    status: str = "queued"  # queued | running | completed | failed | timed_out | interrupted
    agent_view_url: str | None = None
    session_id: str | None = None
    created_at: float = 0.0
    result: dict | None = None
    error: str | None = None
    profile_id: str = ""
    payload: dict = Field(default_factory=dict)
