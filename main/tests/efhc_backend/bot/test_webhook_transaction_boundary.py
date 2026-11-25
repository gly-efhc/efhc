import asyncio
import json
import sys
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from app import deps
from app.bot.handlers import start_handlers
from app.routes import system_routes
from app.services.referral_service import ReferralOnboardingRejected
from fastapi import HTTPException

pytestmark = pytest.mark.asyncio


class _FakeResult:
    def __init__(self, value: int | None) -> None:
        self._value = value

    def scalar_one_or_none(self) -> int | None:
        return self._value


class FakeDb:
    def __init__(self, *, execute_error: Exception | None = None) -> None:
        self.calls: list[str] = []
        self.execute_error = execute_error
        self.pending_markers: set[str] = set()
        self.committed_markers: set[str] = set()

    async def execute(self, statement: Any, params: dict[str, Any]) -> _FakeResult:
        if self.execute_error is not None:
            raise self.execute_error
        sql = str(statement)
        if "processed_external_events" not in sql or "INSERT" not in sql:
            raise AssertionError(f"unexpected SQL: {sql}")
        self.calls.append("insert")
        event_id = str(params["e"])
        if event_id in self.committed_markers or event_id in self.pending_markers:
            return _FakeResult(None)
        self.pending_markers.add(event_id)
        return _FakeResult(1)

    async def commit(self) -> None:
        self.calls.append("commit")
        self.committed_markers.update(self.pending_markers)
        self.pending_markers.clear()

    async def rollback(self) -> None:
        self.calls.append("rollback")
        self.pending_markers.clear()


class FakeRequest:
    def __init__(self, payload: object) -> None:
        self.state = SimpleNamespace(_raw_body=None)
        if isinstance(payload, bytes):
            self._body = payload
        else:
            self._body = json.dumps(payload).encode("utf-8")

    async def body(self) -> bytes:
        return self._body


class FakeMessage:
    def __init__(self, *, tg_id: int = 1001, text: str = "/start") -> None:
        self.from_user = SimpleNamespace(
            id=tg_id,
            username="tester",
            full_name="Tester",
        )
        self.text = text


def _install_process_update(
    monkeypatch: pytest.MonkeyPatch,
    handler: Any,
) -> None:
    fake_bot_module = ModuleType("app.bot.bot")
    fake_bot_module.process_update = handler
    monkeypatch.setitem(sys.modules, "app.bot.bot", fake_bot_module)
    monkeypatch.setattr(
        system_routes,
        "get_settings",
        lambda: SimpleNamespace(
            TELEGRAM_WEBHOOK_SECRET="",
            env_normalized="ci",
        ),
    )


async def _call_webhook(
    request: FakeRequest,
    db: FakeDb,
    *,
    event_id: str,
) -> dict[str, Any]:
    return await system_routes.telegram_webhook(
        request,
        x_telegram_bot_api_secret_token=None,
        db=db,
        x_event_id=event_id,
        x_delivery_id=None,
        x_update_id=None,
    )


async def test_dedupe_helper_не_коммитит_marker() -> None:
    db = FakeDb()
    result = await deps.register_external_event_after_secret(
        "telegram",
        FakeRequest({"update_id": 1}),
        db,
        x_event_id="evt-1",
    )

    assert result["is_duplicate"] is False
    assert db.calls == ["insert"]
    assert len(db.pending_markers) == 1
    assert db.committed_markers == set()


async def test_dedupe_storage_failure_закрывается_ошибкой() -> None:
    db = FakeDb(execute_error=RuntimeError("database unavailable"))

    with pytest.raises(deps.ExternalEventDedupeUnavailable):
        await deps.register_external_event_after_secret(
            "telegram",
            FakeRequest({"update_id": 2}),
            db,
            x_event_id="evt-2",
        )

    assert db.calls == []
    assert db.committed_markers == set()


async def test_webhook_success_делает_один_root_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = FakeDb()
    calls = 0

    async def process_update(**kwargs: Any) -> None:
        nonlocal calls
        calls += 1
        assert kwargs["db"] is db
        assert kwargs["payload"] == {"update_id": 3}

    _install_process_update(monkeypatch, process_update)

    first = await _call_webhook(
        FakeRequest({"update_id": 3}),
        db,
        event_id="evt-3",
    )
    second = await _call_webhook(
        FakeRequest({"update_id": 3}),
        db,
        event_id="evt-3",
    )

    assert first == {"status": "ok"}
    assert second == {"status": "ok", "dedupe": True}
    assert calls == 1
    assert db.calls == ["insert", "commit", "insert", "rollback"]
    assert len(db.committed_markers) == 1


async def test_webhook_processing_error_откатывает_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = FakeDb()

    async def process_update(**_kwargs: Any) -> None:
        raise RuntimeError("handler failed")

    _install_process_update(monkeypatch, process_update)

    with pytest.raises(RuntimeError, match="handler failed"):
        await _call_webhook(
            FakeRequest({"update_id": 4}),
            db,
            event_id="evt-4",
        )

    assert db.calls == ["insert", "rollback"]
    assert db.pending_markers == set()
    assert db.committed_markers == set()


async def test_webhook_cancelled_error_откатывает_и_разрешает_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = FakeDb()

    async def cancelled(**_kwargs: Any) -> None:
        raise asyncio.CancelledError()

    _install_process_update(monkeypatch, cancelled)
    with pytest.raises(asyncio.CancelledError):
        await _call_webhook(
            FakeRequest({"update_id": 5}),
            db,
            event_id="evt-5",
        )

    processed = 0

    async def succeeds(**_kwargs: Any) -> None:
        nonlocal processed
        processed += 1

    _install_process_update(monkeypatch, succeeds)
    result = await _call_webhook(
        FakeRequest({"update_id": 5}),
        db,
        event_id="evt-5",
    )

    assert result == {"status": "ok"}
    assert processed == 1
    assert db.calls == ["insert", "rollback", "insert", "commit"]
    assert len(db.committed_markers) == 1


async def test_webhook_dedupe_failure_возвращает_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = FakeDb(execute_error=RuntimeError("database unavailable"))

    async def should_not_run(**_kwargs: Any) -> None:
        raise AssertionError("process_update must not run")

    _install_process_update(monkeypatch, should_not_run)

    with pytest.raises(HTTPException) as exc_info:
        await _call_webhook(
            FakeRequest({"update_id": 6}),
            db,
            event_id="evt-6",
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "WEBHOOK_DEDUPE_UNAVAILABLE"
    assert db.calls == ["rollback"]


async def test_webhook_invalid_json_не_создаёт_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = FakeDb()

    async def should_not_run(**_kwargs: Any) -> None:
        raise AssertionError("process_update must not run")

    _install_process_update(monkeypatch, should_not_run)

    with pytest.raises(HTTPException) as exc_info:
        await _call_webhook(
            FakeRequest(b'{"update_id":'),
            db,
            event_id="evt-bad-json",
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "INVALID_TELEGRAM_UPDATE"
    assert db.calls == []


async def test_webhook_non_object_json_отклоняется(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = FakeDb()

    async def should_not_run(**_kwargs: Any) -> None:
        raise AssertionError("process_update must not run")

    _install_process_update(monkeypatch, should_not_run)

    with pytest.raises(HTTPException) as exc_info:
        await _call_webhook(
            FakeRequest([1, 2, 3]),
            db,
            event_id="evt-list",
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "INVALID_TELEGRAM_UPDATE"
    assert db.calls == []


async def test_start_unexpected_onboarding_error_пробрасывается(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail(_db: Any, **_kwargs: Any) -> None:
        raise RuntimeError("registration failed")

    monkeypatch.setattr(
        start_handlers,
        "onboard_user_at_first_creation_in_transaction",
        fail,
    )

    with pytest.raises(RuntimeError, match="registration failed"):
        await start_handlers.cmd_start(FakeMessage(), db=SimpleNamespace())


async def test_start_expected_referral_rejection_остаётся_business_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def reject(_db: Any, **_kwargs: Any) -> None:
        raise ReferralOnboardingRejected("invalid_code")

    monkeypatch.setattr(
        start_handlers,
        "onboard_user_at_first_creation_in_transaction",
        reject,
    )

    result = await start_handlers.cmd_start(
        FakeMessage(text="/start ref_invalid"),
        db=SimpleNamespace(),
    )
    assert result is None
