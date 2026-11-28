# backend/app/schemas/panels_schemas.py
# ======================================================================
# Схемы API для раздела «Панели».
# - листинги: CursorPage[PanelCard];
# - активация: вход/выход;
# - служебная синхронизация и краткая сводка.
# ======================================================================

from __future__ import annotations

from typing import Any, cast

from app.schemas.common_schemas import (
    BalancePair,
    CursorPage,
    EfhcBaseModel,
    IdempotencyContract,
    OkMeta,
    PanelCard,
    d8_str,
)
from pydantic import Field, field_validator

PanelsPage = CursorPage[PanelCard]


class PanelPurchaseIn(IdempotencyContract):
    """Вход активации панели(ей)."""

    quantity: int = Field(
        ...,
        gt=0,
        le=1000,
        description="Количество панелей к активации (>0)",
    )


class PanelPurchaseOut(EfhcBaseModel):
    """Результат активации панелей."""

    meta: OkMeta = Field(
        default_factory=OkMeta,
        description="Мета об успешной обработке",
    )
    purchased: int = Field(
        ...,
        description="Сколько панелей активировано в этой операции",
    )
    total_active: int = Field(
        ...,
        description="Итоговое число активных панелей у пользователя",
    )
    balances: BalancePair = Field(
        ...,
        description="Итоговые балансы (EFHC) после активации",
    )


class PanelsSyncOut(EfhcBaseModel):
    """Результат принудительной синхронизации генерации по панелям."""

    meta: OkMeta = Field(default_factory=OkMeta)
    backfilled: int = Field(
        ...,
        ge=0,
        description="Сколько панелей догнали",
    )
    errors: int = Field(
        ...,
        ge=0,
        description="Сколько ошибок возникло",
    )
    note: str | None = Field(
        None,
        description="Короткая приметка по результату",
    )


class PanelsSummaryOut(EfhcBaseModel):
    """Короткая сводка по панелям пользователя."""

    active_count: int = Field(
        ...,
        description="Число активных панелей",
    )
    total_generated_by_panels: str = Field(
        ...,
        description="Суммарная генерация по панелям (кВт·ч), str d8",
    )
    nearest_expire_at: str | None = Field(
        None,
        description="ISO дата ближайшего истечения срока",
    )

    @field_validator("total_generated_by_panels", mode="before")
    def _norm_q8(cls, v: Any) -> str:
        return cast(str, d8_str(v))
