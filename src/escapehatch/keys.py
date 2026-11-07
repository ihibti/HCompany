"""API key pool: spread agent sessions across org quotas.

Each entry is an (api_key, session_limit) pair; acquire() yields an AsyncClient
bound to the least-loaded key with free capacity and blocks until one frees up.
"""

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from hai_agents import AsyncClient

KEY_ENV_VARS = ("HAI_API_KEY", "HCOMPANY_KEY")
DEFAULT_SESSION_LIMIT = 3


def _env_slots() -> list[tuple[str, int]]:
    slots = []
    for var in KEY_ENV_VARS:
        key = os.environ.get(var)
        if key:
            slots.append((key, DEFAULT_SESSION_LIMIT))
    return slots


class KeyPool:
    """Async context manager handing out quota-capped AsyncClients."""

    def __init__(self, slots: list[tuple[str, int]] | None = None) -> None:
        raw = slots if slots is not None else _env_slots()
        if not raw:
            raise ValueError(
                f"KeyPool: no API keys found (set one of {', '.join(KEY_ENV_VARS)})"
            )
        self._slots: list[dict[str, Any]] = [
            {
                "key": key,
                "limit": limit,
                "used": 0,
                "client": AsyncClient(api_key=key),
            }
            for key, limit in raw
        ]

    @property
    def capacity(self) -> int:
        return sum(s["limit"] for s in self._slots)

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[AsyncClient]:
        while True:
            slot = min(self._slots, key=lambda s: s["used"] / max(1, s["limit"]))
            if slot["used"] < slot["limit"]:
                slot["used"] += 1
                break
            await asyncio.sleep(0.1)
        try:
            yield slot["client"]
        finally:
            slot["used"] -= 1

    async def aclose(self) -> None:
        for s in self._slots:
            try:
                await s["client"].aclose()
            except Exception:
                pass


def pool_from_env() -> KeyPool:
    return KeyPool()
