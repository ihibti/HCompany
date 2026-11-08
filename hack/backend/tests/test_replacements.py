import pytest

pytestmark = pytest.mark.asyncio

from app.core import replacements as R  # noqa: E402
from app.models import TopicProfile, Verdict  # noqa: E402


@pytest.fixture(autouse=True)
def clean(tmp_path):
    from app.config import get_settings
    s = get_settings()
    object.__setattr__(s, "data_dir", tmp_path)
    object.__setattr__(s, "fake_ai", False)
    R.POOLS.clear(); R.SERVED.clear(); R.BUILDING.clear()


P = TopicProfile(id="p1", summary="escalade",
                 include=[{"topic": "escalade", "keywords": ["bloc"], "example_creators": []}],
                 exclude=[], languages=["fr"])


def test_normalize_id():
    assert R.normalize_id("youtube", "https://www.youtube.com/watch?v=abc123X") == ("abc123X", "video")
    assert R.normalize_id("youtube_shorts", "https://youtube.com/shorts/zz99ab") == ("zz99ab", "short")
    assert R.normalize_id("tiktok", "https://tiktok.com/@u/video/1234567890") == ("1234567890", "video")
    assert R.normalize_id("instagram", "https://instagram.com/reel/Cxyz/") == ("Cxyz", "short")
    assert R.normalize_id("youtube", "https://tiktok.com/@u/video/1234567890") is None


async def test_pool_enrich_gate_dedupe(monkeypatch):
    class _C:
        videos = [
            {"url": "https://youtube.com/watch?v=good01", "title": "t", "channel": "c"},
            {"url": "https://youtube.com/watch?v=dead01", "title": "t", "channel": "c"},
            {"url": "https://tiktok.com/@x/video/1234567890", "title": "wrong platform", "channel": "x"},
            {"url": "https://youtube.com/watch?v=weak01", "title": "t", "channel": "c"},
        ]

    async def fake_oembed(platform, url, http=None):
        if "dead01" in url:
            return None
        return {"title": "Real", "channel": "Real", "thumbnail_url": "u"}
    monkeypatch.setattr(R, "_oembed", fake_oembed)

    async def fake_classify(metas, profile):
        return [Verdict(id=m.id, verdict="on" if m.id != "weak01" else "unsure",
                        confidence=0.9 if m.id != "weak01" else 0.4, reason="ok")
                for m in metas]
    monkeypatch.setattr(R, "classify", fake_classify)

    items = await R._collect(P, "youtube", linkup_fn=lambda *a, **k: (_C(), []))
    assert [i["id"] for i in items] == ["good01", "weak01"]  # dead01 dropped, wrong-platform filtered
    on = await R._filter_on_topic(P, items)
    assert [i["id"] for i in on] == ["good01"]  # unsure/low-conf gated out
    R.POOLS["p1|youtube"] = on
    got = await R.get_replacements(P, "youtube", [], 5)
    assert [g["id"] for g in got] == ["good01"]
    got2 = await R.get_replacements(P, "youtube", [], 5)
    assert all(g["id"] != "good01" for g in got2)  # never served twice
