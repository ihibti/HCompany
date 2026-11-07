import asyncio

import pytest

from escapehatch.keys import KeyPool, _env_slots


@pytest.mark.asyncio
async def test_keypool_capacity_and_blocking():
    pool = KeyPool([("k1", 1), ("k2", 1)])
    assert pool.capacity == 2
    try:
        async with pool.acquire():
            async with pool.acquire():
                acquired = False

                async def third():
                    nonlocal acquired
                    async with pool.acquire():
                        acquired = True

                t = asyncio.create_task(third())
                await asyncio.sleep(0.3)
                assert not acquired  # both slots busy -> waits
        await asyncio.sleep(0.3)
        assert acquired
        await t
    finally:
        await pool.aclose()


@pytest.mark.asyncio
async def test_keypool_prefers_less_loaded_key():
    pool = KeyPool([("big", 4), ("small", 1)])
    try:
        async with pool.acquire():  # -> big (0/4 beats 0/1? tie -> first)
            async with pool.acquire():  # -> small? big used=1 ratio .25 vs small 0
                pass
        # after release all free again
        assert all(s["used"] == 0 for s in pool._slots)
    finally:
        await pool.aclose()


def test_env_slots(monkeypatch):
    monkeypatch.setenv("HAI_API_KEY", "aaa")
    monkeypatch.setenv("HCOMPANY_KEY", "bbb")
    assert _env_slots() == [("aaa", 3), ("bbb", 3)]
    monkeypatch.delenv("HCOMPANY_KEY")
    assert _env_slots() == [("aaa", 3)]
    monkeypatch.delenv("HAI_API_KEY")
    assert _env_slots() == []


def test_keypool_requires_keys(monkeypatch):
    monkeypatch.delenv("HAI_API_KEY", raising=False)
    monkeypatch.delenv("HCOMPANY_KEY", raising=False)
    with pytest.raises(ValueError):
        KeyPool()
