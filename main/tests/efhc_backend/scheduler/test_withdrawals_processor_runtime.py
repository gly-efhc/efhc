from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from app.scheduler import withdrawals_processor

pytestmark = pytest.mark.asyncio


class _ScalarRows:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)


class _ExecuteResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def scalars(self):
        return _ScalarRows(self._rows)


class _Session:
    def __init__(self, rows):
        self.rows = list(rows)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, stmt):
        params = stmt.compile().params
        assert params.get("status_1") == "PENDING"
        return _ExecuteResult(self.rows)


def _install_session(monkeypatch, session):
    @asynccontextmanager
    async def fake_db_session():
        yield session

    monkeypatch.setattr(
        withdrawals_processor,
        "db_session",
        fake_db_session,
    )


async def test_stale_pending_withdrawal_notifies_with_canonical_signature(
    monkeypatch,
):
    old = datetime.now(UTC) - timedelta(days=4)
    fresh = datetime.now(UTC) - timedelta(hours=1)
    session = _Session(
        [
            SimpleNamespace(created_at=old, status="PENDING"),
            SimpleNamespace(created_at=fresh, status="PENDING"),
        ]
    )
    _install_session(monkeypatch, session)
    captured: dict[str, object] = {}

    async def fake_notify_generic(
        db,
        *,
        event: str,
        message: str,
        payload_json: str = "{}",
        send_telegram: bool = True,
    ) -> int:
        captured["db"] = db
        captured["event"] = event
        captured["message"] = message
        captured["payload_json"] = payload_json
        captured["send_telegram"] = send_telegram
        return 501

    monkeypatch.setattr(
        withdrawals_processor.AdminNotifier,
        "notify_generic",
        staticmethod(fake_notify_generic),
    )

    result = await withdrawals_processor.run_once()

    assert result == {"pending": 2, "stale": 1}
    assert captured["db"] is session
    assert captured["event"] == "withdrawals.stale"
    assert captured["send_telegram"] is True
    payload = json.loads(str(captured["payload_json"]))
    assert payload["pending_count"] == 2
    assert payload["stale_count"] == 1
    assert payload["threshold_days"] == 3
    assert payload["source"] == "withdrawals_processor"


async def test_paid_and_fresh_pending_do_not_trigger_stale_alert(
    monkeypatch,
):
    fresh = datetime.now(UTC) - timedelta(hours=1)
    session = _Session([SimpleNamespace(created_at=fresh, status="PENDING")])
    _install_session(monkeypatch, session)
    calls: list[object] = []

    async def fake_notify_generic(*args, **kwargs):
        calls.append((args, kwargs))
        return 1

    monkeypatch.setattr(
        withdrawals_processor.AdminNotifier,
        "notify_generic",
        staticmethod(fake_notify_generic),
    )

    result = await withdrawals_processor.run_once()

    assert result == {"pending": 1, "stale": 0}
    assert calls == []


async def test_withdrawals_processor_does_not_use_lowercase_pending():
    text = withdrawals_processor.__loader__.get_source(
        withdrawals_processor.__name__
    )
    assert '== "pending"' not in text
    assert "WithdrawalRequest.status == \"PENDING\"" in text
