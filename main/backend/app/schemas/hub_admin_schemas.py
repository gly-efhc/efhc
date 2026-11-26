from __future__ import annotations

from datetime import datetime

from app.schemas.common_schemas import EfhcBaseModel
from app.schemas.id_schemas import ApiLifetimeId
from pydantic import Field


class HubLinkAdminOut(EfhcBaseModel):
    id: ApiLifetimeId
    code: str
    title: str
    subtitle: str | None = None
    url: str
    target_kind: str
    open_mode: str
    sort_order: int
    is_active: bool
    icon_key: str | None = None
    created_at: datetime
    updated_at: datetime


class HubLinkAdminCreateIn(EfhcBaseModel):
    code: str = Field(..., min_length=1, max_length=64)
    title: str = Field(..., min_length=1, max_length=128)
    subtitle: str | None = Field(None, max_length=2000)
    url: str = Field(..., min_length=1, max_length=1024)
    target_kind: str = Field(..., min_length=1, max_length=32)
    open_mode: str = Field(..., min_length=1, max_length=32)
    sort_order: int = Field(100, ge=0, le=1000000)
    is_active: bool = True
    icon_key: str | None = Field(None, max_length=64)


class HubLinkAdminUpdateIn(EfhcBaseModel):
    title: str = Field(..., min_length=1, max_length=128)
    subtitle: str | None = Field(None, max_length=2000)
    url: str = Field(..., min_length=1, max_length=1024)
    target_kind: str = Field(..., min_length=1, max_length=32)
    open_mode: str = Field(..., min_length=1, max_length=32)
    sort_order: int = Field(..., ge=0, le=1000000)
    is_active: bool
    icon_key: str | None = Field(None, max_length=64)


class HubLinkAdminToggleIn(EfhcBaseModel):
    is_active: bool


class HubLinkAdminReorderItem(EfhcBaseModel):
    id: ApiLifetimeId = Field(..., ge=1)
    sort_order: int = Field(..., ge=0, le=1000000)


class HubLinkAdminReorderIn(EfhcBaseModel):
    items: list[HubLinkAdminReorderItem] = Field(
        ..., min_length=1, max_length=200
    )


class HubSupportLinkAdminCreateIn(EfhcBaseModel):
    code: str = Field(..., min_length=9, max_length=64)
    title: str = Field(..., min_length=1, max_length=128)
    subtitle: str | None = Field(None, max_length=2000)
    url: str = Field(..., min_length=1, max_length=1024)
    sort_order: int = Field(100, ge=0, le=1000000)
    is_active: bool = True
    icon_key: str | None = Field(None, max_length=64)


class HubSupportLinkAdminUpdateIn(EfhcBaseModel):
    title: str = Field(..., min_length=1, max_length=128)
    subtitle: str | None = Field(None, max_length=2000)
    url: str = Field(..., min_length=1, max_length=1024)
    sort_order: int = Field(..., ge=0, le=1000000)
    is_active: bool
    icon_key: str | None = Field(None, max_length=64)
