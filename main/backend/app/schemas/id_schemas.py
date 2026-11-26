"""Wire-контракты PostgreSQL lifetime identifiers.

Внутри backend идентификаторы остаются Python ``int``. На JSON/OpenAPI
границе canonical representation — десятичная строка, чтобы frontend не
терял точность 64-bit PostgreSQL ``BIGINT``.
"""

from __future__ import annotations

from typing import Annotated, Final, cast

from app.identity.api_contract import GLOBAL_ID_OPENAPI_SCHEMA
from app.identity.types import (
    GlobalId,
    format_global_id,
    parse_global_id,
)
from pydantic import BeforeValidator, PlainSerializer, WithJsonSchema

POSTGRES_BIGINT_MAX: Final[int] = 9_223_372_036_854_775_807
LIFETIME_ID_OPENAPI_FORMAT: Final[str] = "efhc-lifetime-id"
LIFETIME_ID_OPENAPI_SCHEMA: Final[dict[str, object]] = {
    "type": "string",
    "title": "EFHC Lifetime ID",
    "description": (
        "Положительный PostgreSQL lifetime identifier. Canonical JSON "
        "representation — десятичная строка; legacy integer input "
        "временно принимается для обратной совместимости."
    ),
    "format": LIFETIME_ID_OPENAPI_FORMAT,
    "pattern": "^[1-9][0-9]{0,18}$",
    "minLength": 1,
    "maxLength": 19,
    "examples": ["1"],
}


def _parse_positive_bigint(value: object) -> int:
    """Нормализовать legacy integer/string input в положительный BIGINT."""

    if isinstance(value, bool):
        raise ValueError("Lifetime ID не может быть boolean")
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str):
        if not value or not value.isascii() or not value.isdigit():
            raise ValueError("Lifetime ID должен быть десятичной строкой")
        parsed = int(value, 10)
    else:
        raise ValueError("Lifetime ID должен быть integer или строкой")
    if parsed < 1 or parsed > POSTGRES_BIGINT_MAX:
        raise ValueError("Lifetime ID вне диапазона PostgreSQL BIGINT")
    return parsed


def _serialize_positive_bigint(value: int) -> str:
    """Сериализовать lifetime ID canonical decimal string."""

    return str(_parse_positive_bigint(value))


ApiLifetimeId = Annotated[
    int,
    BeforeValidator(_parse_positive_bigint),
    PlainSerializer(
        _serialize_positive_bigint,
        return_type=str,
        when_used="always",
    ),
    WithJsonSchema(LIFETIME_ID_OPENAPI_SCHEMA, mode="validation"),
    WithJsonSchema(LIFETIME_ID_OPENAPI_SCHEMA, mode="serialization"),
]
# API boundary: Python ``int`` внутри, decimal string в JSON/OpenAPI.


def _parse_database_global_id(value: object) -> int:
    """Нормализовать DB/global-id boundary без ослабления внешнего формата."""

    if isinstance(value, GlobalId):
        return cast(int, value.to_database())
    if isinstance(value, bool):
        raise ValueError("Global ID не может быть boolean")
    if isinstance(value, int):
        return cast(int, GlobalId.from_database(value).to_database())
    return cast(int, parse_global_id(value).to_database())


def _serialize_database_global_id(value: int) -> str:
    """Сериализовать DB ``global_id`` в каноническую 10-значную строку."""

    global_id = GlobalId.from_database(value)
    return str(format_global_id(global_id))


ApiDatabaseGlobalId = Annotated[
    int,
    BeforeValidator(_parse_database_global_id),
    PlainSerializer(
        _serialize_database_global_id,
        return_type=str,
        when_used="always",
    ),
    WithJsonSchema(GLOBAL_ID_OPENAPI_SCHEMA, mode="validation"),
    WithJsonSchema(GLOBAL_ID_OPENAPI_SCHEMA, mode="serialization"),
]
# Compatibility boundary: DB ``int`` внутри, canonical Global ID снаружи.
