"""Spike 3: LiveViewUrlEvent — extract live_view_url and check iframe embeddability.

Usage: uv run python spikes/03_liveview.py <session_id>
Prints the URL and curl-equivalent header check (X-Frame-Options, CSP frame-ancestors).
"""

import os
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))
from common import get_client, save_json


def find_live_view(session_id: str) -> str | None:
    client = get_client()
    page = 1
    while True:
        p = client.sessions.list_session_events(session_id, page=page, size=200)
        for e in p.items:
            d = e.model_dump(mode="json") if hasattr(e, "model_dump") else e
            if d.get("type") == "LiveViewUrlEvent":
                return (d.get("data") or {}).get("live_view_url")
        if page * 200 >= (p.total or 0):
            break
        page += 1
    return None


def main(session_id: str) -> None:
    url = find_live_view(session_id)
    print("live_view_url:", url)
    if not url:
        return
    save_json("03_liveview.json", {"session_id": session_id, "live_view_url": url})
    headers = {
        "x-frame-options": None,
        "content-security-policy": None,
        "content-security-policy-report-only": None,
    }
    try:
        # GET with stream so we can inspect headers without downloading the body.
        with httpx.stream("GET", url, timeout=30, follow_redirects=True) as r:
            for k in headers:
                headers[k] = r.headers.get(k)
            print("final URL after redirects:", str(r.url))
            print("status:", r.status_code)
    except Exception as ex:
        print("request error:", type(ex).__name__, ex)
    for k, v in headers.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main(sys.argv[1])
