# backend/app/deps.py
# ======================================================================
# EFHC Bot — Общие зависимости FastAPI: БД-сессия, идемпотентность,
# аутентификация,
# админ-гейт, keyset-пагинация, ETag и точность Decimal.
# ----------------------------------------------------------------------
# Канон/требования:
# • Все денежные POST — строго с Idempotency-Key (или client_nonce).
# • Списки — только cursor-based (keyset) пагинация.
# • Источник истины для генерации — посекундные ставки.
#   (В сервисах; здесь не считаем.)
# • Пользователь не может уходить в минус.
#   Банк — может (проверки в сервисах/locks).
#
# Этот модуль НЕ делает бизнес-логику, только инфраструктуру/валидацию.
# ======================================================================

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from typing import Any

from app.core.config_core import get_settings
from app.core.database_core import fastapi_db_dependency as get_db
from app.core.database_core import get_session_factory
from app.core.logging_core import get_logger
from app.identity.types import parse_global_id
from app.utils.cursor_codec import decode_cursor, encode_cursor
from fastapi import (
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)
settings = get_settings()

# ----------------------------------------------------------------------
# БД-сессия
# ----------------------------------------------------------------------


# Точность Decimal и утилиты для UI/списков
# ----------------------------------------------------------------------

EFHC_DECIMALS: int = int(getattr(settings, "EFHC_DECIMALS", 8) or 8)
Q8 = Decimal(1).scaleb(-EFHC_DECIMALS)


def d8(x: Any) -> Decimal:
    """Округление вниз до 8 знаков — строго по канону."""
    return Decimal(str(x)).quantize(Q8, rounding=ROUND_DOWN)


def make_etag(payload: dict[str, Any]) -> str:
    """
    Делает детерминированный ETag из JSON - представления payload.
    Используется фронтом для «304 Not Modified».
    """
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()



def decode_cursor_or_400(cursor: str) -> dict[str, Any]:
    """Декодирует cursor (SSOT) и преобразует ошибку в HTTP 400.

    Зачем:
    - Роутам часто нужен немедленный 400.
    - SSOT-кодек остаётся чистым и даёт ValueError.
    """
    try:
        return dict(decode_cursor(cursor))
    except ValueError as err:
        raise HTTPException(
            status_code=400,
            detail="Некорректный cursor",
        ) from err


# ----------------------------------------------------------------------
# Идемпотентность денежных операций
# ----------------------------------------------------------------------


IDEMPOTENCY_KEY_MAX_LENGTH = 128


def validate_raw_idempotency_key(
    raw: str | None,
    *,
    required_detail: str = "Idempotency-Key (или client_nonce) обязателен",
) -> str:
    """Проверить сырой idempotency key до необратимого хеширования."""

    raw_value = str(raw or "")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in raw_value):
        raise HTTPException(
            status_code=400,
            detail="IDEMPOTENCY_KEY_INVALID",
        )
    value = raw_value.strip()
    if not value:
        raise HTTPException(status_code=400, detail=required_detail)
    if len(value) > IDEMPOTENCY_KEY_MAX_LENGTH:
        raise HTTPException(
            status_code=400,
            detail="IDEMPOTENCY_KEY_TOO_LONG",
        )
    return value


def normalize_idempotency_key(raw: str | None) -> str:
    """Нормализовать проверенный клиентский nonce в SHA-256 key."""

    value = validate_raw_idempotency_key(raw)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def require_idempotency_key(
    idempotency_key: str | None = Header(
        default=None,
        convert_underscores=False,
        alias="Idempotency-Key",
    ),
    client_nonce: str | None = Query(
        default=None,
        description="Альтернатива заголовку Idempotency-Key",
    ),
) -> str:
    """Зависимость FastAPI: Idempotency-Key ИЛИ client_nonce.

    Возвращает нормализованный ключ (sha256 hex).
    Применять только для денежных POST.
    """
    header_raw = str(idempotency_key or "")
    query_raw = str(client_nonce or "")
    raw = (
        header_raw
        if header_raw.strip() or any(
            ord(ch) < 32 or ord(ch) == 127 for ch in header_raw
        )
        else query_raw
    )
    value = validate_raw_idempotency_key(raw)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def require_idempotency_key_header_only(
    idempotency_key: str | None = Header(
        default=None,
        convert_underscores=False,
        alias="Idempotency-Key",
    ),
) -> str:
    """Строгий вариант: только заголовок Idempotency-Key.

    Нужен там, где query/body nonce запрещены политикой.
    """
    value = validate_raw_idempotency_key(
        idempotency_key,
        required_detail="Idempotency-Key обязателен",
    )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def accept_idempotency_key(
    idempotency_key: str | None = Header(
        default=None,
        convert_underscores=False,
        alias="Idempotency-Key",
    ),
    client_nonce: str | None = Query(
        default=None,
        description="Альтернатива заголовку Idempotency-Key",
    ),
) -> str | None:
    """SHOULD-IDK: если ключ есть — нормализует и возвращает.
    Если ключа нет — возвращает None.

    Использовать для команд, где повторяемость запроса желательна.
    Например, служебные POST/PATCH.
    Но отсутствие ключа не должно блокировать пользователя/оператора.
    """
    header_raw = str(idempotency_key or "")
    query_raw = str(client_nonce or "")
    raw = (
        header_raw
        if header_raw.strip() or any(
            ord(ch) < 32 or ord(ch) == 127 for ch in header_raw
        )
        else query_raw
    )
    if not raw.strip() and not any(
        ord(ch) < 32 or ord(ch) == 127 for ch in raw
    ):
        return None
    value = validate_raw_idempotency_key(raw)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


# ----------------------------------------------------------------------
# Аутентификация пользователя (auth-ready, с запасным контуром)
# ----------------------------------------------------------------------


class ExternalEventDedupeUnavailable(RuntimeError):
    """Хранилище dedupe недоступно; external event нельзя обрабатывать."""


@dataclass
class AuthContext:
    """Минимальный privileged context только с canonical admin owner."""

    global_id: int
    admin_id: int
    role: str
    is_admin: bool = True
    auth_source: str = "admin_global_session"


async def register_external_event_after_secret(
    provider: str,
    request: Request,
    db: AsyncSession,
    *,
    x_event_id: str | None = None,
    x_delivery_id: str | None = None,
    x_update_id: str | None = None,
) -> dict[str, Any]:
    """Register external webhook/callback after source validation.

    Security canon: callers that have a provider secret/signature must
    verify that secret first and only then call this helper.
    This prevents invalid webhook attempts from poisoning the dedupe
    table before auth.
    """
    raw_id = (
        (x_event_id or "").strip()
        or (x_delivery_id or "").strip()
        or (x_update_id or "").strip()
    )

    body_bytes = await request.body()
    request.state._raw_body = body_bytes
    if not raw_id:
        raw_id = hashlib.sha256(body_bytes).hexdigest()

    event_id = hashlib.sha256(raw_id.encode("utf-8")).hexdigest()

    try:
        from sqlalchemy import text as _text

        q = _text(
            """
        INSERT INTO efhc_core.processed_external_events
                (provider, event_id)
            VALUES (:p, :e)
            ON CONFLICT (provider, event_id) DO NOTHING
            RETURNING 1
            """
        )
        r = await db.execute(q, {"p": provider, "e": event_id})
        inserted = r.scalar_one_or_none() == 1
        return {
            "provider": provider,
            "event_id": event_id,
            "is_duplicate": (not inserted),
        }
    except Exception as exc:
        logger.exception(
            "external event dedupe unavailable",
            extra={"provider": provider},
        )
        raise ExternalEventDedupeUnavailable(
            "external event dedupe unavailable"
        ) from exc


def external_event_dedupe_dep(provider: str):
    """Dependency for external callbacks without a secret pre-check.

    Secret-protected routes must call
    register_external_event_after_secret() manually after verifying the
    provider token/signature.
    """

    async def _dep(
        request: Request,
        db: AsyncSession = Depends(get_db),
        x_event_id: str | None = Header(
            default=None,
            alias="X-Event-Id",
        ),
        x_delivery_id: str | None = Header(
            default=None,
            alias="X-Delivery-Id",
        ),
        x_update_id: str | None = Header(
            default=None,
            alias="X-Telegram-Update-Id",
        ),
    ) -> dict[str, Any]:
        return await register_external_event_after_secret(
            provider,
            request,
            db,
            x_event_id=x_event_id,
            x_delivery_id=x_delivery_id,
            x_update_id=x_update_id,
        )

    return _dep


def _try_int(val: Any) -> int | None:
    """Пытается преобразовать значение в int.

    При ошибке возвращает None.
    """
    try:
        v = int(val)
        return v if v > 0 else None
    except Exception:
        return None


async def _bearer_auth_context(request: Request):
    """Проверить Bearer session, если Authorization присутствует."""

    raw = request.headers.get("Authorization")
    if raw is None:
        return None
    scheme, separator, token = raw.partition(" ")
    if (
        separator != " "
        or scheme.lower() != "bearer"
        or not token
        or token != token.strip()
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Auth session недействительна",
            headers={"WWW-Authenticate": "Bearer"},
        )

    from app.identity.auth_errors import (
        AuthSessionNotActive,
        InvalidAuthRuntimeInput,
    )
    from app.identity.auth_runtime_services import AuthSessionService

    service = AuthSessionService(get_session_factory())
    try:
        context = await service.authenticate(token)
    except (AuthSessionNotActive, InvalidAuthRuntimeInput) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Auth session недействительна",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    request.state.auth_context = context
    return context


async def get_current_telegram_subject_id(
    request: Request,
) -> int:
    """Return the verified Telegram provider subject for current session.

    This is a provider boundary for TonConnect/Telegram operations; it is not
    a business-owner selector.
    """

    from app.identity.auth_transport_telemetry import (
        record_auth_transport,
    )
    from app.identity.telegram_channel import (
        TelegramChannelResolutionError,
        resolve_verified_telegram_subject,
    )

    context = await _bearer_auth_context(request)
    if context is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется server-side auth session",
            headers={"WWW-Authenticate": "Bearer"},
        )

    session_factory = get_session_factory()
    try:
        async with session_factory() as session:
            subject = await resolve_verified_telegram_subject(
                session, global_id=context.global_id.value
            )
    except TelegramChannelResolutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Telegram provider mapping конфликтует",
        ) from exc
    if subject is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Telegram provider mapping не найден",
        )

    request.state.provider_tg_id = subject
    record_auth_transport("server_session_provider_subject")
    return int(subject)


async def require_wallet_connected(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_global_id: str | None = None,
    feature: str | None = None,
) -> None:
    """Проверить кошелёк только по canonical ``global_id`` owner.

    Telegram authentication разрешается до этой границы, но wallet
    business runtime не принимает Telegram ID как selector.
    """
    global_id = str(current_global_id or "").strip()
    try:
        parse_global_id(global_id)
    except Exception:
        global_id = ""
    if not global_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "WALLET_REQUIRED",
                "details": {"feature": feature or "unknown"},
            },
        )
    try:
        from app.services.wallets_service import has_active_wallet
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Wallet service is not available",
        ) from e

    ok = await has_active_wallet(
        db,
        global_id=global_id,
    )
    if ok:
        return None

    logger.info(
        "wallet.required",
        extra={
            "audit__schema__version": "v1",
            "global_id": global_id,
            "event": "wallet_gate",
            "result": "blocked",
            "feature": feature or "unknown",
        },
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "code": "WALLET_REQUIRED",
            "details": {"feature": feature or "unknown"},
        },
    )


# ----------------------------------------------------------------------
# Админ-гейт (эмиссия/модерация и т.п.)
# ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class VerifiedAdminPrincipal:
    """Only the verified Admin gate may produce this route/service DTO.

    It is deliberately separate from immutable provider-neutral AuthContext.
    No session credential is carried into the route layer.
    """

    global_id: int
    admin_id: int
    role: str
    is_admin: bool
    auth_source: str


async def require_admin_or_nft_or_key(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> VerifiedAdminPrincipal:
    """Центральный admin gate: session + RBAC ИЛИ Admin NFT-доступ.

    Исторический Admin NFT-путь восстановлен без возврата Telegram-header и
    admin-secret bypass. Bearer session сначала даёт canonical ``global_id``;
    затем разрешается обычный ``admin_whitelist``/RBAC либо резервный
    Admin NFT-кэш через проверенную ``ton_wallet_id`` identity; источник
    права — точный NFT-item address из TON_ADMIN_NFT_IDS, обнаруженный штатным NFT-checker.
    """

    from app.identity.auth_transport_telemetry import (
        record_auth_transport,
    )
    from app.services.admin.admin_rbac import RBAC, AdminAuthError

    context = await _bearer_auth_context(request)
    if context is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется server-side auth session",
            headers={"WWW-Authenticate": "Bearer"},
        )

    global_id = int(context.global_id.value)

    # Permanent OWNER policy: public Global ID 0000000088 is the only
    # administrator. The public number is never a credential. A native
    # server-side Telegram session, exact server-stored TG binding and an
    # active SuperAdmin RBAC record are all required. Test MOCK sessions,
    # other Global IDs, arbitrary wallet proofs and Admin NFT do not bypass.
    from app.services.admin.admin_rbac import AdminRole

    if (
        global_id != 88
        or context.session_id is None
        or context.provider.value != "telegram"
        or not str(context.provider_subject).isdigit()
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ADMIN_OWNER_VERIFIED_TELEGRAM_REQUIRED",
        )
    try:
        admin = await RBAC.resolve_admin(db, global_id)
    except AdminAuthError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ADMIN_OWNER_NOT_AUTHORIZED",
        ) from None
    except Exception as exc:
        logger.warning("admin RBAC check failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Проверка прав администратора временно недоступна",
        ) from exc
    if (
        admin.role != AdminRole.SUPERADMIN
        or admin.tg_id is None
        or str(admin.tg_id) != context.provider_subject
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ADMIN_OWNER_TELEGRAM_BINDING_MISMATCH",
        )
    auth_source = "admin_server_session_bridge"
    record_auth_transport(auth_source)
    return VerifiedAdminPrincipal(
        global_id=int(admin.global_id),
        admin_id=int(admin.id),
        role=str(admin.role),
        is_admin=True,
        auth_source=auth_source,
    )


# Все текущие admin routes импортируют require_admin. Сохраняем имя,
# но реальный центральный gate снова включает Admin NFT credential.
require_admin = require_admin_or_nft_or_key


async def require_admin_write(
    context: VerifiedAdminPrincipal = Depends(require_admin_or_nft_or_key),
) -> VerifiedAdminPrincipal:
    """Проверить право на любую изменяющую Admin-операцию.

    ``require_admin`` отвечает только за аутентификацию и принадлежность к
    контуру Admin-доступа. Этот отдельный guard запрещает роли
    ``Analyst/auditor`` выполнять POST/PUT/PATCH/DELETE. Admin NFT использует
    уже разрешённый canonical principal и не проходит повторную
    whitelist-only авторизацию.
    """

    from app.services.admin.admin_rbac import (
        RBAC,
        AdminAuthError,
        AdminRole,
    )

    try:
        admin = RBAC.admin_from_auth_context(context)
        RBAC.require_role(admin, AdminRole.MODERATOR)
    except AdminAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав для изменения данных.",
        ) from exc
    return context


# ----------------------------------------------------------------------
# Health-проверка БД
# ----------------------------------------------------------------------


async def db_ping(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Health: выполняет простой запрос к БД.

    Возвращает статус доступности.
    """
    try:
        from sqlalchemy import text as _text

        row = await db.execute(_text("SELECT 1"))
        ok = row.scalar_one_or_none() == 1
        return {"db": "ok" if ok else "fail"}
    except Exception as e:
        logger.error("db_ping error: %s", e)
        return {"db": "fail", "error": str(e)}


# ======================================================================
# Пояснения «для чайника»:
# • get_db() — отдаёт AsyncSession.
#   При ошибках — rollback, затем исключение.
# • require_idempotency_key() — включайте как Depends
#   во всех денежных POST.
# Если клиент не может передать заголовок — используйте
# client_nonce в query,
# или нормализуйте body-поле через normalize_idempotency_key().
# • require_admin() — требует server-side session global_id и разрешает
#   обычный RBAC/admin_whitelist либо активный Admin NFT whitelist;
#   старые admin headers/SECRET_KEY bypass запрещены.
# • encode_cursor()/decode_cursor() — единые helpers
#   для keyset-пагинации
# списков.
# • Никаких «суточных» ставок в этом файле нет и быть не должно.
# ======================================================================

__all__ = [
    "decode_cursor",
    "encode_cursor",
]
