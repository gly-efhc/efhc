from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from app.scheduler import reports_daily

pytestmark = pytest.mark.asyncio


class _Session:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


async def test_reports_daily_notify_uses_canonical_signature(
    monkeypatch,
):
    session = _Session()
    captured: dict[str, object] = {}

    async def fake_summary(db, *, days: int = 1):
        assert db is session
        assert days == 1
        return {"users": 3, "withdrawals": 1}

    async def fake_write_log(db, *, title: str, payload):
        assert db is session
        assert title.startswith("EFHC Daily Report")
        assert payload["users"] == 3

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
        return 801

    monkeypatch.setattr(reports_daily, "db_session", lambda: session)
    monkeypatch.setattr(reports_daily, "daily_admin_summary", fake_summary)
    monkeypatch.setattr(reports_daily, "_write_log", fake_write_log)
    monkeypatch.setattr(
        reports_daily,
        "get_settings",
        lambda: SimpleNamespace(BOT_TOKEN="token", ADMIN_TG_ID="42"),
    )
    monkeypatch.setattr(
        reports_daily.AdminNotifier,
        "notify_generic",
        staticmethod(fake_notify_generic),
    )

    result = await reports_daily.run_once()

    assert result["sent_to_admin"] is True
    assert result["notification_id"] == 801
    assert captured["db"] is session
    assert captured["event"] == "reports.daily"
    assert captured["send_telegram"] is True
    assert "Daily" in str(captured["message"])
    payload = json.loads(str(captured["payload_json"]))
    assert payload["source"] == "reports_daily"
    assert payload["summary"] == {"users": 3, "withdrawals": 1}


async def test_reports_daily_logs_notification_errors(monkeypatch):
    session = _Session()
    logged: list[str] = []

    async def fake_notify_generic(*args, **kwargs):
        raise RuntimeError("notify failed")

    monkeypatch.setattr(reports_daily, "db_session", lambda: session)

    async def fake_summary(db, *, days: int = 1):
        _ = db
        _ = days
        return {"ok": True}

    monkeypatch.setattr(
        reports_daily,
        "daily_admin_summary",
        fake_summary,
    )

    async def fake_write_log(db, *, title: str, payload):
        return None

    monkeypatch.setattr(reports_daily, "_write_log", fake_write_log)
    monkeypatch.setattr(
        reports_daily,
        "get_settings",
        lambda: SimpleNamespace(BOT_TOKEN="token", ADMIN_TG_ID="42"),
    )
    monkeypatch.setattr(
        reports_daily.AdminNotifier,
        "notify_generic",
        staticmethod(fake_notify_generic),
    )
    monkeypatch.setattr(
        reports_daily.logger,
        "exception",
        lambda msg: logged.append(str(msg)),
    )

    result = await reports_daily.run_once()

    assert result["sent_to_admin"] is False
    assert logged == ["daily_report: notification failed"]
