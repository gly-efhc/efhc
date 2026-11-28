# backend/app/schemas/ads_schemas.py
# ----------------------------------------------------------------------
# Pydantic v2 схемы для Ads API.
# ----------------------------------------------------------------------

from __future__ import annotations

from app.schemas.common_schemas import EfhcBaseModel
from app.schemas.id_schemas import ApiLifetimeId
from typing import Any

from pydantic import BaseModel, Field


class AdOut(EfhcBaseModel):
    id: ApiLifetimeId
    title: str
    status: str
    weight: int = Field(ge=1)


class AdSessionCreateIn(BaseModel):
    task_code: str = Field(min_length=1, max_length=64)


class AdFallbackIn(BaseModel):
    reason: str = Field(default="PROVIDER_ERROR", max_length=64)


class AdClientEventIn(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)


class AdTelemetryIn(BaseModel):
    event_type: str = Field(min_length=1, max_length=48)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AdSessionOut(BaseModel):
    session_id: str
    task_code: str
    status: str
    primary_provider: str | None = None
    actual_provider: str | None = None
    provider: dict[str, Any] | None = None
    reward_efhcb: str
    expires_at: str
    failure_code: str | None = None
    fallback_count: int
    verification_level: str | None = None
    estimated_revenue_usd: str | None = None
    actual_revenue_usd: str | None = None
    rewarded: bool
    test_mode: bool


# Compatibility schema старого /ads/slot.
class AdSlotOut(BaseModel):
    provider: str
    task_code: str
    global_id: str
    bonus_efhc: str
    token: str | None = None
    expires_at: str | None = None
    min_view_sec: int | None = None
    placement_id: str | None = None


class AdCallbackResultOut(BaseModel):
    ok: bool
    provider: str
    task_code: str
    provider_ref: str
    bonus_efhc: str
    replayed: bool = False
