"""A tiny async, in-memory TTL cache.

The catalog, docs pages, and pipeline status this server proxies are all
fetched live on every cache miss -- nothing about dynamical.org's data is
baked into this repo. The cache only exists so a burst of tool calls (e.g.
an LLM calling `get_dataset_info` for several collections in a row) doesn't
re-fetch the same STAC document several times per second.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass
class _Entry(Generic[T]):
    value: T
    expires_at: float


class TTLCache(Generic[T]):
    """Async-safe cache keyed by string, with a fixed TTL in seconds."""

    def __init__(self, ttl_seconds: float) -> None:
        self._ttl = ttl_seconds
        self._entries: dict[str, _Entry[T]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock_for(self, key: str) -> asyncio.Lock:
        lock = self._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[key] = lock
        return lock

    async def get_or_fetch(self, key: str, fetch: Callable[[], Awaitable[T]]) -> T:
        entry = self._entries.get(key)
        now = time.monotonic()
        if entry is not None and entry.expires_at > now:
            return entry.value

        async with self._lock_for(key):
            # Re-check after acquiring the lock in case another task refreshed it.
            entry = self._entries.get(key)
            now = time.monotonic()
            if entry is not None and entry.expires_at > now:
                return entry.value

            value = await fetch()
            self._entries[key] = _Entry(value=value, expires_at=now + self._ttl)
            return value

    def invalidate(self, key: str | None = None) -> None:
        if key is None:
            self._entries.clear()
        else:
            self._entries.pop(key, None)
