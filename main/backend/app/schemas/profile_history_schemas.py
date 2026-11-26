"""Wire-схемы единой истории профиля."""

from __future__ import annotations

from app.schemas.id_schemas import ApiLifetimeId
from pydantic import BaseModel, Field


class ProfileHistoryItemOut(BaseModel):
    """Одна логическая операция общего профиля."""

    id: ApiLifetimeId
    source: str = Field(..., max_length=32)
    kind: str = Field(..., max_length=64)
    occurred_at: str
    executed_at: str | None = Field(
        default=None,
        description="UTC execution time recorded by the underlying operation, when executed.",
    )
    panel_public_id: str | None = Field(default=None, pattern=r"^PNL-[0-9]{8}$")
    status: str | None = None
    direction: str | None = None
    balance_type: str | None = None
    amount_efhc: str | None = None
    amount_asset: str | None = None
    asset: str | None = None
    reason: str | None = None


class ProfileHistoryPageOut(BaseModel):
    """Одна глобально упорядоченная keyset-страница, максимум 50 операций."""

    items: list[ProfileHistoryItemOut]
    next_cursor: str | None = None
    page_size: int = 50


__all__ = ["ProfileHistoryItemOut", "ProfileHistoryPageOut"]
