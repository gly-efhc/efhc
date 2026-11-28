from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from app.deps import decode_cursor, encode_cursor
from app.lib.time import utcnow
from app.services import panels_service

pytestmark = pytest.mark.asyncio


class _Result:
    def __init__(self, rows):
        self._rows = list(rows)

    def fetchall(self):
        return list(self._rows)


class _Db:
    def __init__(self, *pages):
        self._pages = list(pages)
        self.calls = 0

    async def execute(self, stmt):
        _ = stmt
        self.calls += 1
        if not self._pages:
            return _Result([])
        return _Result(self._pages.pop(0))


def _row(idx: int, *, expired: bool = False):
    now = utcnow()
    act_at = now - timedelta(minutes=idx)
    expires = (
        now - timedelta(days=1)
        if expired
        else now + timedelta(days=1)
    )
    return SimpleNamespace(
        id=idx,
        public_id=f"ID{idx:08d}",
        act_at=act_at,
        expires_at=expires,
        archived_at=now if expired else None,
        base_gen_per_sec=Decimal("0.00000001"),
        generated_kwh=Decimal("1.00000000"),
    )


async def test_active_panels_over_limit_returns_next_cursor():
    rows = [_row(i) for i in range(1, 5)]
    db = _Db(rows)

    page = await panels_service.list_active_panels(
        db,  # type: ignore[arg-type]
        global_id=777001,
        limit=3,
    )

    assert len(page.items) == 3
    assert page.next_cursor
    decoded = decode_cursor(page.next_cursor)
    assert decoded["id"] == 3
    assert decoded["ts"]


async def test_archived_panels_over_limit_returns_next_cursor():
    rows = [_row(i, expired=True) for i in range(1, 4)]
    db = _Db(rows)

    page = await panels_service.list_archived_panels(
        db,  # type: ignore[arg-type]
        global_id=777002,
        limit=2,
    )

    assert len(page.items) == 2
    assert page.next_cursor
    assert decode_cursor(page.next_cursor)["id"] == 2


async def test_second_page_accepts_cursor_without_typeerror():
    first_rows = [_row(i) for i in range(1, 4)]
    second_rows = [_row(4)]
    db = _Db(first_rows, second_rows)

    first = await panels_service.list_active_panels(
        db,  # type: ignore[arg-type]
        global_id=777003,
        limit=2,
    )
    second = await panels_service.list_active_panels(
        db,  # type: ignore[arg-type]
        global_id=777003,
        limit=2,
        cursor=first.next_cursor,
    )

    assert first.next_cursor
    assert [item["id"] for item in second.items] == [4]
    assert second.next_cursor is None


async def test_cursor_roundtrip_preserves_ts_and_id():
    payload = {"ts": "2026-06-16T00:00:00+00:00", "id": 42}
    assert decode_cursor(encode_cursor(payload))["ts"] == payload["ts"]
    assert decode_cursor(encode_cursor(payload))["id"] == payload["id"]


async def test_panels_no_overflow_returns_no_next_cursor():
    db = _Db([_row(1), _row(2)])

    page = await panels_service.list_active_panels(
        db,  # type: ignore[arg-type]
        global_id=777004,
        limit=2,
    )

    assert len(page.items) == 2
    assert page.next_cursor is None
