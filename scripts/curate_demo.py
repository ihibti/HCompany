"""Curate demo_runs/: copy selected audits + download every journey screenshot.

Usage: set -a; source .env; set +a; uv run python scripts/curate_demo.py
"""

import asyncio
import json
import re
import shutil
from pathlib import Path

import httpx
from hai_agents import AsyncClient

from escapehatch.agent import fetch_screenshot
from escapehatch.models import Audit
from escapehatch.store import RunStore

RUNS = Path("runs")
DEMO = Path("demo_runs")

AUDIT_IDS = [
    # Netflux gauntlet L1-L5
    "20261107-220628-ihibti-github-io-cancel_subscription",
    "20261107-220717-ihibti-github-io-cancel_subscription",
    "20261107-220806-ihibti-github-io-cancel_subscription",
    "20261107-220915-ihibti-github-io-cancel_subscription",
    "20261107-221014-ihibti-github-io-cancel_subscription",
    # cookie audits (latest good runs)
    "20261107-222205-leboncoin-fr-refuse_cookies",
    "20261107-222250-marmiton-org-refuse_cookies",
    "20261107-222321-lefigaro-fr-refuse_cookies",
    "20261107-223407-doctissimo-fr-refuse_cookies",
    "20261107-223525-lemonde-fr-refuse_cookies",
    "20261107-223601-allocine-fr-refuse_cookies",
]


def shot_urls(audit: Audit) -> list[str]:
    urls: list[str] = []
    for journey in (audit.leave, audit.enter):
        if journey is None:
            continue
        for step in journey.steps:
            if step.screenshot_url:
                urls.append(step.screenshot_url)
        if journey.final_screenshot_url:
            urls.append(journey.final_screenshot_url)
    # dedupe, keep order
    seen = set()
    out = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


async def download(http: httpx.AsyncClient, client: AsyncClient, url: str) -> bytes:
    try:
        return await fetch_screenshot(http, url)
    except Exception:
        pass
    m = re.search(r"/trajectories/([^/]+)/resources/([^/]+)/(.+)$", url)
    if not m:
        raise RuntimeError(f"cannot parse resource url: {url[:80]}")
    sid, bucket, key = m.groups()
    chunks = []
    async for chunk in client.sessions.get_session_resource(sid, bucket, key):
        chunks.append(chunk)
    return b"".join(chunks)


async def main() -> None:
    src = RunStore(RUNS)
    demo = RunStore(DEMO)
    client = AsyncClient()
    http = httpx.AsyncClient(timeout=60)
    total_shots = 0
    failures = []

    for audit_id in AUDIT_IDS:
        src_dir = RUNS / audit_id
        if not (src_dir / "audit.json").exists():
            print(f"!! missing {audit_id}")
            continue
        audit = Audit.model_validate_json((src_dir / "audit.json").read_text())
        dst_dir = DEMO / audit_id
        dst_dir.mkdir(parents=True, exist_ok=True)
        for name in ("audit.json", "events_leave.json", "events_enter.json", "report.html"):
            p = src_dir / name
            if p.exists():
                shutil.copy2(p, dst_dir / name)

        urls = shot_urls(audit)
        ok = 0
        async with httpx.AsyncClient() as _:
            pass
        for url in urls:
            try:
                data = await download(http, client, url)
                demo.save_screenshot(url, data)
                ok += 1
            except Exception as e:
                failures.append((audit_id, url[:90], str(e)[:80]))
        total_shots += ok
        print(f"{audit_id}: {ok}/{len(urls)} shots")

    # merge benchmark JSONs: latest levels across files, one per agent
    bench_dir = DEMO / "benchmarks"
    bench_dir.mkdir(exist_ok=True)
    by_agent: dict[str, dict] = {}
    for bp in sorted((RUNS / "benchmarks").glob("*.json")):
        data = json.loads(bp.read_text())
        agent = data.get("agent", "?")
        cur = by_agent.setdefault(agent, {"created_at": "", "agent": agent,
                                          "base": data.get("base"), "levels": {}})
        for row in data.get("levels", []):
            lvl = row["level"]
            # keep the newest row per level
            cur["levels"][lvl] = row if row.get("wall_seconds", 0) >= \
                cur["levels"].get(lvl, {}).get("wall_seconds", -1) else cur["levels"].get(lvl)
        if data.get("created_at", "") > cur["created_at"]:
            cur["created_at"] = data["created_at"]
    for agent, cur in by_agent.items():
        levels = [cur["levels"][k] for k in sorted(cur["levels"])]
        out = {"created_at": cur["created_at"], "agent": agent,
               "base": cur["base"], "levels": levels}
        (bench_dir / f"{cur['created_at'][:8]}-{agent.replace('/', '-')}-demo.json").write_text(
            json.dumps(out, indent=2, ensure_ascii=False))
        print(f"benchmark {agent}: {len(levels)} levels")

    await client.aclose()
    await http.aclose()

    size = sum(f.stat().st_size for f in DEMO.rglob("*") if f.is_file())
    print(f"\ntotal shots ok={total_shots} failures={len(failures)}")
    print(f"demo_runs size: {size / 1e6:.1f} MB")
    for f in failures[:10]:
        print("FAIL", f)


if __name__ == "__main__":
    asyncio.run(main())
