# backend/app/schemas/user_schemas.py
# ----------------------------------------------------------------------
# Pydantic-схемы для user_routes:
# - профиль/балансы,
# - сводка панелей,
# - предпросмотр обмена.
# Все числа наружу: str(8) через d8_str.
# ----------------------------------------------------------------------

from __future__ import annotations

from typing import Any

from app.identity.api_contract import ApiExternalGlobalId
from app.schemas.common_schemas import EfhcBaseModel, d8_str
from pydantic import Field, field_validator


class UserProfileOut(EfhcBaseModel):
    """Профиль: балансы и ставки."""

    global_id: ApiExternalGlobalId = Field(
        ...,
        description="Главный идентификатор аккаунта EFHC.",
    )
    username: str | None = Field(
        None,
        description="Никнейм Telegram (если есть)",
    )
    is_vip: bool = Field(
        ...,
        description="VIP-статус (NFT в кошельке)",
    )

    main_balance: str = Field(
        ...,
        description="Основной баланс EFHC, str(8)",
    )
    bonus_balance: str = Field(
        ...,
        description="Бонусный баланс EFHC, str(8)",
    )

    available_kwh: str = Field(
        ...,
        description="Доступная энергия, kWh, str(8)",
    )
    total_generated_kwh: str = Field(
        ...,
        description="Всего, kWh, str(8)",
    )

    gen_per_sec_base_kwh: str = Field(
        ...,
        description="Ставка без VIP, kWh/сек, str(8)",
    )
    gen_per_sec_vip_kwh: str = Field(
        ...,
        description="Ставка VIP, kWh/сек, str(8)",
    )

    @field_validator(
        "main_balance",
        "bonus_balance",
        "available_kwh",
        "total_generated_kwh",
        "gen_per_sec_base_kwh",
        "gen_per_sec_vip_kwh",
        mode="before",
    )
    def _norm_q8(cls, v: Any) -> str:
        return str(d8_str(v))


class PanelsSummaryOut(EfhcBaseModel):
    """Сводка по панелям для UI."""

    active_count: int = Field(
        ...,
        description="Число активных панелей",
    )
    total_generated_by_panels: str = Field(
        ...,
        description="Генерация панелей, kWh, str(8)",
    )
    nearest_expire_at: str | None = Field(
        None,
        description="ISO истечения (или None)",
    )

    @field_validator("total_generated_by_panels", mode="before")
    def _norm_q8(cls, v: Any) -> str:
        return str(d8_str(v))
