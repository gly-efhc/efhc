from __future__ import annotations

import asyncio
import hashlib
import re
import secrets
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ProfileExportGrant:
    path: Path
    filename: str
    media_type: str
    size: int
    expires_at: float
    timer: asyncio.TimerHandle | None = None
    redeemed: bool = False


class ProfileExportDownloadStore:
    def __init__(self, *, ttl: float = 120, max_entries: int = 32,
                 max_bytes: int = 256 * 1024 * 1024) -> None:
        self.ttl = ttl
        self.max_entries = max_entries
        self.max_bytes = max_bytes
        self._entries: dict[str, ProfileExportGrant] = {}

    @staticmethod
    def _key(ticket: str) -> str | None:
        if not isinstance(ticket, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", ticket):
            return None
        return hashlib.sha256(ticket.encode("ascii")).hexdigest()

    def _discard(self, key: str) -> None:
        entry = self._entries.pop(key, None)
        if entry is not None:
            if entry.timer is not None:
                entry.timer.cancel()
            entry.path.unlink(missing_ok=True)

    def issue(self, path: Path, filename: str, media_type: str) -> str:
        size = path.stat().st_size
        if size <= 0 or len(self._entries) >= self.max_entries or (
            sum(e.size for e in self._entries.values()) + size > self.max_bytes
        ):
            raise ValueError("PROFILE_EXPORT_DOWNLOAD_CAPACITY")
        ticket = secrets.token_urlsafe(32)
        key = self._key(ticket)
        if key is None or key in self._entries:
            raise RuntimeError("PROFILE_EXPORT_DOWNLOAD_TOKEN")
        loop = asyncio.get_running_loop()
        entry = ProfileExportGrant(path, filename, media_type, size, time.monotonic() + self.ttl)
        entry.timer = loop.call_later(self.ttl, self._discard, key)
        self._entries[key] = entry
        return ticket

    def lookup(self, ticket: str) -> ProfileExportGrant | None:
        key = self._key(ticket)
        if key is None:
            return None
        entry = self._entries.get(key)
        if entry is None or entry.redeemed:
            return None
        if entry.expires_at <= time.monotonic():
            self._discard(key)
            return None
        return entry

    def redeem(self, ticket: str) -> ProfileExportGrant | None:
        entry = self.lookup(ticket)
        if entry is None:
            return None
        key = self._key(ticket)
        assert key is not None
        entry.redeemed = True
        if entry.timer is not None:
            entry.timer.cancel()
        entry.timer = asyncio.get_running_loop().call_later(600, self._discard, key)
        return entry

    def release(self, ticket: str) -> None:
        key = self._key(ticket)
        if key is not None:
            self._discard(key)
