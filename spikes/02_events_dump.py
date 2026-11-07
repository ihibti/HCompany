"""Spike 2: dump session events, verify shapes, download screenshots.

Usage: uv run python spikes/02_events_dump.py <session_id> [<session_id2> ...]
Writes spikes/out/02_events_<sid8>.json and downloads up to 2 screenshots
into spikes/out/screenshots/.
"""

import sys
from collections import Counter
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))
from common import OUT_DIR, dump_events, get_client, save_json

SCREEN_DIR = OUT_DIR / "screenshots"
SCREEN_DIR.mkdir(exist_ok=True)


def analyze(session_id: str) -> None:
    client = get_client()
    events = []
    page = 1
    while True:
        p = client.sessions.list_session_events(session_id, page=page, size=200)
        events.extend(p.items)
        if page * 200 >= (p.total or 0):
            break
        page += 1

    dicts = dump_events(events)
    save_json(f"02_events_{session_id[:8]}.json", dicts)

    kinds = Counter()
    tool_names = Counter()
    obs_types = Counter()
    urls = []
    image_sources = []
    metrics = None
    live_view = None

    for e in dicts:
        t = e.get("type")
        kinds[t] += 1
        if t == "AgentEvent":
            d = e.get("data") or {}
            k = d.get("kind")
            kinds[f"AgentEvent/{k}"] += 1
            if k == "observation_event":
                obs_types[d.get("type")] += 1
                md = d.get("metadata") or {}
                if md.get("url"):
                    urls.append(md["url"])
                img = d.get("image") or {}
                if img.get("source"):
                    image_sources.append(img["source"])
            elif k == "policy_event":
                for tr in d.get("tool_reqs") or []:
                    tool_names[tr.get("tool_name")] += 1
        elif t == "MetricsUpdateEvent":
            metrics = (e.get("data") or {}).get("metrics")
        elif t == "LiveViewUrlEvent":
            live_view = (e.get("data") or {}).get("live_view_url")

    print(f"session {session_id}: {len(dicts)} events")
    print("event types:", dict(kinds))
    print("observation types:", dict(obs_types))
    print("tool names:", dict(tool_names))
    print("unique page urls:", sorted(set(urls))[:20])
    print(f"image sources: {len(image_sources)}")
    print("metrics:", metrics)
    print("live_view_url:", live_view)

    # Try downloading 2 screenshots: first without auth, then with auth.
    for i, src in enumerate(image_sources[:2]):
        for label, headers in (("noauth", {}), ("auth", {"Authorization": f"Bearer {__import__('os').environ.get('HAI_API_KEY','')}"})):
            try:
                r = httpx.get(src, headers=headers, follow_redirects=True, timeout=30)
                print(f"img{i} {label}: HTTP {r.status_code}, {len(r.content)} bytes, content-type={r.headers.get('content-type')}")
                if r.status_code == 200 and r.content[:8] == b"\x89PNG\r\n\x1a\n":
                    (SCREEN_DIR / f"{session_id[:8]}_step{i}.png").write_bytes(r.content)
                    print(f"  saved {SCREEN_DIR}/{session_id[:8]}_step{i}.png")
                    break
            except Exception as ex:
                print(f"img{i} {label}: ERROR {type(ex).__name__} {ex}")


if __name__ == "__main__":
    for sid in sys.argv[1:]:
        analyze(sid)
