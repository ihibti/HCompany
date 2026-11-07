from escapehatch.models import Finding, Outcome
from escapehatch.prompts import Task
from escapehatch.scoring import _grade, effort, score

from conftest import make_journey


def _finding(pattern="asymmetric_choice", severity=2) -> Finding:
    return Finding(
        pattern=pattern,
        severity=severity,
        evidence="evidence",
        explanation="explanation",
    )


class TestEffort:
    def test_interactions_counted(self):
        j = make_journey(["click_web", "write", "press_keys_web", "drag_and_drop_web", "select_option"])
        e = effort(j)
        assert e.interactions == 5
        assert e.total == 5

    def test_first_go_to_is_free(self):
        j = make_journey(["go_to_web", "click_web", "go_to_web", "go_back_web", "refresh_web"])
        e = effort(j)
        assert e.interactions == 1
        assert e.navigations == 3  # second go_to + go_back + refresh
        assert e.total == 4

    def test_detours_counted(self):
        j = make_journey(["web_search", "web_fetch", "click_web"])
        e = effort(j)
        assert e.detours == 2
        assert e.interactions == 1
        assert e.total == 3

    def test_scroll_wait_confirmation_cost_nothing(self):
        j = make_journey(["scroll_web", "wait_web", "request_confirmation", "mystery_tool", "click_web"])
        e = effort(j)
        assert e.interactions == 1
        assert e.total == 1


class TestScoreBranches:
    def test_failed_is_inconclusive(self):
        j = make_journey(["click_web"], outcome=Outcome.FAILED)
        s = score(j, None, [])
        assert s.grade == "?"
        assert s.friction == 0
        assert s.headline == "Inconclusive: the agent could not finish."

    def test_not_applicable(self):
        j = make_journey([], outcome=Outcome.NOT_APPLICABLE)
        s = score(j, None, [])
        assert s.grade == "N/A"
        assert s.friction == 0
        assert s.headline == "No exit flow found on this site."

    def test_impossible_is_f_100(self):
        j = make_journey([], outcome=Outcome.IMPOSSIBLE)
        s = score(j, None, [_finding()])
        assert s.grade == "F"
        assert s.friction == 100
        assert s.headline == "Leaving is impossible without paying or accepting."


class TestScoreMath:
    def test_base_effort_curve(self):
        # total=1 -> base 0; total=3 -> 12; total=11 -> 60 (cap)
        s1 = score(make_journey(["click_web"]), None, [])
        assert s1.friction == 0 and s1.grade == "A"
        s3 = score(make_journey(["click_web"] * 3), None, [])
        assert s3.friction == 12 and s3.grade == "B"
        s11 = score(make_journey(["click_web"] * 11), None, [])
        assert s11.friction == 60 and s11.grade == "D"

    def test_asymmetry_bonus_and_cap(self):
        leave = make_journey(["click_web"] * 7)
        enter = make_journey(["click_web"], task=Task.SUBSCRIBE)
        s = score(leave, enter, [])
        assert s.asymmetry_ratio == 7.0
        # base 36 + asym min(20, 5*(7-1-1)=25) = 20 -> 56
        assert s.friction == 56
        assert s.headline == "Leaving takes 7 actions. Subscribing takes 1."

    def test_asymmetry_free_confirmation_step(self):
        # leave 2 vs enter 1: the extra step is a legitimate confirmation
        leave = make_journey(["click_web"] * 2)
        enter = make_journey(["click_web"], task=Task.SUBSCRIBE)
        s = score(leave, enter, [])
        assert s.asymmetry_ratio == 2.0
        assert s.friction == 6  # base only, no asymmetry penalty
        assert s.grade == "A"

    def test_asymmetry_penalty_beyond_one_step(self):
        # leave 4 vs enter 1: 4-1-1=2 -> 5*2=10
        leave = make_journey(["click_web"] * 4)
        enter = make_journey(["click_web"], task=Task.SUBSCRIBE)
        s = score(leave, enter, [])
        assert s.friction == 18 + 10  # base 18 + asym 10
        assert s.grade == "C"

    def test_asymmetry_no_bonus_when_enter_heavier(self):
        leave = make_journey(["click_web"])
        enter = make_journey(["click_web"] * 3, task=Task.SUBSCRIBE)
        s = score(leave, enter, [])
        assert s.asymmetry_ratio == 1 / 3
        assert s.friction == 0

    def test_asymmetry_ignored_when_enter_not_success(self):
        leave = make_journey(["click_web"] * 5)
        enter = make_journey(["click_web"], outcome=Outcome.FAILED, task=Task.SUBSCRIBE)
        s = score(leave, enter, [])
        assert s.asymmetry_ratio is None
        assert s.friction == 24  # base only

    def test_pattern_points_sum_and_cap(self):
        findings = [
            _finding("asymmetric_choice", 3),   # 12
            _finding("confirmshaming", 2),       # 8
            _finding("hidden_option", 1),        # 4
        ]
        s = score(make_journey(["click_web"]), None, findings)
        assert s.pattern_points == 24
        assert s.friction == 24 and s.grade == "B"

    def test_pattern_points_use_max_severity_per_pattern(self):
        findings = [_finding("asymmetric_choice", 1), _finding("asymmetric_choice", 3)]
        s = score(make_journey(["click_web"]), None, findings)
        assert s.pattern_points == 12

    def test_pattern_points_capped_at_30(self):
        findings = [_finding(p, 3) for p in [
            "asymmetric_choice", "hidden_option", "forced_action", "confirmshaming",
            "nagging", "obstruction", "misdirection", "preselection",
            "false_urgency", "sneaking", "trick_question",
        ]]
        s = score(make_journey(["click_web"]), None, findings)
        assert s.pattern_points == 30
        assert s.friction == 30 and s.grade == "C"

    def test_friction_clamped_at_100(self):
        findings = [_finding(p, 3) for p in [
            "asymmetric_choice", "hidden_option", "forced_action", "confirmshaming",
            "nagging", "obstruction", "misdirection", "preselection",
            "false_urgency", "sneaking", "trick_question",
        ]]
        leave = make_journey(["click_web"] * 11)
        enter = make_journey(["click_web"], task=Task.SUBSCRIBE)
        s = score(leave, enter, findings)
        assert s.friction == 100
        assert s.grade == "F"

    def test_headline_without_enter(self):
        s = score(make_journey(["click_web"] * 4), None, [])
        assert s.headline == "Leaving takes 4 actions."

    def test_headline_accept_counterpart(self):
        leave = make_journey(["click_web"], task=Task.REFUSE_COOKIES)
        enter = make_journey(["click_web"], task=Task.ACCEPT_COOKIES)
        s = score(leave, enter, [])
        assert "Accepting takes 1." in s.headline


class TestGradeBoundaries:
    def test_grade_thresholds(self):
        assert _grade(0) == "A"
        assert _grade(10) == "A"
        assert _grade(11) == "B"
        assert _grade(25) == "B"
        assert _grade(26) == "C"
        assert _grade(45) == "C"
        assert _grade(46) == "D"
        assert _grade(70) == "D"
        assert _grade(71) == "F"
        assert _grade(100) == "F"
