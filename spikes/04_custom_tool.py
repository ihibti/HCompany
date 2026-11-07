"""Spike 4: custom tool request_confirmation called before irreversible clicks.

Runs a session on lemonde.fr where the agent must call request_confirmation(action)
before clicking anything that dismisses the cookie banner irreversibly.
Saves events + tool call log.
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import OUT_DIR, dump_events, get_client, save_json

CALL_LOG = OUT_DIR / "04_tool_calls.jsonl"


def request_confirmation(action: str) -> str:
    """Ask the user to approve an action before it is performed.

    Call this before any click that cannot be undone (accepting cookies,
    closing a banner, submitting a form).
    """
    entry = {"action": action, "approved": True}
    with CALL_LOG.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    return "approved"


def main() -> None:
    if CALL_LOG.exists():
        CALL_LOG.unlink()
    client = get_client()
    prompt = (
        "Go to https://www.lemonde.fr . A cookie banner will appear. "
        "Before clicking ANY button on the cookie banner (accept, refuse, close, "
        "settings), you MUST first call the request_confirmation tool with a "
        "description of the action you intend to take. Only click after it returns "
        "'approved'. Goal: refuse all non-essential cookies with the fewest clicks. "
        "Do not accept any cookies. Report each click you made."
    )
    t0 = time.monotonic()
    result = client.run_session(
        agent=__import__("os").environ.get("SPIKE_AGENT", "h/web-surfer-flash"),
        messages=prompt,
        tools=[request_confirmation],
        max_steps=40,
        max_time_s=420,
    )
    wall = time.monotonic() - t0
    events = dump_events(result.events)
    out = {
        "session_id": result.id,
        "status": str(result.status),
        "wall_seconds": round(wall, 1),
        "answer": result.answer.model_dump() if hasattr(result.answer, "model_dump") else result.answer,
        "event_count": len(events),
        "events": events,
        "tool_calls": [json.loads(l) for l in CALL_LOG.read_text().splitlines()] if CALL_LOG.exists() else [],
    }
    save_json(f"04_custom_tool_{__import__('os').environ.get('SPIKE_AGENT','h/web-surfer-flash').replace('/','_')}.json", out)
    print(f"status={result.status} wall={wall:.1f}s events={len(events)}")
    print(f"answer={out['answer']}")
    print(f"tool_calls={out['tool_calls']}")


if __name__ == "__main__":
    main()
