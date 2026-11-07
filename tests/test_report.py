import json
from datetime import datetime, timezone

from escapehatch.legal import applicable_refs
from escapehatch.models import Audit, Finding, Outcome
from escapehatch.prompts import Task
from escapehatch.report import audit_to_json, render_report_html
from escapehatch.scoring import score

from conftest import make_journey, make_step


def _audit(with_enter=False, with_findings=True) -> Audit:
    leave_steps = [
        make_step("go_to_web", index=0, args={"url": "https://site.example"},
                  element=None, url="https://site.example/", screenshot_url="https://shots/0.png"),
        make_step("click_web", index=1, args={"x": 10, "y": 20, "element": "Manage plan"},
                  element="Manage plan", reasoning="need to find cancel",
                  url="https://site.example/account", screenshot_url="https://shots/1.png"),
        make_step("click_web", index=2, args={"x": 5, "y": 5, "element": "Confirm cancellation"},
                  element="Confirm cancellation", url="https://site.example/cancelled",
                  screenshot_url=None),
    ]
    leave = make_journey(steps=leave_steps, final_url="https://site.example/cancelled",
                         final_screenshot_url="https://shots/final.png")
    enter = None
    if with_enter:
        enter = make_journey(["click_web"], task=Task.SUBSCRIBE,
                             final_url="https://site.example/welcome")
    findings = [
        Finding(pattern="asymmetric_choice", severity=2,
                evidence="'No thanks, I enjoy paying full price'",
                explanation="Refusal is a small grey link.",
                step_index=1, screenshot_url="https://shots/1.png"),
    ] if with_findings else []
    sc = score(leave, enter, findings)
    return Audit(
        id="audit-test",
        created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        site_url="https://site.example",
        task=Task.CANCEL_SUBSCRIPTION,
        leave=leave,
        enter=enter,
        findings=findings,
        score=sc,
        legal=applicable_refs(Task.CANCEL_SUBSCRIPTION, [f.pattern for f in findings]),
    )


def _resolver(url):
    return f"/local/{url.rsplit('/', 1)[-1]}" if url else None


def test_render_without_enter():
    html = render_report_html(_audit(with_enter=False), _resolver)
    assert "Escape" in html and "Hatch" in html
    assert ">C<" in html or ">B<" in html or ">A<" in html or ">D<" in html or ">F<" in html
    assert "asymmetric choice" in html
    assert "No thanks, I enjoy paying full price" in html
    assert "Confirm cancellation" in html  # step element
    assert "L215-1-1" in html  # legal code
    assert "/local/1.png" in html  # resolved screenshot
    assert "no screenshot" in html  # step 2 had None


def test_render_with_enter_shows_comparison():
    html = render_report_html(_audit(with_enter=True), _resolver)
    assert "Leave" in html and "Enter" in html
    assert "Subscribing takes 1." in html


def test_render_no_findings_and_no_screenshots():
    audit = _audit(with_enter=False, with_findings=False)
    html = render_report_html(audit, lambda url: None)
    assert "No dark patterns flagged" in html
    assert "no screenshot" in html


def test_render_impossible_grade_f():
    leave = make_journey([], outcome=Outcome.IMPOSSIBLE)
    audit = Audit(
        id="a2", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        site_url="https://wall.example", task=Task.REFUSE_COOKIES,
        leave=leave, findings=[], score=score(leave, None, []),
        legal=applicable_refs(Task.REFUSE_COOKIES, []),
    )
    html = render_report_html(audit, _resolver)
    assert ">F<" in html
    assert "impossible" in html.lower()


def test_audit_json_roundtrip():
    audit = _audit(with_enter=True)
    raw = audit_to_json(audit)
    data = json.loads(raw)
    assert data["score"]["grade"] in {"A", "B", "C", "D", "F", "N/A", "?"}
    assert data["legal"][0]["code"]
    # legal dataclass serializes to plain dicts
    assert isinstance(data["legal"][0], dict)
