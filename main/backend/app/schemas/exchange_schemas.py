# backend/app/schemas/exchange_schemas.py
# ======================================================================
# Схемы API для обмена энергии (kWh) → EFHC.
# Канон:
# - только kWh → EFHC;
# - фиксированный курс 1:1;
# - Decimal d8 наружу и внутрь (ROUND_DOWN).
# ======================================================================

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import cast

from app.deps import d8
from app.schemas.common_schemas import EfhcBaseModel
from app.schemas.id_schemas import ApiLifetimeId
from pydantic import (
    ConfigDict,
    Field,
    field_validator,
)

KWH_TO_EFHC_RATE: Decimal = Decimal("1.0")


class ExchangePreviewOut(EfhcBaseModel):
    """Предпросмотр обмена (ничего не списывает)."""

    ok: bool = Field(
        ...,
        description="Готовность к обмену (true — можно обменять)",
    )
    available_kwh: Decimal = Field(
        ...,
        description="Доступная к обмену энергия, kWh (Decimal d8)",
    )
    max_exchangeable_kwh: Decimal = Field(
        ...,
        description="Максимум к обмену сейчас, kWh (Decimal d8)",
    )
    rate_kwh_to_efhc: Decimal = Field(
        KWH_TO_EFHC_RATE,
        description="Фиксированный курс 1.0 (kWh→EFHC)",
    )
    detail: str = Field(
        "",
        description="Подсказка/причина",
    )

    model_config = ConfigDict(extra="ignore")

    _FIELDS = (
        "available_kwh",
        "max_exchangeable_kwh",
        "rate_kwh_to_efhc",
    )

    @field_validator(*_FIELDS, mode="before")
    def _q8(cls, v: Decimal) -> Decimal:
        return cast(Decimal, d8(v))


class ExchangeConvertIn(EfhcBaseModel):
    """Вход POST обмена: сколько kWh обменять."""

    amount_kwh: Decimal = Field(
        ...,
        gt=Decimal("0"),
        max_digits=30,
        decimal_places=10,
        description="Положительное kWh (>0), округляется вниз до d8",
    )
    client_nonce: str | None = Field(
        None,
        min_length=1,
        max_length=128,
        description="Опциональный нонс (не заменяет Idempotency-Key)",
    )

    model_config = ConfigDict(extra="ignore")

    @field_validator("amount_kwh", mode="before")
    def _q8_amount(cls, v: Decimal) -> Decimal:
        return cast(Decimal, d8(v))


class ExchangeHistoryItemOut(EfhcBaseModel):
    """Элемент истории обменов пользователя."""

    id: ApiLifetimeId = Field(..., description="ID записи")
    created_at: datetime = Field(
        ...,
        description="Время записи (UTC)",
    )
    direction: str = Field(
        ...,
        description="Направление (обычно 'credit')",
    )
    reason: str = Field(
        ...,
        description="Причина/тип операции",
    )
    amount_kwh: Decimal = Field(
        ...,
        description="Списанная энергия, kWh (Decimal d8)",
    )
    amount_efhc: Decimal = Field(
        ...,
        description="Начисленные EFHC (Decimal d8)",
    )
    idempotency_key: str | None = Field(
        None,
        description="Идемпотентный ключ, если применялся",
    )
    meta: str | None = Field(
        None,
        description="Доп. сведения",
    )

    model_config = ConfigDict(extra="ignore")

    @field_validator("amount_kwh", "amount_efhc", mode="before")
    def _q8_amounts(cls, v: Decimal) -> Decimal:
        return cast(Decimal, d8(v))
