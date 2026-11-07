import json
from types import SimpleNamespace

import pytest

from escapehatch.models import Finding
from escapehatch.patterns import classify_step, merge_findings, select_key_steps
from escapehatch.prompts import PATTERN_DEFINITIONS, Task

from conftest import make_journey, make_step


def _finding(pattern, severity, evidence="ev", explanation="ex", step_index=None, screenshot_url=None):
    return Finding(
        pattern=pattern,
        severity=severity,
        evidence=evidence,
        explanation=explanation,
        step_index=step_index,
        screenshot_url=screenshot_url,
    )


class TestSelectKeySteps:
    def test_keeps_interaction_and_navigation_steps_with_unique_shots(self):
        steps = [
            make_step("click_web", index=0, screenshot_url="s1"),
            make_step("scroll_web", index=1, screenshot_url="s2"),   # other: excluded
            make_step("click_web", index=2, screenshot_url="s1"),   # dup shot: excluded
            make_step("go_to_web", index=3, screenshot_url="s3"),
            make_step("wait_web", index=4, screenshot_url=None),     # no shot: excluded
        ]
        j = make_journey(steps=steps, final_screenshot_url="s4")
        key = select_key_steps(j)
        assert [s.screenshot_url for s in key] == ["s1", "s3", "s4"]

    def test_final_screenshot_appended_when_new(self):
        steps = [make_step("click_web", index=0, screenshot_url="s1")]
        j = make_journey(steps=steps, final_screenshot_url="s1")  # same -> not duplicated
        assert [s.screenshot_url for s in select_key_steps(j)] == ["s1"]
        j2 = make_journey(steps=steps, final_screenshot_url="s9")
        assert [s.screenshot_url for s in select_key_steps(j2)] == ["s1", "s9"]

    def test_cap_keeps_first_and_last_and_samples_evenly(self):
        steps = [
            make_step("click_web", index=i, screenshot_url=f"s{i}") for i in range(10)
        ]
        j = make_journey(steps=steps, final_screenshot_url=None)
        key = select_key_steps(j, max_shots=4)
        urls = [s.screenshot_url for s in key]
        assert len(key) == 4
        assert urls[0] == "s0"
        assert urls[-1] == "s9"
        # evenly spaced interior picks
        assert urls[1:-1] == sorted(urls[1:-1])

    def test_under_cap_returns_all(self):
        steps = [make_step("click_web", index=i, screenshot_url=f"s{i}") for i in range(3)]
        j = make_journey(steps=steps)
        assert len(select_key_steps(j, max_shots=6)) == 3


class TestMergeFindings:
    def test_keeps_strongest_severity_per_pattern(self):
        per_shot = [
            [_finding("asymmetric_choice", 1, evidence="weak"), _finding("nagging", 2)],
            [_finding("asymmetric_choice", 3, evidence="strong")],
        ]
        merged = merge_findings(per_shot)
        by_pattern = {f.pattern: f for f in merged}
        assert by_pattern["asymmetric_choice"].severity == 3
        assert by_pattern["asymmetric_choice"].evidence == "strong"
        assert by_pattern["nagging"].severity == 2

    def test_sorted_by_severity_desc_then_pattern(self):
        per_shot = [[_finding("trick_question", 1), _finding("nagging", 3), _finding("hidden_option", 3)]]
        merged = merge_findings(per_shot)
        assert [(f.pattern, f.severity) for f in merged] == [
            ("hidden_option", 3),
            ("nagging", 3),
            ("trick_question", 1),
        ]

    def test_empty(self):
        assert merge_findings([]) == []
        assert merge_findings([[]]) == []


class _FakeCompletions:
    def __init__(self, content: str):
        self._content = content
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self._content))]
        )


class _FakeChat:
    def __init__(self, content: str):
        self.completions = _FakeCompletions(content)


class FakeClient:
    def __init__(self, content: str):
        self.chat = _FakeChat(content)


@pytest.mark.asyncio
async def test_classify_step_parses_findings_and_drops_invalid():
    payload = {
        "findings": [
            {"pattern": "asymmetric_choice", "severity": 2, "evidence": "small grey link", "explanation": "refuse is a text link"},
            {"pattern": "not_a_real_pattern", "severity": 3, "evidence": "x", "explanation": "y"},
            {"pattern": "nagging", "severity": 9, "evidence": "x", "explanation": "y"},
        ]
    }
    client = FakeClient(json.dumps(payload))
    findings = await classify_step(
        client, b"pngbytes", Task.CANCEL_SUBSCRIPTION, "https://x.test/manage",
        "clicked Manage plan", 4, "https://shot/4.png",
    )
    assert len(findings) == 1
    f = findings[0]
    assert f.pattern == "asymmetric_choice"
    assert f.severity == 2
    assert f.step_index == 4
    assert f.screenshot_url == "https://shot/4.png"

    # verify the wire schema constrains patterns to the taxonomy
    call = client.chat.completions.calls[0]
    schema = call["response_format"]["json_schema"]["schema"]
    item_props = schema["properties"]["findings"]["items"]["properties"]
    assert item_props["pattern"]["enum"] == list(PATTERN_DEFINITIONS)
    assert call["response_format"]["json_schema"]["strict"] is True
    # image is sent as a data URI
    user_msg = call["messages"][1]
    assert user_msg["content"][0]["type"] == "image_url"
    assert user_msg["content"][0]["image_url"]["url"].startswith("data:image/png;base64,")


@pytest.mark.asyncio
async def test_classify_step_invalid_json_returns_empty():
    client = FakeClient("not json at all")
    findings = await classify_step(client, b"x", Task.REFUSE_COOKIES, None, None, 0, None)
    assert findings == []


@pytest.mark.asyncio
async def test_classify_step_empty_findings():
    client = FakeClient('{"findings": []}')
    findings = await classify_step(client, b"x", Task.REFUSE_COOKIES, None, None, 0, None)
    assert findings == []
