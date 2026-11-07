import io
from datetime import datetime, timezone

from PIL import Image

from escapehatch.models import Audit, Finding, Outcome, Score, Effort
from escapehatch.prompts import Task
from escapehatch.store import RunStore

from conftest import make_journey


def _png(width=400, height=300, color=(200, 30, 30)) -> bytes:
    img = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _audit(aid="run-1") -> Audit:
    leave = make_journey(["click_web", "click_web"], outcome=Outcome.SUCCESS)
    return Audit(
        id=aid,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        site_url="https://example.com",
        task=Task.CANCEL_SUBSCRIPTION,
        leave=leave,
        findings=[Finding(pattern="nagging", severity=1, evidence="e", explanation="x")],
        score=Score(
            leave_effort=Effort(interactions=2, navigations=0, detours=0, total=2),
            enter_effort=None,
            asymmetry_ratio=None,
            pattern_points=4,
            friction=10,
            grade="A",
            headline="Leaving takes 2 actions.",
        ),
        legal=[],
    )


def test_audit_roundtrip(tmp_path):
    store = RunStore(tmp_path)
    audit = _audit()
    path = store.save_audit(audit)
    assert path.name == "audit.json"
    loaded = store.load_audit("run-1")
    assert loaded.id == "run-1"
    assert loaded.leave.steps[0].action == "click_web"
    assert loaded.findings[0].pattern == "nagging"
    assert loaded.score.grade == "A"


def test_events_roundtrip(tmp_path):
    store = RunStore(tmp_path)
    events = [{"type": "AgentEvent", "data": {"kind": "x"}}]
    store.save_events("run-1", "leave", events)
    store.save_events("run-1", "enter", [{"type": "Other"}])
    assert store.load_events("run-1", "leave") == events
    assert store.load_events("run-1", "enter") == [{"type": "Other"}]


def test_list_audits(tmp_path):
    store = RunStore(tmp_path)
    store.save_audit(_audit("b-run"))
    store.save_audit(_audit("a-run"))
    # not an audit dir: no audit.json inside
    (tmp_path / "shots").mkdir(exist_ok=True)
    ids = store.list_audits()
    assert set(ids) == {"a-run", "b-run"}


def test_screenshot_downscale_and_lookup(tmp_path):
    store = RunStore(tmp_path)
    url = "https://platform.example/shots/abc.png"
    path = store.save_screenshot(url, _png(width=1800, height=900))
    assert path.suffix == ".jpg"
    with Image.open(path) as img:
        assert img.width == 900
        assert img.height == 450
        assert img.format == "JPEG"
    assert store.local_shot(url) == path
    assert store.local_shot("https://other/none.png") is None
    assert store.local_shot(None) is None


def test_screenshot_small_image_kept(tmp_path):
    store = RunStore(tmp_path)
    url = "https://x/small.png"
    path = store.save_screenshot(url, _png(width=300, height=200))
    with Image.open(path) as img:
        assert img.width == 300
