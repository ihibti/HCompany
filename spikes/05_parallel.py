"""Spike 5: quotas + 3 parallel sessions.

Checks session quota and token quota, then runs 3 sessions concurrently
(lemonde.fr, leboncoin.fr, marmiton.org) with a minimal cookie-refusal task.
"""

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import dump_events, get_client, save_json

from hai_agents import AsyncClient

SITES = [
    ("lemonde", "https://www.lemonde.fr"),
    ("leboncoin", "https://www.leboncoin.fr"),
    ("marmiton", "https://www.marmiton.org"),
]

PROMPT = (
    "Go to {url} and refuse all non-essential cookies with the fewest clicks "
    "possible. Do not accept. Report each click you made in one sentence."
)


async def run_site(client: AsyncClient, name: str, url: str) -> dict:
    t0 = time.monotonic()
    try:
        result = await client.run_session(
            agent="h/web-surfer-flash",
            messages=PROMPT.format(url=url),
            max_steps=30,
            max_time_s=300,
        )
        wall = time.monotonic() - t0
        return {
            "site": name,
            "session_id": result.id,
            "status": str(result.status),
            "wall_seconds": round(wall, 1),
            "answer": result.answer if isinstance(result.answer, str) else str(result.answer),
            "event_count": len(result.events or []),
        }
    except Exception as ex:
        return {"site": name, "error": f"{type(ex).__name__}: {ex}", "wall_seconds": round(time.monotonic() - t0, 1)}


async def main() -> None:
    client = get_client()
    quota = client.sessions.get_session_quota()
    try:
        tokens = client.quota.get_token_quota()
        token_quota = tokens.model_dump(mode="json") if hasattr(tokens, "model_dump") else tokens
    except Exception as ex:
        token_quota = {"error": f"{type(ex).__name__}: {ex}"}
    session_quota = quota.model_dump(mode="json") if hasattr(quota, "model_dump") else quota
    print("session_quota:", session_quota)
    print("token_quota:", token_quota)
    save_json("05_quota.json", {"session_quota": session_quota, "token_quota": token_quota})

    async_client = AsyncClient()
    t0 = time.monotonic()
    results = await asyncio.gather(*(run_site(async_client, n, u) for n, u in SITES))
    total_wall = time.monotonic() - t0
    print(f"parallel wall: {total_wall:.1f}s")
    for r in results:
        print(json.dumps(r, ensure_ascii=False))
    save_json("05_parallel.json", {"total_wall_seconds": round(total_wall, 1), "results": results})


if __name__ == "__main__":
    asyncio.run(main())
