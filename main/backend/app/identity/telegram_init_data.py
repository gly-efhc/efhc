"""Строгий Telegram WebApp initData adapter цикла 1619."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final, cast
from urllib.parse import parse_qsl, urlsplit

from app.identity.auth_provider import AuthProvider
from app.identity.provider_registry import (
    finalize_verified_provider_subject,
)
from app.identity.types import InvalidTelegramId, TelegramId
from app.identity.verified_identity import VerifiedIdentity
from app.lib.time import utcnow

TelegramInitDataValidator = Callable[[str], Mapping[str, Any]]

TELEGRAM_INIT_DATA_MAX_LENGTH: Final[int] = 16_384
TELEGRAM_INIT_DATA_MAX_AGE: Final[timedelta] = timedelta(minutes=10)
TELEGRAM_INIT_DATA_FUTURE_SKEW: Final[timedelta] = timedelta(seconds=30)
_REPLAY_NAMESPACE: Final[bytes] = b"efhc.telegram.init-data.v1\x00"
_HASH_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[0-9a-fA-F]{64}$")


class TelegramInitDataError(ValueError):
    """initData не может быть использована для авторизации."""

    code = "auth.telegram_init_data_invalid"
    message = "Telegram initData недействительна"

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(self.message)


@dataclass(frozen=True, slots=True)
class VerifiedTelegramInitData:
    """Проверенный Telegram provider input без raw initData."""

    verified_identity: VerifiedIdentity
    tg_id: TelegramId
    auth_date: datetime
    verified_at: datetime
    replay_key: str
    profile_photo_url: str | None = None

    def __repr__(self) -> str:
        return (
            "VerifiedTelegramInitData("
            "verified_identity='<redacted>', "
            "tg_id='<redacted>', "
            f"auth_date={self.auth_date!r}, "
            f"verified_at={self.verified_at!r}, "
            "replay_key='<redacted>', "
            f"profile_photo_url={'<present>' if self.profile_photo_url else None!r})"
        )


def _utc_now() -> datetime:
    return cast(datetime, utcnow())


def _validate_raw_boundary(value: object) -> str:
    if not isinstance(value, str):
        raise TelegramInitDataError("RAW_TYPE_INVALID")
    if not value or value != value.strip():
        raise TelegramInitDataError("RAW_FORMAT_INVALID")
    if len(value) > TELEGRAM_INIT_DATA_MAX_LENGTH:
        raise TelegramInitDataError("RAW_TOO_LARGE")
    if not value.isascii() or any(ord(item) < 32 for item in value):
        raise TelegramInitDataError("RAW_ASCII_REQUIRED")
    pairs = parse_qsl(
        value,
        keep_blank_values=True,
        strict_parsing=False,
    )
    if not pairs:
        raise TelegramInitDataError("RAW_QUERY_EMPTY")
    keys = [key for key, _item in pairs]
    if len(keys) != len(set(keys)):
        raise TelegramInitDataError("DUPLICATE_FIELD")
    return value


def _validate_clock(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise TelegramInitDataError("CLOCK_INVALID")
    if value.tzinfo is None or value.utcoffset() is None:
        raise TelegramInitDataError("CLOCK_NOT_UTC_AWARE")
    return value.astimezone(UTC)


def _validate_auth_date(
    value: object,
    *,
    now: datetime,
) -> datetime:
    if not isinstance(value, str) or not value.isascii():
        raise TelegramInitDataError("AUTH_DATE_INVALID")
    if not value.isdigit():
        raise TelegramInitDataError("AUTH_DATE_INVALID")
    timestamp = int(value)
    try:
        auth_date = datetime.fromtimestamp(timestamp, tz=UTC)
    except (OverflowError, OSError, ValueError) as exc:
        raise TelegramInitDataError("AUTH_DATE_INVALID") from exc
    if now - auth_date > TELEGRAM_INIT_DATA_MAX_AGE:
        raise TelegramInitDataError("AUTH_DATE_EXPIRED")
    if auth_date - now > TELEGRAM_INIT_DATA_FUTURE_SKEW:
        raise TelegramInitDataError("AUTH_DATE_IN_FUTURE")
    return auth_date


def _validate_tg_id(value: object) -> TelegramId:
    try:
        return TelegramId.from_provider(value)
    except InvalidTelegramId as exc:
        raise TelegramInitDataError("TG_ID_INVALID") from exc


def _build_replay_key(value: object) -> str:
    if not isinstance(value, str):
        raise TelegramInitDataError("HASH_INVALID")
    if _HASH_PATTERN.fullmatch(value) is None:
        raise TelegramInitDataError("HASH_INVALID")
    payload = _REPLAY_NAMESPACE + value.lower().encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def _safe_profile_photo_url(value: object) -> str | None:
    """Вернуть только безопасный для браузера HTTPS URL фотографии профиля.

    Необязательный URL берётся из уже проверенного подписью Telegram user object.
    Некорректные presentation metadata не должны блокировать аутентификацию.
    """
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate or len(candidate) > 2048:
        return None
    if any(ord(ch) < 32 for ch in candidate):
        return None
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return None
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        return None
    if parsed.username is not None or parsed.password is not None:
        return None
    return candidate


class TelegramInitDataAdapter:
    """Преобразовать проверенный initData в VerifiedIdentity."""

    provider = AuthProvider.TELEGRAM

    def __init__(
        self,
        validator: TelegramInitDataValidator,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        if not callable(validator) or not callable(clock):
            raise TelegramInitDataError("ADAPTER_CONFIG_INVALID")
        self._validator = validator
        self._clock = clock

    def verify_subject(self, raw_input: object) -> str | None:
        """Выполнить provider adapter contract без side effects."""

        subject = (
            self.verify(raw_input).verified_identity.provider_subject
        )
        if not isinstance(subject, str):
            raise TelegramInitDataError("VERIFIER_RESULT_INVALID")
        return subject

    def verify(self, raw_input: object) -> VerifiedTelegramInitData:
        """Проверить raw initData и вернуть безопасный результат."""

        raw = _validate_raw_boundary(raw_input)
        try:
            parsed = self._validator(raw)
        except TelegramInitDataError:
            raise
        except Exception as exc:
            error = TelegramInitDataError(
                "SIGNATURE_OR_TTL_INVALID"
            )
            raise error from exc
        if not isinstance(parsed, Mapping):
            raise TelegramInitDataError("VERIFIER_RESULT_INVALID")

        now = _validate_clock(self._clock())
        auth_date = _validate_auth_date(
            parsed.get("auth_date"),
            now=now,
        )
        user = parsed.get("user")
        if not isinstance(user, Mapping):
            raise TelegramInitDataError("USER_REQUIRED")
        tg_id = _validate_tg_id(user.get("id"))
        replay_key = _build_replay_key(parsed.get("hash"))
        profile_photo_url = _safe_profile_photo_url(user.get("photo_url"))
        identity = finalize_verified_provider_subject(
            AuthProvider.TELEGRAM,
            str(tg_id.value),
        )
        return VerifiedTelegramInitData(
            verified_identity=identity,
            tg_id=tg_id,
            auth_date=auth_date,
            verified_at=now,
            replay_key=replay_key,
            profile_photo_url=profile_photo_url,
        )


def build_telegram_init_data_contract() -> dict[str, object]:
    """Сформировать machine contract Telegram adapter."""

    return {
        "схема": "EFHC_TELEGRAM_INIT_DATA_ADAPTER_V1",
        "цикл": 1619,
        "provider": AuthProvider.TELEGRAM.value,
        "проверки": {
            "hmac": True,
            "auth_date_required": True,
            "ttl_seconds": int(
                TELEGRAM_INIT_DATA_MAX_AGE.total_seconds()
            ),
            "future_skew_seconds": int(
                TELEGRAM_INIT_DATA_FUTURE_SKEW.total_seconds()
            ),
            "duplicate_fields_rejected": True,
            "tg_id_nominal_type": "TelegramId",
        },
        "выход": {
            "verified_identity": True,
            "provider_subject_is_decimal_tg_id": True,
            "raw_init_data_retained": False,
            "replay_key_namespaced_hash": True,
            "signed_profile_photo_url_optional": True,
        },
        "запреты": {
            "tg_id_as_global_owner": True,
            "global_id_from_tg_id": True,
            "domain_side_effects": True,
        },
    }


__all__ = [
    "TELEGRAM_INIT_DATA_FUTURE_SKEW",
    "TELEGRAM_INIT_DATA_MAX_AGE",
    "TELEGRAM_INIT_DATA_MAX_LENGTH",
    "TelegramInitDataAdapter",
    "TelegramInitDataError",
    "VerifiedTelegramInitData",
    "build_telegram_init_data_contract",
]
