import asyncio
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

pytestmark = pytest.mark.asyncio

from app import store  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.core import h_jobs  # noqa: E402
from app.core.classify import _VerdictBatch, classify  # noqa: E402
from app.core.profile import build_profile  # noqa: E402
from app.main import app  # noqa: E402
from app.models import TopicProfile, VideoMeta  # noqa: E402


@pytest.fixture(autouse=True)
def tmp_data(tmp_path, monkeypatch):
    s = get_settings()
    object.__setattr__(s, "data_dir", tmp_path)
    object.__setattr__(s, "fake_ai", False)
    yield


PROFILE = TopicProfile(
    id="p1", raw_text="escalade et cuisine japonaise, pas de drama ni gaming",
    summary="Escalade et cuisine japonaise uniquement.",
    include=[{"topic": "escalade", "keywords": ["bloc", "grimpe"], "example_creators": []},
             {"topic": "cuisine japonaise", "keywords": ["ramen", "sushi"], "example_creators": []}],
    exclude=[{"topic": "drama", "keywords": ["drama"]}, {"topic": "gaming", "keywords": ["gaming"]}],
    languages=["fr"])


def v(i, title, platform="youtube"):
    return VideoMeta(platform=platform, id=i, url=f"https://x/{i}", title=title, channel="ch")


def holo_returns(batch):
    """fake holo_fn returning verdicts by title keywords; records calls."""
    calls = []

    def fn(schema, messages):
        calls.append(messages)
        user = messages[-1]["content"]
        items = []
        for line in user.split("VIDÉOS:\n")[1].splitlines():
            vid = line.split("|")[0].replace("id=", "").strip()
            if "escalade" in line or "ramen" in line:
                items.append({"id": vid, "verdict": "on", "confidence": 0.95, "reason": "dans le sujet"})
            elif "fortnite" in line or "drama" in line:
                items.append({"id": vid, "verdict": "off", "confidence": 0.95, "reason": "hors sujet"})
            else:
                items.append({"id": vid, "verdict": "unsure", "confidence": 0.4, "reason": "flou"})
        return _VerdictBatch(verdicts=items)
    fn.calls = calls
    return fn


async def test_classify_batching_and_cache():
    videos = [v(f"v{i}", "escalade") for i in range(25)]
    holo = holo_returns(None)
    out = await classify(videos, PROFILE, holo_fn=holo, linkup_fn=lambda q: [])
    assert len(out) == 25 and all(x.verdict == "on" for x in out)
    assert len(holo.calls) == 4  # 25 videos -> 4 chunks of 8
    # second call fully cached
    out2 = await classify(videos, PROFILE, holo_fn=holo, linkup_fn=lambda q: [])
    assert len(holo.calls) == 4


async def test_classify_no_linkup_and_refine_parallel():
    import time as _t
    from app.core.classify import refine
    videos = [v("u1", "titre bizarre"), v("o1", "drama")]
    holo = holo_returns(None)
    out = await classify(videos, PROFILE, holo_fn=holo, linkup_fn=lambda q: [])
    assert len(holo.calls) == 1  # no refine inside classify anymore
    link_calls = []

    def fake_linkup(q):
        link_calls.append(q)
        _t.sleep(0.2)
        return [{"name": "x", "url": "u", "content": "cette vidéo parle de cuisine japonaise"}]

    t0 = _t.time()
    out2 = await refine([v("u1", "titre bizarre"), v("u2", "mystère 2")], PROFILE, holo_fn=holo, linkup_fn=fake_linkup)
    assert len(link_calls) == 2
    assert _t.time() - t0 < 0.4  # parallel: ~max not ~sum
    assert "CONTEXTE WEB" in holo.calls[-1][-1]["content"]


async def test_feedback_fewshot_and_cache_invalidate():
    from app import store
    from app.main import app as fastapi_app
    holo = holo_returns(None)
    await classify([v("x1", "mystère")], PROFILE, holo_fn=holo, linkup_fn=lambda q: [])
    assert store.cache_get("p1", "youtube", "x1")
    client = TestClient(fastapi_app)
    store.save_profile(PROFILE)
    r = client.post("/feedback", json={
        "profile_id": "p1", "action": "tomato",
        "video": {"id": "x1", "platform": "youtube", "title": "mystère", "url": "u"}})
    assert r.status_code == 200
    assert store.cache_get("p1", "youtube", "x1") is None
    await classify([v("x2", "mystère2")], PROFILE, holo_fn=holo, linkup_fn=lambda q: [])
    assert "EXEMPLES DE L'UTILISATEUR" in holo.calls[-1][-1]["content"]
    assert "mystère" in holo.calls[-1][-1]["content"]


async def test_profile_merges_linkup():
    class _P(BaseModel):
        summary: str = ""
        include: list[dict] = []
        exclude: list[dict] = []
        languages: list[str] = ["fr"]

    class _E(BaseModel):
        keywords: list[str] = []
        creators: list[dict] = []

    def fake_holo(schema, messages):
        return _P(summary="Escalade.", include=[{"topic": "escalade", "keywords": ["bloc"]}],
                  exclude=[{"topic": "gaming", "keywords": ["jeux"]}], languages=["fr"])

    def fake_linkup(q, schema, depth="standard"):
        return _E(keywords=["grimpe", "boulder"], creators=[{"name": "GrimpeurFR", "platform": "youtube"}]), \
               [{"name": "src", "url": "https://s"}]

    p = await build_profile("je veux de l'escalade", holo_fn=fake_holo, linkup_fn=fake_linkup)
    assert p.include[0].topic == "escalade"
    assert "grimpe" in p.include[0].keywords and "bloc" in p.include[0].keywords
    assert p.include[0].example_creators == ["GrimpeurFR"]
    assert p.sources == [{"name": "src", "url": "https://s"}]


async def test_job_queue_serializes_and_exposes_url(monkeypatch):
    order = []

    async def fake_session(instruction, schema, job):
        job.agent_view_url = f"https://view/{job.id}"
        order.append(("start", job.id))
        await asyncio.sleep(0.05)
        job.status = "completed"
        order.append(("end", job.id))
        return schema()

    monkeypatch.setattr(h_jobs, "SESSION_FACTORY", fake_session)
    worker = asyncio.create_task(h_jobs.worker())
    j1 = h_jobs.enqueue("scout", "tiktok", "p1", {"count": 3, "profile": {}})
    j2 = h_jobs.enqueue("scout", "tiktok", "p1", {"count": 3, "profile": {}})
    while order.count(("end", j1.id)) == 0:
        await asyncio.sleep(0.01)
        assert j1.agent_view_url  # visible while running
    while order.count(("end", j2.id)) == 0:
        await asyncio.sleep(0.01)
    worker.cancel()
    # serialized: j1 ended before j2 started
    assert order.index(("end", j1.id)) < order.index(("start", j2.id))
    assert h_jobs.JOBS[j1.id].status == "completed"


def test_health_no_secrets(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("HAI_API_KEY", "sekrit-value-123")
    get_settings.cache_clear()
    r = TestClient(app).get("/health")
    assert r.status_code == 200
    assert "sekrit" not in json.dumps(r.json())
    get_settings.cache_clear()

def test_train_instruction_consent():
    from app.core.h_jobs import Job, build_instruction
    job = Job(id="j", kind="train", platform="youtube", profile_id="p", created_at=0,
              payload={"profile": {"summary": "escalade", "include": [{"topic": "escalade"}]},
                       "videos": [], "actions": {"not_interested": True, "search_watch": False, "like": False}})
    instr, schema = build_instruction(job)
    assert "Pas intéressé" in instr
    assert "recherche" not in instr and "aime" not in instr  # disabled actions omitted
    assert "s'abonner" in instr and "INTERDIT" in instr  # only in prohibition
    # 'Ne pas recommander la chaîne' only inside interdiction lines
    for line in instr.split("\\n"):
        if "Ne pas recommander la chaîne" in line:
            assert "jamais" in line or "INTERDIT" in line
    job2 = Job(id="j2", kind="train", platform="youtube", profile_id="p", created_at=0,
               payload={"profile": {"summary": "x", "include": []}, "videos": [],
                        "actions": {"not_interested": False, "search_watch": True, "like": True}})
    instr2, _ = build_instruction(job2)
    assert "Pas intéressé" not in instr2.split("INTERDIT")[0]
