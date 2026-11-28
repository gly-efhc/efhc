# backend/app/schemas/admin_sale_packages_schemas.py

from __future__ import annotations

from app.schemas.common_schemas import EfhcBaseModel
from app.schemas.id_schemas import ApiLifetimeId
from pydantic import ConfigDict, Field


class AdminSalePackageIn(EfhcBaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1, max_length=255)
    asset: str = Field(..., min_length=2, max_length=16)
    price_asset_d8: str = Field(..., min_length=1, max_length=64)
    efhc_amount_d8: str = Field(..., min_length=1, max_length=64)


class AdminSalePackageOut(EfhcBaseModel):
    model_config = ConfigDict(extra="allow")

    id: ApiLifetimeId
    title: str
    asset: str
    price_asset_d8: str
    efhc_amount_d8: str
    is_active: bool


class AdminSalePackagesOut(EfhcBaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[AdminSalePackageOut]
