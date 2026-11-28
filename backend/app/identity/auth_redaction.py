"""Security/redaction skeleton для auth diagnostics EFHC."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Final

from app.identity.auth_context import AuthContext
from app.identity.auth_errors import AuthProviderError
from app.identity.auth_provider import AuthProvider
from app.identity.identity_registry import (
    CANONICAL_PROVIDER_SUBJECT_FIELDS,
)
from app.identity.types import GlobalId, format_global_id
from app.identity.verified_identity import VerifiedIdentity

AUTH_REDACTION_MASK: Final[str] = "<redacted>"
AUTH_PROVIDER_SUBJECT_FIELDS: Final[frozenset[str]] = frozenset(
    CANONICAL_PROVIDER_SUBJECT_FIELDS.values()
)
AUTH_SENSITIVE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "authorization",
        "cookie",
        "set-cookie",
        "x-telegram-init-data",
        "init_data",
        "initdata",
        "raw_init_data",
        "raw_input",
        "provider_subject",
        "session_id",
        "session_token",
        "access_token",
        "refresh_token",
        "id_token",
        "client_secret",
        "challenge",
        "nonce",
        "ton_proof",
        "wallet_proof",
        "proof",
        "proof_envelope",
        "signature",
        "private_key",
        "seed",
        "mnemonic",
        "password",
        "secret",
        "token",
    }
    | set(AUTH_PROVIDER_SUBJECT_FIELDS)
)
_MAX_DIAGNOSTIC_DEPTH: Final[int] = 8
_MAX_DIAGNOSTIC_ITEMS: Final[int] = 64
_PROVIDER_SUBJECT_ASSIGNMENT_PATTERN: Final[str] = "|".join(
    re.escape(item)
    for item in sorted(AUTH_PROVIDER_SUBJECT_FIELDS, key=len, reverse=True)
)
_SENSITIVE_ASSIGNMENT_RE: Final[re.Pattern[str]] = re.compile(
    rf"(?i)\b(authorization|cookie|init_?data|provider_subject|"
    rf"{_PROVIDER_SUBJECT_ASSIGNMENT_PATTERN}|"
    r"session_(?:id|token)|access_token|refresh_token|id_token|"
    r"client_secret|challenge|nonce|ton_proof|wallet_proof|proof|"
    r"signature|private_key|seed|mnemonic|password|secret|token)"
    r"\b\s*([=:])\s*([^\s,;]+)"
)
_BEARER_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"
)


def _redact_text(value: str) -> str:
    """Удалить credential patterns из диагностического текста."""

    redacted = _SENSITIVE_ASSIGNMENT_RE.sub(
        lambda item: (
            f"{item.group(1)}{item.group(2)}{AUTH_REDACTION_MASK}"
        ),
        value,
    )
    return _BEARER_RE.sub(
        f"Bearer {AUTH_REDACTION_MASK}",
        redacted,
    )


def redact_auth_diagnostic(
    value: object,
    *,
    field_name: str | None = None,
    _depth: int = 0,
) -> object:
    """Рекурсивно сформировать безопасное diagnostic value."""

    if field_name and field_name.lower() in AUTH_SENSITIVE_FIELDS:
        return AUTH_REDACTION_MASK
    if _depth >= _MAX_DIAGNOSTIC_DEPTH:
        return "<depth-limit>"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, AuthProvider):
        return value.value
    if isinstance(value, GlobalId):
        return str(format_global_id(value))
    if isinstance(value, VerifiedIdentity):
        return {
            "provider": value.provider.value,
            "provider_subject": AUTH_REDACTION_MASK,
        }
    if isinstance(value, AuthContext):
        return {
            "global_id": str(format_global_id(value.global_id)),
            "provider": value.provider.value,
            "provider_subject": AUTH_REDACTION_MASK,
            "roles": sorted(value.roles),
            "session_id": (
                AUTH_REDACTION_MASK if value.session_id else None
            ),
        }
    if isinstance(value, AuthProviderError):
        return value.as_dict()
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= _MAX_DIAGNOSTIC_ITEMS:
                result["<truncated>"] = True
                break
            safe_key = str(key)
            result[safe_key] = redact_auth_diagnostic(
                item,
                field_name=safe_key,
                _depth=_depth + 1,
            )
        return result
    if is_dataclass(value) and not isinstance(value, type):
        result = {}
        for index, field in enumerate(fields(value)):
            if index >= _MAX_DIAGNOSTIC_ITEMS:
                result["<truncated>"] = True
                break
            result[field.name] = redact_auth_diagnostic(
                getattr(value, field.name),
                field_name=field.name,
                _depth=_depth + 1,
            )
        return result
    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        return [
            redact_auth_diagnostic(item, _depth=_depth + 1)
            for item in value[:_MAX_DIAGNOSTIC_ITEMS]
        ]
    return f"<{type(value).__name__}>"


def build_auth_diagnostic(
    *,
    code: str,
    outcome: str,
    provider: AuthProvider | None = None,
    details: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Построить bounded machine diagnostic без raw credentials."""

    if not isinstance(code, str) or not code.isascii() or not code:
        raise ValueError("Код auth diagnostic недействителен")
    if (
        not isinstance(outcome, str)
        or not outcome.isascii()
        or not outcome
    ):
        raise ValueError("Результат auth diagnostic недействителен")
    return {
        "код": code,
        "результат": outcome,
        "provider": provider.value if provider else None,
        "детали": redact_auth_diagnostic(details or {}),
    }
