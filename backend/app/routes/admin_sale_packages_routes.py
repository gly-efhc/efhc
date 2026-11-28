# backend/app/routes/admin_sale_packages_routes.py
# =====================================================================
# Admin API: EFHC sale packages (pricing для deposit_efhc).
# =====================================================================

from __future__ import annotations

from app.core.logging_core import get_logger
from app.deps import (
    get_db,
    require_admin,
    require_admin_write,
    require_idempotency_key,
)
from app.schemas.admin_sale_packages_schemas import (
    AdminSalePackageIn,
    AdminSalePackageOut,
    AdminSalePackagesOut,
)
from app.schemas.id_schemas import ApiLifetimeId
from app.services.admin.admin_sale_packages_service import list_packages
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

router = APIRouter(
    prefix="/admin/sale-packages",
    tags=["admin:sale-packages"],
)


@router.get("/", response_model=AdminSalePackagesOut)
async def admin_list_sale_packages(
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_admin),
) -> AdminSalePackagesOut:
    items = await list_packages(db)
    return AdminSalePackagesOut(items=items)


@router.post(
    "/",
    response_model=AdminSalePackageOut,
    status_code=status.HTTP_200_OK,
)
async def admin_create_sale_package(
    payload: AdminSalePackageIn,
    _auth=Depends(require_admin_write),
    idk: str = Depends(require_idempotency_key),
) -> AdminSalePackageOut:
    """Запретить запись в legacy efhc_admin sale-packages."""
    _ = (payload, idk)
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="SALE_PACKAGES_NOT_RELEASE_SSOT",
    )


@router.post(
    "/{package_id}/toggle",
    response_model=AdminSalePackageOut,
)
async def admin_toggle_sale_package(
    package_id: ApiLifetimeId,
    _auth=Depends(require_admin_write),
    idk: str = Depends(require_idempotency_key),
) -> AdminSalePackageOut:
    """Не переключать legacy package, не являющийся sale SSOT."""
    _ = (package_id, idk)
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="SALE_PACKAGES_NOT_RELEASE_SSOT",
    )


@router.put(
    "/{package_id}",
    response_model=AdminSalePackageOut,
)
async def admin_update_sale_package(
    package_id: ApiLifetimeId,
    payload: AdminSalePackageIn,
    _auth=Depends(require_admin_write),
    idk: str = Depends(require_idempotency_key),
) -> AdminSalePackageOut:
    """Не изменять legacy package, не являющийся sale SSOT."""
    _ = (package_id, payload, idk)
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="SALE_PACKAGES_NOT_RELEASE_SSOT",
    )

