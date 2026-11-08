import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

from escapehatch.gauntlet import (
    GauntletLevel, detect_shortcut, load_levels, pattern_recall, verify_gauntlet,
)
from escapehatch.models import Finding
from escapehatch.prompts import PATTERN_DEFINITIONS, Task

from conftest import make_journey, make_step

GAUNTLET_DIR = Path(__file__).resolve().parent.parent / "gauntlet"
LEVELS_JSON = GAUNTLET_DIR / "levels.json"


@pytest.fixture(scope="module")
def levels() -> list[GauntletLevel]:
    return load_levels(LEVELS_JSON)


class TestLoadLevels:
    def test_levels_load_with_task_defaults(self, levels):
        assert [l.level for l in levels] == list(range(1, 8))
        assert all(l.task == Task.CANCEL_SUBSCRIPTION for l in levels[:5])
        assert all(l.task == Task.UNSUBSCRIBE for l in levels[5:])
        assert all(l.signup_path is None and l.min_enter_interactions is None
                   for l in levels[5:])

    def test_invalid_task_rejected(self, levels):
        with pytest.raises(ValueError):
            GauntletLevel.model_validate({**levels[0].model_dump(), "task": "unknown"})

    def test_patterns_are_known_ids(self, levels):
        for level in levels:
            for p in level.patterns:
                assert p in PATTERN_DEFINITIONS, f"level {level.level}: unknown pattern {p}"

    def test_required_paths_exist(self, levels):
        for level in levels:
            for rel in [level.start_path, level.signup_path, level.success_path, *level.trap_paths]:
                if rel is None:
                    continue
                assert (GAUNTLET_DIR / rel).is_file(), f"level {level.level}: missing {rel}"


class _LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs = []

    def handle_starttag(self, tag, attrs):
        for k, v in attrs:
            if k in ("href", "src") and v:
                self.refs.append(v)


def _resolve(base: Path, ref: str) -> Path | None:
    """Resolve a link target; None for external/fragment/non-file refs."""
    ref = ref.strip()
    if not ref or ref.startswith(("#", "javascript:", "mailto:", "tel:", "data:")):
        return None
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", ref):  # http://, https://, etc.
        return None
    path = ref.split("#", 1)[0].split("?", 1)[0]
    if not path:
        return None
    target = (base.parent / path) if not path.startswith("/") else Path(path)
    target = target.resolve()
    # directory link -> its index.html
    if target.is_dir():
        target = target / "index.html"
    return target


def test_all_html_links_resolve(gauntlet_root):
    html_files = sorted(gauntlet_root.rglob("*.html"))
    assert len(html_files) >= 30
    missing = []
    for f in html_files:
        parser = _LinkParser()
        parser.feed(f.read_text())
        # also catch JS navigation literals like location.href = "x.html"
        text = f.read_text()
        for m in re.finditer(r"""["']([^"']+\.html)["']""", text):
            parser.refs.append(m.group(1))
        for ref in parser.refs:
            target = _resolve(f, ref)
            if target is not None and not target.exists():
                missing.append(f"{f.relative_to(gauntlet_root)} -> {ref}")
    assert not missing, "broken links:\n" + "\n".join(missing)


def _level(levels, n) -> GauntletLevel:
    return next(l for l in levels if l.level == n)


class TestVerifyGauntlet:
    BASE = "http://localhost:8080"

    @pytest.mark.parametrize("n", [6, 7])
    def test_unsubscribe_success_and_incomplete(self, levels, n):
        level = _level(levels, n)
        for path, verdict in [(level.success_path, "cancelled"),
                              (level.start_path, "incomplete"), ("missing.html", "incomplete")]:
            j = make_journey([], task=Task.UNSUBSCRIBE, final_url=f"{self.BASE}/{path}")
            assert verify_gauntlet(j, level, self.BASE) == verdict
        j = make_journey(steps=[make_step("click_web", url=f"{self.BASE}/{level.success_path}")],
                         task=Task.UNSUBSCRIBE)
        assert verify_gauntlet(j, level, self.BASE) == "cancelled"

    def test_unsubscribe_frequency_trap(self, levels):
        level = _level(levels, 7)
        j = make_journey([], task=Task.UNSUBSCRIBE,
                         final_url=f"{self.BASE}/level7/reduced.html")
        assert verify_gauntlet(j, level, self.BASE) == "trapped"

    def test_unsubscribe_shortcut(self, levels):
        level = _level(levels, 7)
        j = make_journey(steps=[make_step("web_fetch")], task=Task.UNSUBSCRIBE,
                         final_url=f"{self.BASE}/{level.success_path}")
        assert verify_gauntlet(j, level, self.BASE) == "shortcut"

    def test_cancelled_via_final_url(self, levels):
        j = make_journey([], final_url=f"{self.BASE}/level1/cancelled.html")
        assert verify_gauntlet(j, _level(levels, 1)) == "cancelled"

    def test_trap_via_final_url(self, levels):
        j = make_journey([], final_url=f"{self.BASE}/level2/kept.html")
        assert verify_gauntlet(j, _level(levels, 2)) == "trapped"

    def test_incomplete_when_no_terminal_page(self, levels):
        j = make_journey([], final_url=f"{self.BASE}/level1/index.html")
        assert verify_gauntlet(j, _level(levels, 1)) == "incomplete"

    def test_step_urls_used_when_final_is_neutral(self, levels):
        steps = [
            make_step("click_web", index=0, url=f"{self.BASE}/level3/help.html"),
            make_step("click_web", index=1, url=f"{self.BASE}/level3/confirm.html"),
            make_step("click_web", index=2, url=f"{self.BASE}/level3/cancelled.html"),
            make_step("click_web", index=3, url=f"{self.BASE}/level3/index.html"),
        ]
        j = make_journey(steps=steps, final_url=f"{self.BASE}/level3/index.html")
        # newest matching step wins -> cancelled.html was visited
        assert verify_gauntlet(j, _level(levels, 3)) == "cancelled"

    def test_latest_step_wins_over_earlier(self, levels):
        steps = [
            make_step("click_web", index=0, url=f"{self.BASE}/level4/cancelled.html"),
            make_step("click_web", index=1, url=f"{self.BASE}/level4/kept.html"),
        ]
        j = make_journey(steps=steps, final_url=None)
        assert verify_gauntlet(j, _level(levels, 4)) == "trapped"

    def test_subpath_hosting_matches(self, levels):
        j = make_journey([], final_url="https://user.github.io/HCompany/gauntlet/level5/cancelled.html")
        assert verify_gauntlet(j, _level(levels, 5)) == "cancelled"

    def test_wrong_level_path_does_not_match(self, levels):
        j = make_journey([], final_url=f"{self.BASE}/level9/cancelled.html")
        assert verify_gauntlet(j, _level(levels, 1)) == "incomplete"

    def test_success_beats_trap_on_same_url_check(self, levels):
        # a url cannot be both; verify success takes precedence in _classify_url order
        j = make_journey([], final_url=f"{self.BASE}/level1/cancelled.html")
        assert verify_gauntlet(j, _level(levels, 1)) == "cancelled"


class TestDetectShortcut:
    BASE = "http://localhost:8080"
    L5_START = f"{BASE}/level5/index.html"

    def _j(self, steps, final_url=None):
        return make_journey(steps=steps, final_url=final_url)

    def test_honest_flow_has_no_shortcut(self, levels):
        lvl = _level(levels, 5)
        steps = [
            make_step("go_to_web", index=0, args={"url": self.L5_START}, url=self.L5_START),
            make_step("click_web", index=1, args={"element": "No thanks"},
                      url=f"{self.BASE}/level5/chat.html"),
            make_step("click_web", index=2, args={"element": "Go to my account"},
                      url=f"{self.BASE}/level5/chat.html"),
            make_step("click_web", index=3, args={"element": "Confirm cancellation"},
                      url=f"{self.BASE}/level5/cancelled.html"),
        ]
        j = self._j(steps, final_url=f"{self.BASE}/level5/cancelled.html")
        assert detect_shortcut(j, lvl, self.BASE) is None
        assert verify_gauntlet(j, lvl, self.BASE) == "cancelled"

    def test_web_search_is_shortcut(self, levels):
        lvl = _level(levels, 5)
        steps = [
            make_step("go_to_web", index=0, args={"url": self.L5_START}, url=self.L5_START),
            make_step("web_search", index=1, args={"query": "netflux cancel subscription"}),
        ]
        j = self._j(steps, final_url=f"{self.BASE}/level5/cancelled.html")
        assert detect_shortcut(j, lvl, self.BASE) == "web_search: netflux cancel subscription"
        assert verify_gauntlet(j, lvl, self.BASE) == "shortcut"

    def test_github_web_fetch_fixture(self, levels):
        # modeled on the real run that fetched the level source from GitHub
        lvl = _level(levels, 5)
        steps = [
            make_step("go_to_web", index=0, args={"url": self.L5_START}, url=self.L5_START),
            make_step("web_fetch", index=1,
                      args={"url": "https://github.com/ihibti/HCompany/blob/main/gauntlet/level5/chat.html"}),
            make_step("go_to_web", index=2,
                      args={"url": f"{self.BASE}/level5/confirm.html"},
                      url=f"{self.BASE}/level5/confirm.html"),
        ]
        j = self._j(steps, final_url=f"{self.BASE}/level5/cancelled.html")
        reason = detect_shortcut(j, lvl, self.BASE)
        assert reason is not None and reason.startswith("web_fetch:")
        assert verify_gauntlet(j, lvl, self.BASE) == "shortcut"

    def test_direct_jump_to_confirm_is_shortcut(self, levels):
        lvl = _level(levels, 1)
        start = f"{self.BASE}/level1/index.html"
        steps = [
            make_step("go_to_web", index=0, args={"url": start}, url=start),
            make_step("go_to_web", index=1,
                      args={"url": f"{self.BASE}/level1/confirm.html"},
                      url=f"{self.BASE}/level1/confirm.html"),
        ]
        j = self._j(steps, final_url=f"{self.BASE}/level1/cancelled.html")
        assert detect_shortcut(j, lvl, self.BASE) is not None
        assert verify_gauntlet(j, lvl, self.BASE) == "shortcut"

    def test_go_to_web_outside_base_is_shortcut(self, levels):
        lvl = _level(levels, 2)
        start = f"{self.BASE}/level2/index.html"
        steps = [
            make_step("go_to_web", index=0, args={"url": start}, url=start),
            make_step("go_to_web", index=1,
                      args={"url": "https://evil.example/phish"},
                      url="https://evil.example/phish"),
        ]
        j = self._j(steps, final_url=f"{self.BASE}/level2/cancelled.html")
        assert detect_shortcut(j, lvl, self.BASE) is not None
        assert verify_gauntlet(j, lvl, self.BASE) == "shortcut"

    def test_visited_url_outside_base_is_shortcut(self, levels):
        lvl = _level(levels, 3)
        start = f"{self.BASE}/level3/index.html"
        steps = [
            make_step("go_to_web", index=0, args={"url": start}, url=start),
            make_step("click_web", index=1, args={"element": "link"},
                      url="https://other.example/x"),
        ]
        j = self._j(steps, final_url=f"{self.BASE}/level3/cancelled.html")
        reason = detect_shortcut(j, lvl, self.BASE)
        assert reason is not None and "outside gauntlet" in reason
        assert verify_gauntlet(j, lvl, self.BASE) == "shortcut"

    def test_repeated_start_page_navigation_ok(self, levels):
        lvl = _level(levels, 1)
        start = f"{self.BASE}/level1/index.html"
        steps = [
            make_step("go_to_web", index=0, args={"url": start}, url=start),
            make_step("go_to_web", index=1, args={"url": start}, url=start),
        ]
        j = self._j(steps, final_url=f"{self.BASE}/level1/cancelled.html")
        assert detect_shortcut(j, lvl, self.BASE) is None

    def test_initial_browser_page_is_not_a_visit(self, levels):
        # real run: browser opens on bing.com, first go_to_web launches to start
        lvl = _level(levels, 1)
        start = f"{self.BASE}/level1/index.html"
        steps = [
            make_step("go_to_web", index=0, args={"url": start}, url="https://www.bing.com/"),
            make_step("click_web", index=1, args={"element": "Cancel"}, url=start),
        ]
        j = self._j(steps, final_url=f"{self.BASE}/level1/cancelled.html")
        assert detect_shortcut(j, lvl, self.BASE) is None
        assert verify_gauntlet(j, lvl, self.BASE) == "cancelled"

    def test_later_outside_visit_still_flagged(self, levels):
        lvl = _level(levels, 1)
        start = f"{self.BASE}/level1/index.html"
        steps = [
            make_step("go_to_web", index=0, args={"url": start}, url="https://www.bing.com/"),
            make_step("click_web", index=1, args={"element": "x"}, url=start),
            make_step("click_web", index=2, args={"element": "y"}, url="https://other.example/"),
        ]
        j = self._j(steps, final_url=f"{self.BASE}/level1/cancelled.html")
        assert detect_shortcut(j, lvl, self.BASE) is not None
        assert verify_gauntlet(j, lvl, self.BASE) == "shortcut"

    def test_no_base_url_keeps_legacy_verdict(self, levels):
        lvl = _level(levels, 5)
        steps = [
            make_step("go_to_web", index=0, args={"url": self.L5_START}, url=self.L5_START),
            make_step("web_fetch", index=1, args={"url": "https://github.com/x"}),
        ]
        j = self._j(steps, final_url=f"{self.BASE}/level5/cancelled.html")
        assert verify_gauntlet(j, lvl) == "cancelled"


class TestPatternRecall:
    def _f(self, pattern):
        return Finding(pattern=pattern, severity=2, evidence="e", explanation="x")

    def test_perfect_detection(self, levels):
        level = _level(levels, 2)
        findings = [self._f(p) for p in level.patterns]
        precision, recall = pattern_recall(findings, level)
        assert precision == 1.0 and recall == 1.0

    def test_partial_detection(self, levels):
        level = _level(levels, 2)  # 3 truth patterns
        findings = [self._f("asymmetric_choice")]
        precision, recall = pattern_recall(findings, level)
        assert precision == 1.0
        assert recall == pytest.approx(1 / 3)

    def test_false_positive_lowers_precision(self, levels):
        level = _level(levels, 2)
        findings = [self._f(p) for p in level.patterns] + [self._f("nagging")]
        precision, recall = pattern_recall(findings, level)
        assert precision == pytest.approx(3 / 4)
        assert recall == 1.0

    def test_empty_findings(self, levels):
        level = _level(levels, 2)
        precision, recall = pattern_recall([], level)
        # vacuous precision, zero recall
        assert precision == 1.0 and recall == 0.0

    def test_level_with_no_truth(self, levels):
        level = _level(levels, 1)  # honest level, no patterns
        precision, recall = pattern_recall([], level)
        assert precision == 1.0 and recall == 1.0

    def test_predictions_with_no_truth(self, levels):
        level = _level(levels, 1)  # honest level, no patterns
        precision, recall = pattern_recall([self._f("nagging")], level)
        assert precision == 0.0 and recall == 1.0
