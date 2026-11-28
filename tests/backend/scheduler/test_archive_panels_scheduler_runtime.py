from __future__ import annotations

from types import SimpleNamespace

import pytest
from app.scheduler import archive_panels

pytestmark = pytest.mark.asyncio


class _Session:
    def __init__(self):
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def commit(self):
        self.committed = True


async def test_run_once_uses_limit_and_return_count(monkeypatch):
    session = _Session()
    captured: dict[str, int] = {}

    async def fake_archive_expired_panels(db, *, limit: int = 1000):
        captured["limit"] = int(limit)
        assert db is session
        return 7

    monkeypatch.setattr(
        archive_panels,
        "db_session",
        lambda: session,
    )
    monkeypatch.setattr(
        archive_panels,
        "archive_expired_panels",
        fake_archive_expired_panels,
    )
    monkeypatch.setattr(
        archive_panels,
        "S",
        SimpleNamespace(PANELS_ARCHIVE_BATCH_SIZE=11),
    )

    result = await archive_panels.run_once()

    assert result == {"archived": 7}
    assert captured == {"limit": 11}
    assert session.committed is True
