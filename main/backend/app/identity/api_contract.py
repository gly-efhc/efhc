"""Строгий Pydantic/OpenAPI-контракт канонического ``GlobalId``.

Контракт используется действующими routes и DTO. Внешний ``global_id``
всегда передаётся строкой из десяти ASCII-цифр; provider identifiers не
могут быть неявно приведены к нему.
"""

from __future__ import annotations

from typing import Annotated, Final

from app.identity.types import (
    ExternalGlobalId,
    GlobalId,
    InvalidGlobalId,
    TelegramId,
    format_global_id,
    parse_global_id,
)
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    WithJsonSchema,
)

GLOBAL_ID_OPENAPI_FORMAT: Final[str] = "efhc-global-id"
GLOBAL_ID_OPENAPI_EXAMPLE: Final[str] = "0000000001"
GLOBAL_ID_OPENAPI_SCHEMA: Final[dict[str, object]] = {
    "type": "string",
    "title": "EFHC Global ID",
    "description": (
        "Главный идентификатор единого аккаунта EFHC: ровно десять "
        "ASCII-цифр; 0000000000 запрещён."
    ),
    "format": GLOBAL_ID_OPENAPI_FORMAT,
    "pattern": "^[0-9]{10}$",
    "minLength": 10,
    "maxLength": 10,
    "examples": [GLOBAL_ID_OPENAPI_EXAMPLE],
}


def _validate_pydantic_global_id(value: object) -> GlobalId:
    """Принять существующий ``GlobalId`` или строгую строку."""

    if isinstance(value, GlobalId):
        return value
    if isinstance(value, TelegramId):
        raise InvalidGlobalId(
            "TelegramId нельзя использовать как EFHC GlobalId"
        )
    return parse_global_id(value)


def _serialize_pydantic_global_id(value: GlobalId) -> str:
    """Сериализовать ``GlobalId`` только десятизначной строкой."""

    if not isinstance(value, GlobalId):
        raise InvalidGlobalId(
            "PydanticGlobalId требует проверенный GlobalId"
        )
    return str(format_global_id(value))


ApiExternalGlobalId = Annotated[
    ExternalGlobalId,
    WithJsonSchema(GLOBAL_ID_OPENAPI_SCHEMA, mode="validation"),
    WithJsonSchema(GLOBAL_ID_OPENAPI_SCHEMA, mode="serialization"),
]
"""FastAPI-safe scalar contract для path и query input."""


PydanticGlobalId = Annotated[
    GlobalId,
    BeforeValidator(_validate_pydantic_global_id),
    PlainSerializer(
        _serialize_pydantic_global_id,
        return_type=str,
        when_used="always",
    ),
    WithJsonSchema(GLOBAL_ID_OPENAPI_SCHEMA, mode="validation"),
    WithJsonSchema(GLOBAL_ID_OPENAPI_SCHEMA, mode="serialization"),
]
"""Pydantic boundary: хранит ``GlobalId``, выдаёт строку."""


class GlobalIdRequest(BaseModel):
    """Строгий request envelope канонического аккаунта EFHC."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    global_id: PydanticGlobalId = Field(
        ...,
        description=(
            "Канонический EFHC global_id в форме десяти ASCII-цифр."
        ),
        examples=[GLOBAL_ID_OPENAPI_EXAMPLE],
    )


class GlobalIdResponse(BaseModel):
    """Строгий response envelope канонического аккаунта EFHC."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    global_id: PydanticGlobalId = Field(
        ...,
        description=(
            "Канонический EFHC global_id в форме десяти ASCII-цифр."
        ),
        examples=[GLOBAL_ID_OPENAPI_EXAMPLE],
    )

    @classmethod
    def from_global_id(
        cls,
        global_id: GlobalId,
    ) -> GlobalIdResponse:
        """Построить ответ только из проверенного ``GlobalId``."""

        if not isinstance(global_id, GlobalId):
            raise InvalidGlobalId(
                "GlobalIdResponse требует проверенный GlobalId"
            )
        return cls(global_id=global_id)
