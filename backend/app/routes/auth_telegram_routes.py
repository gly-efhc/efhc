"""Telegram WebApp initData auth endpoint цикла 1619."""

from __future__ import annotations

from typing import Annotated

from app.core.config_core import get_settings
from app.core.database_core import get_session_factory
from app.core.security_core import validate_telegram__init__data
from app.identity.referral_ingress import (
    ReferralIngressError,
    parse_referral_start_param,
)
from app.identity.telegram_auth_session import (
    TelegramAuthSessionError,
    TelegramAuthSessionService,
)
from app.identity.telegram_init_data import (
    TelegramInitDataAdapter,
    TelegramInitDataError,
)
from app.schemas.auth_telegram_schemas import (
    TelegramAuthSessionIn,
    TelegramAuthSessionOut,
)
from app.schemas.auth_ton_schemas import AuthSessionCredentialOut
from fastapi import (
    APIRouter,
    Body,
    Depends,
    Header,
    HTTPException,
    Response,
    status,
)

router = APIRouter(
    prefix="/auth/telegram",
    tags=["auth", "telegram"],
)


def _error_detail(
    *,
    error: str,
    message: str,
    reason: str | None = None,
) -> dict[str, object]:
    details: dict[str, str] = {}
    if reason is not None:
        details["reason"] = reason
    return {
        "error": error,
        "message": message,
        "details": details,
    }


def get_telegram_init_data_adapter() -> TelegramInitDataAdapter:
    """Создать adapter поверх канонического HMAC verifier."""

    return TelegramInitDataAdapter(validate_telegram__init__data)


def get_telegram_auth_session_service() -> TelegramAuthSessionService:
    """Создать transactional Telegram account/session service."""

    return TelegramAuthSessionService(get_session_factory())


def require_telegram_login_enabled() -> None:
    """Отсутствующий feature flag означает deny."""

    settings = get_settings()
    runtime_flags = dict(
        getattr(settings, "AUTH_PROVIDER_FLAGS", {}) or {}
    )
    test_flags = dict(
        getattr(settings, "AUTH_PROVIDER_TEST_FLAGS", {}) or {}
    )
    env = str(getattr(settings, "ENV", "local") or "local").lower()
    active = test_flags if env in {"ci", "test"} else runtime_flags
    if active.get("telegram") is not True:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_error_detail(
                error="auth.provider_disabled",
                message="Telegram login provider отключён",
            ),
        )


@router.post(
    "/session",
    response_model=TelegramAuthSessionOut,
    summary="Проверить Telegram initData и выдать auth session",
)
async def issue_telegram_auth_session(
    response: Response,
    init_data: Annotated[
        str,
        Header(alias="X-Telegram-Init-Data"),
    ],
    body: Annotated[
        TelegramAuthSessionIn | None,
        Body(),
    ] = None,
    _enabled: None = Depends(require_telegram_login_enabled),
    adapter: TelegramInitDataAdapter = Depends(
        get_telegram_init_data_adapter
    ),
    service: TelegramAuthSessionService = Depends(
        get_telegram_auth_session_service
    ),
) -> TelegramAuthSessionOut:
    """Разрешить Telegram account без tg_id owner semantics."""

    try:
        referral_ingress = parse_referral_start_param(
            body.referral_start_param if body is not None else None
        )
    except ReferralIngressError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_error_detail(
                error=exc.code,
                message=exc.message,
                reason=exc.reason,
            ),
        ) from exc

    try:
        verified = adapter.verify(init_data)
    except TelegramInitDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_error_detail(
                error=exc.code,
                message=exc.message,
                reason=exc.reason,
            ),
        ) from exc
    try:
        if referral_ingress.normalized_code is None:
            login = await service.login(verified)
        else:
            login = await service.login(
                verified,
                referral_start_param=(
                    referral_ingress.normalized_code
                ),
            )
    except TelegramAuthSessionError as exc:
        status_code = status.HTTP_409_CONFLICT
        if exc.reason == "INIT_DATA_REPLAY":
            status_code = status.HTTP_401_UNAUTHORIZED
        elif exc.reason in {
            "REFERRAL_CODE_NOT_FOUND",
            "REFERRAL_CODE_INVALID",
        }:
            status_code = status.HTTP_400_BAD_REQUEST
        raise HTTPException(
            status_code=status_code,
            detail=_error_detail(
                error=exc.code,
                message=exc.message,
                reason=exc.reason,
            ),
        ) from exc

    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return TelegramAuthSessionOut(
        global_id=login.account.global_id.display,
        account_outcome=login.account.outcome,
        session=AuthSessionCredentialOut(
            access_token=login.session.token,
            expires_at=login.session.expires_at,
        ),
    )


__all__ = [
    "get_telegram_auth_session_service",
    "get_telegram_init_data_adapter",
    "issue_telegram_auth_session",
    "require_telegram_login_enabled",
    "router",
]
