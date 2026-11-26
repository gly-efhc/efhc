"""backend/app/schemas/skins_schemas.py

Pydantic схемы домена «Skins».
"""

from __future__ import annotations

from datetime import datetime

from app.schemas.common_schemas import EfhcBaseModel
from pydantic import Field


class SkinItem(EfhcBaseModel):
    skin_id: int = Field(..., ge=1)
    title: str
    price_efhc: str
    asset_path: str


class SkinsCatalogOut(EfhcBaseModel):
    items: list[SkinItem]


class MySkin(EfhcBaseModel):
    skin_id: int = Field(..., ge=1)
    purchased_at: datetime


class SkinsMyOut(EfhcBaseModel):
    active_skin_id: int = Field(..., ge=1)
    owned: list[MySkin]


class SkinSwitcherItem(EfhcBaseModel):
    skin_id: int = Field(..., ge=1, le=12)
    title: str
    asset_path: str
    is_unlocked: bool
    is_active: bool


class SkinSwitcherOut(EfhcBaseModel):
    current_level: int = Field(..., ge=1, le=12)
    available_skin_ids: list[int]
    active_skin_id: int = Field(..., ge=1, le=12)
    items: list[SkinSwitcherItem]
