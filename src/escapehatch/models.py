from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from escapehatch.legal import LegalRef
from escapehatch.prompts import PATTERN_DEFINITIONS, Task


class Outcome(str, Enum):
    SUCCESS = "success"
    IMPOSSIBLE = "impossible"
    NOT_APPLICABLE = "not_applicable"
    FAILED = "failed"
    BLOCKED = "blocked"


class AgentAnswer(BaseModel):
    completed: bool
    impossible: bool
    flow_found: bool
    interactions_reported: int
    steps: list[str]
    obstacles: list[str]
    final_state: str
    access_blocked: bool = False


class Step(BaseModel):
    index: int
    action: str
    args: dict
    element: str | None = None
    reasoning: str | None = None
    message: str | None = None
    url: str | None = None
    title: str | None = None
    screenshot_url: str | None = None
    timestamp: datetime


class Journey(BaseModel):
    session_id: str
    site_url: str
    task: Task
    agent: str
    steps: list[Step]
    answer: AgentAnswer | None = None
    session_status: str
    outcome: Outcome
    cost_usd: float | None = None
    duration_s: float | None = None
    final_url: str | None = None
    final_screenshot_url: str | None = None
    retried_from: str | None = None


class Finding(BaseModel):
    pattern: str
    severity: int = Field(ge=1, le=3)
    evidence: str
    explanation: str
    step_index: int | None = None
    screenshot_url: str | None = None

    @field_validator("pattern")
    @classmethod
    def _known_pattern(cls, v: str) -> str:
        if v not in PATTERN_DEFINITIONS:
            raise ValueError(f"unknown dark pattern id: {v!r}")
        return v


class Effort(BaseModel):
    interactions: int
    navigations: int
    detours: int
    total: int


class Score(BaseModel):
    leave_effort: Effort
    enter_effort: Effort | None = None
    asymmetry_ratio: float | None = None
    pattern_points: int
    friction: int
    grade: Literal["A", "B", "C", "D", "F", "N/A", "?"]
    headline: str


class Audit(BaseModel):
    id: str
    created_at: datetime
    site_url: str
    task: Task
    leave: Journey
    enter: Journey | None = None
    findings: list[Finding] = Field(default_factory=list)
    score: Score
    legal: list[LegalRef] = Field(default_factory=list)
