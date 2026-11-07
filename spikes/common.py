"""Shared helpers for the Escape Hatch API spike."""

import json
import os
import time
from pathlib import Path
from typing import Any

from hai_agents import Client

OUT_DIR = Path(__file__).parent / "out"
OUT_DIR.mkdir(exist_ok=True)

TASK = (
    "Go to https://www.lemonde.fr and refuse all non-essential cookies with the "
    "fewest clicks possible. Do not accept any cookies. Report each click you made."
)


def get_client() -> Client:
    return Client()  # defaults to EU region (agp.eu.hcompany.ai)


def save_json(name: str, obj: Any) -> Path:
    path = OUT_DIR / name
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str))
    return path


def event_to_dict(event: Any) -> dict:
    """Serialize a SessionEvent pydantic model to a plain dict."""
    if hasattr(event, "model_dump"):
        return event.model_dump(mode="json", exclude_none=False)
    if hasattr(event, "dict"):
        return event.dict()
    return dict(event)


def dump_events(events: list) -> list[dict]:
    return [event_to_dict(e) for e in events]


def wall_clock(fn, *args, **kwargs):
    t0 = time.monotonic()
    result = fn(*args, **kwargs)
    return result, time.monotonic() - t0
