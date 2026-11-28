# backend/app/schemas/ads_schemas.py
# ----------------------------------------------------------------------
# Pydantic v2 схемы для Ads API.
# ----------------------------------------------------------------------

from __future__ import annotations

from app.schemas.common_schemas import EfhcBaseModel
from app.schemas.id_schemas import ApiLifetimeId
from pydantic import Field


class AdOut(EfhcBaseModel):
    id: ApiLifetimeId
    title: str
    status: str
    weight: int = Field(ge=1)
