"""Pure friction scoring: how much effort leaving takes vs entering."""

from escapehatch.events import ACTION_KIND
from escapehatch.models import Effort, Finding, Journey, Outcome, Score, Step
from escapehatch.prompts import Task


def effort_steps(steps: list[Step]) -> Effort:
    interactions = 0
    navigations = 0
    detours = 0
    go_to_count = 0
    for step in steps:
        kind = ACTION_KIND.get(step.action, "other")
        if kind == "interaction":
            interactions += 1
        elif kind == "navigation":
            if step.action == "go_to_web":
                go_to_count += 1
            else:
                navigations += 1
        elif kind == "detour":
            detours += 1
    # the first go_to_web is the initial navigation to the site: not effort
    navigations += max(0, go_to_count - 1)
    return Effort(
        interactions=interactions,
        navigations=navigations,
        detours=detours,
        total=interactions + navigations + detours,
    )


def effort(journey: Journey) -> Effort:
    return effort_steps(journey.steps)


def _grade(friction: int) -> str:
    if friction <= 10:
        return "A"
    if friction <= 25:
        return "B"
    if friction <= 45:
        return "C"
    if friction <= 70:
        return "D"
    return "F"


def _enter_verb(task: Task | None) -> str:
    return {
        Task.ACCEPT_COOKIES: "Accepting",
        Task.SUBSCRIBE: "Subscribing",
        Task.UNSUBSCRIBE: "Unsubscribing",
        Task.REFUSE_COOKIES: "Refusing",
        Task.CANCEL_SUBSCRIPTION: "Cancelling",
    }.get(task, "The counterpart flow")


def score(leave: Journey, enter: Journey | None, findings: list[Finding]) -> Score:
    leave_eff = effort(leave)
    enter_eff = effort(enter) if enter is not None else None

    if leave.outcome == Outcome.FAILED:
        return Score(
            leave_effort=leave_eff,
            enter_effort=enter_eff,
            asymmetry_ratio=None,
            pattern_points=0,
            friction=0,
            grade="?",
            headline="Inconclusive: the agent could not finish.",
        )
    if leave.outcome == Outcome.NOT_APPLICABLE:
        return Score(
            leave_effort=leave_eff,
            enter_effort=enter_eff,
            asymmetry_ratio=None,
            pattern_points=0,
            friction=0,
            grade="N/A",
            headline="No exit flow found on this site.",
        )
    if leave.outcome == Outcome.IMPOSSIBLE:
        return Score(
            leave_effort=leave_eff,
            enter_effort=enter_eff,
            asymmetry_ratio=None,
            pattern_points=0,
            friction=100,
            grade="F",
            headline="Leaving is impossible without paying or accepting.",
        )

    base = min(60, 6 * max(0, leave_eff.total - 1))

    asymmetry_ratio: float | None = None
    asym = 0
    if enter is not None and enter.outcome == Outcome.SUCCESS:
        ratio = leave_eff.total / max(1, enter_eff.total if enter_eff else 1)
        asymmetry_ratio = ratio
        if ratio > 1:
            asym = min(20, round(10 * (ratio - 1)))

    max_sev: dict[str, int] = {}
    for f in findings:
        max_sev[f.pattern] = max(max_sev.get(f.pattern, 0), f.severity)
    pattern_points = min(30, sum(4 * sev for sev in max_sev.values()))

    friction = max(0, min(100, base + asym + pattern_points))

    if enter is not None:
        headline = (
            f"Leaving takes {leave_eff.total} actions. "
            f"{_enter_verb(enter.task)} takes {enter_eff.total if enter_eff else 0}."
        )
    else:
        headline = f"Leaving takes {leave_eff.total} actions."

    return Score(
        leave_effort=leave_eff,
        enter_effort=enter_eff,
        asymmetry_ratio=asymmetry_ratio,
        pattern_points=pattern_points,
        friction=friction,
        grade=_grade(friction),
        headline=headline,
    )
