"""Spike 7: confirm SDK method names for pause/resume/cancel/send_message.

Pure inspection — no API calls, no sessions consumed.
"""

import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import save_json

from hai_agents import Client
from hai_agents.polling import SessionHandle


def main() -> None:
    out = {}

    handle_methods = [m for m in dir(SessionHandle) if not m.startswith("_")]
    out["SessionHandle_methods"] = handle_methods
    for m in ("send_message", "pause", "resume", "cancel", "force_answer", "stream", "wait_for_completion", "status", "changes", "get"):
        out[f"SessionHandle.{m}"] = str(inspect.signature(getattr(SessionHandle, m)))

    client = Client(api_key="hk-spike-introspection-only")  # dummy key, introspection only
    sessions_methods = [m for m in dir(client.sessions.__class__) if not m.startswith("_")]
    out["SessionsClient_methods"] = sessions_methods
    for m in ("create_session", "get_session", "get_session_status", "get_session_changes",
              "list_session_events", "get_session_quota", "send_session_messages",
              "pause_session", "resume_session", "cancel_session", "force_session_answer",
              "get_session_resource", "share_session", "unshare_session"):
        fn = getattr(client.sessions, m, None)
        out[f"sessions.{m}"] = str(inspect.signature(fn)) if fn else "MISSING"

    quota_methods = [m for m in dir(client.quota.__class__) if not m.startswith("_")]
    out["QuotaClient_methods"] = quota_methods
    out["quota.get_token_quota"] = str(inspect.signature(client.quota.get_token_quota))

    for m in ("run_session", "start_session", "session"):
        out[f"Client.{m}"] = str(inspect.signature(getattr(Client, m)))

    print(save_json("07_sdk_methods.json", out).read_text()[:200], "...")
    for k, v in out.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
