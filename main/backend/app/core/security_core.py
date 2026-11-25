# backend/app/core/security_core.py
# =====================================================================
# Назначение кода:
# Централизованный слой безопасности EFHC Bot:
# • JWT (HS256) + exp/jti для transport/session контрактов;
# • валидация Telegram WebApp initData.
#
# Канон / инварианты EFHC:
# • Здесь НЕТ денег и балансов: только «кто ты» и «можно/нельзя».
# • Авторизация Admin Panel живёт в app.deps.require_admin и active RBAC/Admin-NFT CANON.
# • JWT: алгоритм HS256, обязательный exp; SECRET_KEY берём из настроек.
# • Telegram WebApp initData валидируется строго по алгоритму Telegram
# (HMAC-SHA256 от data-check-string).
#
# ИИ-защита / самовосстановление:
# • Любые ошибки в безопасности → контролируемые 401/403/400,
#   а не падение процесса FastAPI.
# • TTL initData читается из настроек, есть безопасный дефолт (600 сек).
#
# Запреты:
# • Никаких правок балансов/денег в этом модуле.
# • Никакой бизнес-логики — только аутентификация/авторизация.
# =====================================================================

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import timedelta
from typing import Any
from urllib.parse import parse_qsl
from uuid import uuid4

import jwt
from app.core.config_core import get_settings
from app.core.logging_core import get_logger
from app.lib.time import utcnow
from fastapi import HTTPException, status

logger = get_logger(__name__)

# Важно: не кэшируем критичные секреты (например, BOT_TOKEN)
# на уровне модуля.
# Для некритичных параметров допускается снимок настроек при импорте.
_settings = get_settings()

# --------------------------------------------------------------------
# Базовые константы безопасности
# --------------------------------------------------------------------
JWT_ALGORITHM = "HS256"

DEFAULT_ACCESS_TTL_MIN = int(
    getattr(_settings, "ACCESS_TOKEN_EXPIRE_MINUTES", 30) or 30,
)

# TTL проверки Telegram WebApp initData (сек), по умолчанию 10 минут.
WEBAPP_INITDATA_TTL_SEC = int(
    getattr(_settings, "WEBAPP_INITDATA_TTL_SEC", 600) or 600,
)

Payload = dict[str, Any]

# --------------------------------------------------------------------
# JWT токены (HS256)
# --------------------------------------------------------------------


def _get_secret_key() -> str:
    """
    Возвращает SECRET_KEY из настроек или поднимает 500,
    если секрет не сконфигурирован.

    Это соответствует канону: никаких «фиктивных» секретов по умолчанию.
    """
    # Настройки читаем через get_settings(),
    # чтобы избежать stale snapshot.
    key = getattr(get_settings(), "SECRET_KEY", None)
    if not key:
        logger.error("SECRET_KEY is not configured")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server is not configured",
        )
    return str(key)


def create_jwt_token(
    subject: str,
    *,
    expires_delta: timedelta | None = None,
    extra: Payload | None = None,
) -> str:
    """
    Создаёт JWT с полями:
      • sub — строковое назначение/subject токена;
      • iat — момент выпуска (UTC);
      • exp — момент истечения (UTC);
      • jti — уникальный идентификатор токена;
      • extra — дополнительные claims конкретного transport-контракта.

    Для privileged account-контекста canonical actor claim — ``global_id``.
    Provider subjects не используются как privileged owner.
    """
    if expires_delta is None:
        expires_delta = timedelta(minutes=DEFAULT_ACCESS_TTL_MIN)

    now = utcnow()
    payload: Payload = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        "jti": uuid4().hex,
    }
    if extra:
        payload.update(extra)

    secret_key = _get_secret_key()
    token = jwt.encode(payload, secret_key, algorithm=JWT_ALGORITHM)
    return token


def decode_jwt_token(
    token: str,
    *,
    expected_audience: str | None = None,
) -> Payload:
    """
    Декод JWT с контролируемыми ошибками (401).

    Любая проблема верификации токена оборачивается в HTTPException 401,
    чтобы не раскрывать детали внутренней реализации.
    """
    secret_key = _get_secret_key()
    try:
        if expected_audience is None:
            return jwt.decode(
                token,
                secret_key,
                algorithms=[JWT_ALGORITHM],
            )
        return jwt.decode(
            token,
            secret_key,
            algorithms=[JWT_ALGORITHM],
            audience=expected_audience,
        )
    except jwt.ExpiredSignatureError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
        ) from err
    except jwt.InvalidTokenError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        ) from err


# --------------------------------------------------------------------
# Telegram WebApp initData validation
# --------------------------------------------------------------------


def _telegram_data_check_string(init_items: dict[str, str]) -> str:
    """
    Формируем data-check-string: пары key=value,
    отсортированные по ключу,
    разделённые символом перевода строки.

    Поле 'hash' исключается (по спецификации Telegram).
    """
    pairs = [
        f"{k}={v}" for k, v in sorted(init_items.items()) if k != "hash"
    ]
    return "\n".join(pairs)


def validate_telegram__init__data(init_data: str) -> dict[str, Any]:
    """
    Верификация подписи Telegram WebApp initData.

    Алгоритм:
      1) Разобрать init_data как query - string (URL - декод).
      2) Сформировать data-check-string из пар k=v (без hash).
      3) secret_key = HMAC_SHA256('WebAppData', bot_token).
      4) calc_hash = HMAC_SHA256(secret_key, data-check-string)
         .hexdigest().
      5) Сравнить с переданным 'hash'.
      6) Обязательно проверить freshness по 'auth_date'.

    Возвращает распарсенный словарь:
      • все поля, переданные Telegram;
      • поле user — уже JSON - объект, если его удалось распарсить.
    """
    parsed_pairs: dict[str, str] = dict(
        parse_qsl(
            init_data,
            keep_blank_values=True,
            strict_parsing=False,
        ),
    )

    if "hash" not in parsed_pairs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing hash in initData",
        )

    received_hash = parsed_pairs.get("hash") or ""
    if not received_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty hash in initData",
        )

    check_string = _telegram_data_check_string(parsed_pairs)

    bot_token = getattr(get_settings(), "BOT_TOKEN", None)
    if not bot_token:
        logger.error("BOT_TOKEN is not configured")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server is not configured",
        )

    secret_key = hmac.new(
        b"WebAppData",
        bot_token.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    calc_hash = hmac.new(
        secret_key,
        check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(received_hash, calc_hash):
        logger.warning("Invalid Telegram initData signature")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Telegram signature",
        )

    # Telegram WebApp freshness boundary. auth_date is mandatory
    # for replay resistance: missing or malformed values fail closed.
    auth_date = parsed_pairs.get("auth_date")
    if not auth_date:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing auth_date in initData",
        )
    if not auth_date.isdigit():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid auth_date in initData",
        )

    now = int(utcnow().timestamp())
    if now - int(auth_date) > WEBAPP_INITDATA_TTL_SEC:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="initData is too old",
        )

    # Поле user — JSON-строка → объект (если парсится).
    user_raw = parsed_pairs.get("user")
    if user_raw:
        try:
            parsed_pairs["user"] = json.loads(user_raw)
        except Exception:  # noqa: BLE001
            logger.warning("initData 'user' field is not a valid JSON")

    return parsed_pairs


__all__ = [
    "create_jwt_token",
    "decode_jwt_token",
    "validate_telegram__init__data",
]

# =====================================================================
# Граница ответственности: transport JWT + Telegram initData validation.
# Admin authorization: app.deps.require_admin.
# =====================================================================
