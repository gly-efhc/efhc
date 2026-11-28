# backend/app/schemas/common_schemas.py
# ======================================================================
# Базовые Pydantic-схемы EFHC Bot:
# - курсорная пагинация;
# - сериализация Decimal наружу как строка d8 (ROUND_DOWN);
# - типовые формы ok/error.
# ======================================================================

from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal, InvalidOperation
from typing import Any, Generic, TypeVar  # noqa: E402

from app.schemas.id_schemas import ApiLifetimeId  # noqa: E402
from pydantic import (  # noqa: E402
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_serializer,
)

ZERO_D8 = Decimal("0.00000000")
EFHC_DECIMALS: int = 8
_Q8 = Decimal(1).scaleb(-EFHC_DECIMALS)  # Decimal("0.00000001")


def utcnow_iso() -> str:
    """UTC now as ISO-8601 string."""
    return datetime.now(UTC).isoformat()


def _to_decimal_q8(x: Any) -> Decimal:
    """Coerce to Decimal and quantize to d8 using ROUND_DOWN."""
    try:
        d = Decimal(str(x))
    except (InvalidOperation, ValueError, TypeError) as err:
        raise ValueError("Некорректное числовое значение") from err
    return d.quantize(_Q8, rounding=ROUND_DOWN)


def d8_str(x: Any) -> str:
    """Serialize as Decimal d8 string (ROUND_DOWN)."""
    d = _to_decimal_q8(x)
    # str(Decimal('0E-8')) -> '0E-8' (не канон).
    # Канон: всегда фиксированный формат d8.
    return format(d, "f")


def _serialize_decimals(value: Any) -> Any:
    """Recursively convert Decimal values to canonical d8 strings."""
    if isinstance(value, Decimal):
        return d8_str(value)
    if isinstance(value, dict):
        return {
            key: _serialize_decimals(val) for key, val in value.items()
        }
    if isinstance(value, list):
        return [_serialize_decimals(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_serialize_decimals(v) for v in value)
    return value


class EfhcBaseModel(BaseModel):
    """Base model: serialize Decimal as str d8 in JSON outputs."""

    model_config = ConfigDict()

    @model_serializer(mode="wrap")
    def _serialize_model(self, handler):
        return _serialize_decimals(handler(self))


class ErrorResponse(BaseModel):
    """Стандартная форма ошибки для фронтенда."""

    code: str = Field(
        ...,
        description="Короткий код ошибки (snake-case)",
    )
    detail: str = Field(
        ...,
        description="Человеко-читаемое описание проблемы",
    )


class OkMeta(BaseModel):
    """Мета об успешной обработке."""

    ok: bool = Field(True, description="Флаг успешной операции")
    server_time: str = Field(
        default_factory=utcnow_iso,
        description="UTC время формирования ответа (ISO-8601)",
    )


T = TypeVar("T")


class CursorPage(BaseModel, Generic[T]):
    """Курсорная страница списка (без OFFSET)."""

    items: list[T] = Field(
        ...,
        description="Элементы текущей страницы",
    )
    next_cursor: str | None = Field(
        None,
        description="Курсор следующей страницы или None",
    )
    etag: str | None = Field(
        None,
        description="Опциональный ETag ответа",
    )
    server_time: str = Field(
        default_factory=utcnow_iso,
        description="UTC время формирования ответа (ISO-8601)",
    )


class MoneyStr(BaseModel):
    """Денежное значение EFHC как строка d8."""

    value: str = Field(
        ...,
        description="Строка с 8 знаками после запятой",
    )

    @field_validator("value", mode="before")
    def _norm(cls, v: Any) -> str:
        return d8_str(v)


class EnergyStr(BaseModel):
    """Энергия (кВт·ч) как строка d8."""

    value: str = Field(
        ...,
        description="КВт·ч строкой с 8 знаками",
    )

    @field_validator("value", mode="before")
    def _norm(cls, v: Any) -> str:
        return d8_str(v)


class BalancePair(BaseModel):
    """Пара балансов пользователя (main/bonus) как строки d8."""

    main_balance: str = Field(
        ...,
        description="Основной баланс EFHC (str d8)",
    )
    bonus_balance: str = Field(
        ...,
        description="Бонусный баланс EFHC (str d8)",
    )

    @field_validator("main_balance", "bonus_balance", mode="before")
    def _norm(cls, v: Any) -> str:
        return d8_str(v)


class EnergyPair(BaseModel):
    """Раздельный учёт энергии как строки d8."""

    total_generated_kwh: str = Field(
        ...,
        description="Всего сгенерировано (кВт·ч), str d8",
    )
    available_kwh: str = Field(
        ...,
        description="Доступно для обмена (кВт·ч), str d8",
    )

    _FIELDS = ("total_generated_kwh", "available_kwh")

    @field_validator(*_FIELDS, mode="before")
    def _norm(cls, v: Any) -> str:
        return d8_str(v)


class VipFlags(BaseModel):
    """Мини-набор флагов статуса пользователя."""

    is_vip: bool = Field(
        ...,
        description="VIP по наличию NFT из коллекции",
    )


class StrictIn(BaseModel):
    """База для входящих DTO.

    Запрещает неизвестные поля (mass assignment).
    """

    model_config = ConfigDict(extra="forbid")


class IdempotencyContract(StrictIn):
    """Контракт идемпотентности для денежных POST."""

    client_nonce: str | None = Field(
        None,
        description="Опциональный нонс клиента для трассировки",
    )


class PanelCard(BaseModel):
    """Карточка панели (активной/архивной)."""

    panel_id: ApiLifetimeId = Field(..., description="ID панели")
    is_active: bool = Field(..., description="Активность")
    created_at: str = Field(..., description="ISO-время создания")
    expires_at: str | None = Field(
        None,
        description="ISO-время истечения (для активной)",
    )
    closed_at: str | None = Field(
        None,
        description="ISO-время закрытия (для архивной)",
    )
    base_gen_per_sec: str = Field(
        ...,
        description="Ставка генерации, кВт·ч/сек (str d8)",
    )
    generated_kwh: str = Field(
        ...,
        description="Сгенерировано панелью, кВт·ч (str d8)",
    )

    @field_validator("base_gen_per_sec", "generated_kwh", mode="before")
    def _norm_decimals(cls, v: Any) -> str:
        return d8_str(v)


class ExchangePreviewDTO(BaseModel):
    """Предпросмотр обмена kWh→EFHC (ничего не списывает)."""

    ok: bool = Field(..., description="Можно ли выполнить обмен")
    available_kwh: str = Field(
        ...,
        description="Доступная энергия (кВт·ч), str d8",
    )
    max_exchangeable_kwh: str = Field(
        ...,
        description="Максимум к обмену (кВт·ч), str d8",
    )
    rate_kwh_to_efhc: str = Field(
        ...,
        description="Фиксированный курс 1.00000000",
    )
    detail: str = Field(
        ...,
        description="Подсказка/причина",
    )
