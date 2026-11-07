"""Spike 1: cookie-refusal sessions with answer_schema on lemonde.fr.

Runs h/web-surfer-flash, then h/web-surfer-pro for comparison.
Saves the run result (incl. events) and prints wall time / steps / cost.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import OUT_DIR, TASK, dump_events, get_client, save_json

from pydantic import BaseModel


class CookieRefusal(BaseModel):
    clicks: int
    steps: list[str]
    refused: bool
    notes: str


def run_one(agent: str) -> dict:
    client = get_client()
    print(f"=== {agent} ===", flush=True)
    t0 = time.monotonic()
    result = client.run_session(
        agent=agent,
        messages=TASK,
        answer_schema=CookieRefusal,
        max_steps=40,
        max_time_s=420,
    )
    wall = time.monotonic() - t0

    events = dump_events(result.events)
    out = {
        "agent": agent,
        "session_id": result.id,
        "status": str(result.status),
        "wall_seconds": round(wall, 1),
        "answer": result.answer.model_dump() if hasattr(result.answer, "model_dump") else result.answer,
        "outcome": result.outcome,
        "error": result.error,
        "error_code": result.error_code,
        "event_count": len(events),
        "events": events,
    }
    save_json(f"01_{agent.replace('/', '_')}.json", out)
    print(f"status={result.status} wall={wall:.1f}s events={len(events)}")
    print(f"answer={out['answer']}")
    return out


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "both"
    if which in ("flash", "both"):
        run_one("h/web-surfer-flash")
    if which in ("pro", "both"):
        run_one("h/web-surfer-pro")
