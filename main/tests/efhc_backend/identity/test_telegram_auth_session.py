"""Узкие contracts Telegram account/session цикла 1619."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast

import pytest
from app.identity.auth_runtime_services import AuthSessionService
from app.identity.telegram_auth_session import (
    TelegramAccountResolution,
    TelegramAuthSessionError,
    TelegramAuthSessionResult,
    TelegramAuthSessionService,
    build_telegram_auth_session_contract,
)
from app.identity.types import GlobalId
from app.routes.auth_telegram_routes import issue_telegram_auth_session
from app.schemas.auth_telegram_schemas import TelegramAuthSessionOut
from fastapi import HTTPException, Response

NOW = datetime(2026, 7, 31, 0, 0, tzinfo=UTC)


def test_telegram_session_contract_фиксирует_owner_и_replay() -> None:
    contract = build_telegram_auth_session_contract()
    assert contract["цикл"] == 1619
    assert contract["атомарность"]["identity_resolver_used"] is True
    assert contract["session"]["raw_token_stored"] is False
    assert contract["replay"]["raw_init_data_stored"] is False
    assert contract["запреты"]["tg_id_as_owner"] is True


def test_result_repr_не_раскрывает_global_id_или_token() -> None:
    token = "S" * 43
    result = TelegramAuthSessionResult(
        account=TelegramAccountResolution(
            global_id=GlobalId(42),
            outcome="existing_identity",
            identity_id=7,
        ),
        session=SimpleNamespace(
            token=token,
            expires_at=NOW,
        ),  # type: ignore[arg-type]
    )
    rendered = repr(result)
    assert token not in rendered
    assert "0000000042" not in rendered
    assert "<redacted>" in rendered


@pytest.mark.asyncio
async def test_endpoint_выдаёт_session_без_tg_id() -> None:
    class Adapter:
        def verify(self, _raw: object) -> object:
            return object()

    class Service:
        async def login(self, _verified: object) -> object:
            return SimpleNamespace(
                account=SimpleNamespace(
                    global_id=GlobalId(42),
                    outcome="existing_identity",
                ),
                session=SimpleNamespace(
                    token="S" * 43,
                    expires_at=NOW,
                ),
            )

    response = Response()
    result = await issue_telegram_auth_session(
        response=response,
        init_data="auth_date=1&hash=x&user=y",
        _enabled=None,
        adapter=cast(object, Adapter()),
        service=cast(TelegramAuthSessionService, Service()),
    )
    assert isinstance(result, TelegramAuthSessionOut)
    payload = result.model_dump(mode="json")
    assert payload["provider"] == "telegram"
    assert payload["global_id"] == "0000000042"
    assert payload["session"]["access_token"] == "S" * 43
    assert "tg_id" not in payload
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.asyncio
async def test_endpoint_отклоняет_replay_с_401() -> None:
    class Adapter:
        def verify(self, _raw: object) -> object:
            return object()

    class Service:
        async def login(self, _verified: object) -> object:
            raise TelegramAuthSessionError("INIT_DATA_REPLAY")

    with pytest.raises(HTTPException) as captured:
        await issue_telegram_auth_session(
            response=Response(),
            init_data="auth_date=1&hash=x&user=y",
            _enabled=None,
            adapter=cast(object, Adapter()),
            service=cast(TelegramAuthSessionService, Service()),
        )
    assert captured.value.status_code == 401
    assert captured.value.detail["details"] == {
        "reason": "INIT_DATA_REPLAY"
    }


def test_telegram_session_service_требует_session_factory() -> None:
    with pytest.raises(TelegramAuthSessionError) as captured:
        TelegramAuthSessionService(
            cast(object, AuthSessionService)
        )
    assert captured.value.reason == "SERVICE_CONFIG_INVALID"
