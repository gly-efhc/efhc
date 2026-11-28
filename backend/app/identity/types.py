"""Канонические provider-independent типы идентичности EFHC.

``GlobalId`` — главный неизменяемый идентификатор единого аккаунта.
``TelegramId`` — внешний идентификатор Telegram provider. Типы нельзя
неявно преобразовывать друг в друга даже при одинаковом числе.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Annotated, Final, TypeGuard

from pydantic import AfterValidator, Strict, StringConstraints

GLOBAL_ID_MIN: Final[int] = 1
GLOBAL_ID_MAX: Final[int] = 9_999_999_999
GLOBAL_ID_DIGITS: Final[int] = 10
GLOBAL_ID_PATTERN_TEXT: Final[str] = r"^[0-9]{10}$"
GLOBAL_ID_PATTERN: Final[re.Pattern[str]] = re.compile(
    GLOBAL_ID_PATTERN_TEXT
)
TG_ID_MIN: Final[int] = 1
TG_ID_MAX: Final[int] = 9_007_199_254_740_991


class IdentityValueError(ValueError):
    """Базовая машинно-различимая ошибка identity-контракта."""

    field: str = "identity"
    default_code: str = "identity.invalid"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code or self.default_code

    def as_dict(self) -> dict[str, str]:
        """Вернуть стабильный payload без внутренних данных."""

        return {
            "поле": self.field,
            "код": self.code,
            "сообщение": str(self),
        }


class InvalidGlobalId(IdentityValueError):
    """Ошибка нарушения контракта глобального аккаунта EFHC."""

    field = "global_id"
    default_code = "global_id.invalid"


class InvalidTelegramId(IdentityValueError):
    """Ошибка нарушения контракта Telegram provider identifier."""

    field = "tg_id"
    default_code = "tg_id.invalid"


class GlobalIdDisplay(str):
    """Строгое внешнее представление из десяти ASCII-цифр."""

    def __new__(cls, value: str) -> GlobalIdDisplay:
        if not isinstance(value, str):
            raise InvalidGlobalId(
                "global_id display должен быть строкой",
                code="global_id.display_type",
            )
        if GLOBAL_ID_PATTERN.fullmatch(value) is None:
            raise InvalidGlobalId(
                "global_id display должен содержать ровно десять "
                "ASCII-цифр",
                code="global_id.display_format",
            )
        if value == "0" * GLOBAL_ID_DIGITS:
            raise InvalidGlobalId(
                "global_id 0000000000 запрещён",
                code="global_id.zero_forbidden",
            )
        return str.__new__(cls, value)


@dataclass(frozen=True, slots=True, order=True)
class GlobalId:
    """Проверенный идентификатор единого глобального аккаунта EFHC."""

    value: int

    def __post_init__(self) -> None:
        _validate_global_id_integer(self.value)

    @classmethod
    def from_database(cls, value: object) -> GlobalId:
        """Создать ``GlobalId`` из строгого целого значения БД."""

        if isinstance(value, cls):
            return value
        return cls(_validate_global_id_integer(value))

    @classmethod
    def from_external(cls, value: object) -> GlobalId:
        """Создать ``GlobalId`` из канонической внешней строки."""

        display = validate_global_id_display(value)
        return cls(int(display))

    @property
    def display(self) -> GlobalIdDisplay:
        """Вернуть точное десятизначное внешнее представление."""

        return GlobalIdDisplay(
            f"{self.value:0{GLOBAL_ID_DIGITS}d}"
        )

    def to_database(self) -> int:
        """Вернуть целое значение для физической BIGINT-колонки."""

        return self.value

    def __int__(self) -> int:
        return self.value

    def __index__(self) -> int:
        return self.value

    def __str__(self) -> str:
        return str(self.display)


@dataclass(frozen=True, slots=True, order=True)
class TelegramId:
    """Проверенный внешний идентификатор Telegram provider."""

    value: int

    def __post_init__(self) -> None:
        _validate_tg_id_integer(self.value)

    @classmethod
    def from_provider(cls, value: object) -> TelegramId:
        """Создать ``TelegramId`` только из provider-целого значения."""

        if isinstance(value, cls):
            return value
        return cls(_validate_tg_id_integer(value))

    def to_provider_value(self) -> int:
        """Вернуть целое значение для Telegram API."""

        return self.value

    def __int__(self) -> int:
        return self.value

    def __index__(self) -> int:
        return self.value

    def __str__(self) -> str:
        return str(self.value)


def _validate_global_id_integer(value: object) -> int:
    if isinstance(value, TelegramId):
        raise InvalidGlobalId(
            "TelegramId нельзя использовать как GlobalId",
            code="global_id.provider_mismatch",
        )
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidGlobalId(
            "global_id должен быть целым числом",
            code="global_id.type",
        )
    if not GLOBAL_ID_MIN <= value <= GLOBAL_ID_MAX:
        raise InvalidGlobalId(
            "global_id должен находиться в диапазоне 1–9999999999",
            code="global_id.range",
        )
    return value


def _validate_tg_id_integer(value: object) -> int:
    if isinstance(value, GlobalId):
        raise InvalidTelegramId(
            "GlobalId нельзя использовать как TelegramId",
            code="tg_id.global_mismatch",
        )
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidTelegramId(
            "tg_id должен быть целым числом",
            code="tg_id.type",
        )
    if not TG_ID_MIN <= value <= TG_ID_MAX:
        raise InvalidTelegramId(
            "tg_id должен находиться в безопасном диапазоне "
            "1–9007199254740991",
            code="tg_id.range",
        )
    return value


def validate_global_id(value: object) -> GlobalId:
    """Проверить значение БД либо существующий ``GlobalId``."""

    return GlobalId.from_database(value)


def validate_tg_id(value: object) -> TelegramId:
    """Проверить внешний Telegram identifier."""

    return TelegramId.from_provider(value)


def validate_global_id_display(value: object) -> GlobalIdDisplay:
    """Проверить строгое десятизначное внешнее представление."""

    if isinstance(value, GlobalIdDisplay):
        return value
    if not isinstance(value, str):
        raise InvalidGlobalId(
            "внешний global_id должен быть строкой",
            code="global_id.external_type",
        )
    return GlobalIdDisplay(value)


def format_global_id(value: GlobalId) -> GlobalIdDisplay:
    """Форматировать проверенный ``GlobalId`` для API и UI."""

    if not isinstance(value, GlobalId):
        raise InvalidGlobalId(
            "format_global_id требует проверенный GlobalId",
            code="global_id.nominal_required",
        )
    return value.display


def format_tg_id(value: TelegramId) -> str:
    """Форматировать проверенный ``TelegramId`` строго строкой."""

    if not isinstance(value, TelegramId):
        raise InvalidTelegramId(
            "format_tg_id требует проверенный TelegramId",
            code="tg_id.nominal_required",
        )
    return str(value.value)


def parse_global_id(value: object) -> GlobalId:
    """Разобрать строгий десятизначный внешний global_id."""

    return GlobalId.from_external(value)


def global_id_from_database(value: object) -> GlobalId:
    """Явная граница БД: строгое целое значение → ``GlobalId``."""

    return GlobalId.from_database(value)


def global_id_to_database(value: GlobalId) -> int:
    """Явная граница БД: ``GlobalId`` → BIGINT value."""

    if not isinstance(value, GlobalId):
        raise InvalidGlobalId(
            "global_id_to_database требует проверенный GlobalId",
            code="global_id.nominal_required",
        )
    return value.to_database()


def tg_id_from_provider(value: object) -> TelegramId:
    """Явная provider-граница: Telegram integer → ``TelegramId``."""

    return TelegramId.from_provider(value)


def tg_id_to_provider(value: TelegramId) -> int:
    """Явная provider-граница: ``TelegramId`` → Telegram integer."""

    if not isinstance(value, TelegramId):
        raise InvalidTelegramId(
            "tg_id_to_provider требует проверенный TelegramId",
            code="tg_id.nominal_required",
        )
    return value.to_provider_value()


def is_global_id(value: object) -> TypeGuard[GlobalId]:
    """Проверить, что значение уже является ``GlobalId``."""

    return isinstance(value, GlobalId)


def is_tg_id(value: object) -> TypeGuard[TelegramId]:
    """Проверить, что значение является ``TelegramId``."""

    return isinstance(value, TelegramId)


def _validate_external_global_id(value: str) -> str:
    parse_global_id(value)
    return value


ExternalGlobalId = Annotated[
    str,
    Strict(),
    StringConstraints(
        min_length=GLOBAL_ID_DIGITS,
        max_length=GLOBAL_ID_DIGITS,
        pattern=GLOBAL_ID_PATTERN_TEXT,
    ),
    AfterValidator(_validate_external_global_id),
]
"""Строгий Pydantic-ready внешний контракт global_id."""

def _validate_external_tg_id(value: int) -> int:
    """Проверить integer-контракт Telegram provider для Pydantic."""

    return tg_id_to_provider(tg_id_from_provider(value))


ExternalTelegramId = Annotated[
    int,
    Strict(),
    AfterValidator(_validate_external_tg_id),
]
"""Строгий Pydantic-ready integer-контракт Telegram ID."""

