from datetime import datetime, timezone

import pytest

from escapehatch.models import AgentAnswer, Journey, Outcome, Step
from escapehatch.prompts import Task


def make_step(action: str, **kw) -> Step:
    defaults = dict(
        index=0,
        action=action,
        args={},
        element=None,
        reasoning=None,
        message=None,
        url=None,
        title=None,
        screenshot_url=None,
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    defaults.update(kw)
    return Step(**defaults)


def make_steps(actions: list[str]) -> list[Step]:
    return [
        make_step(a, index=i, element=f"el-{i}", screenshot_url=f"shot-{i}")
        for i, a in enumerate(actions)
    ]


def make_journey(
    actions: list[str] | None = None,
    *,
    outcome: Outcome = Outcome.SUCCESS,
    task: Task = Task.CANCEL_SUBSCRIPTION,
    steps: list[Step] | None = None,
    final_url: str | None = None,
    final_screenshot_url: str | None = None,
    answer: AgentAnswer | None = None,
) -> Journey:
    return Journey(
        session_id="sess-test",
        site_url="https://example.com",
        task=task,
        agent="h/web-surfer-pro",
        steps=steps if steps is not None else make_steps(actions or []),
        answer=answer,
        session_status="completed",
        outcome=outcome,
        cost_usd=0.01,
        duration_s=12.5,
        final_url=final_url,
        final_screenshot_url=final_screenshot_url,
    )


@pytest.fixture
def gauntlet_root():
    from pathlib import Path

    return Path(__file__).resolve().parent.parent / "gauntlet"
