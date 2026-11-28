# backend/app/routes/admin_hub_routes.py
# ======================================================================
# EFHC Bot — Admin Hub links manager
# ----------------------------------------------------------------------
# Назначение:
# Канонический backend router для отдельного раздела Admin Hub.
#
# Канон текущего Admin Hub repair:
# • Admin Hub живёт по `/admin/hub/*`, не под `/admin/shop/*`.
# • Shop router и Hub router не вкладываются друг в друга.
# • Изменения Hub links доступны только через admin guard.
# • Runtime-код из Песочницы не переносится.
# ======================================================================

from __future__ import annotations

from typing import Any

from app.core.logging_core import get_logger
from app.deps import get_db, require_admin, require_admin_write
from app.schemas.hub_admin_schemas import (
    HubLinkAdminCreateIn,
    HubLinkAdminOut,
    HubLinkAdminReorderIn,
    HubLinkAdminToggleIn,
    HubLinkAdminUpdateIn,
    HubSupportLinkAdminCreateIn,
    HubSupportLinkAdminUpdateIn,
)
from app.schemas.id_schemas import ApiLifetimeId
from app.services.admin.admin_hub_links_service import (
    HubLinkAdminError,
    admin_create_hub_link,
    admin_create_support_link,
    admin_list_hub_links,
    admin_list_support_links,
    admin_reorder_hub_links,
    admin_reorder_support_links,
    admin_toggle_hub_link,
    admin_toggle_support_link,
    admin_update_hub_link,
    admin_update_support_link,
)
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/admin/hub", tags=["admin:hub"])
logger = get_logger(__name__)


@router.get("/links", response_model=list[HubLinkAdminOut])
async def admin_hub_links_list(
    active_only: bool = False,
    db: AsyncSession = Depends(get_db),
    _auth: Any = Depends(require_admin),
) -> list[HubLinkAdminOut]:
    rows = await admin_list_hub_links(db, active_only=active_only)
    return [HubLinkAdminOut.model_validate(row) for row in rows]


@router.post("/links", response_model=HubLinkAdminOut)
async def admin_hub_link_create(
    payload: HubLinkAdminCreateIn,
    db: AsyncSession = Depends(get_db),
    _auth: Any = Depends(require_admin_write),
) -> HubLinkAdminOut:
    try:
        row = await admin_create_hub_link(
            db,
            code=payload.code,
            title=payload.title,
            subtitle=payload.subtitle,
            url=payload.url,
            target_kind=payload.target_kind,
            open_mode=payload.open_mode,
            sort_order=payload.sort_order,
            is_active=payload.is_active,
            icon_key=payload.icon_key,
        )
        await db.commit()
        return HubLinkAdminOut.model_validate(row)
    except HubLinkAdminError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        await db.rollback()
        logger.exception("admin hub create failed")
        raise HTTPException(
            status_code=500,
            detail="ADMIN_HUB_CREATE_UNAVAILABLE",
        ) from None


@router.put("/links/{link_id}", response_model=HubLinkAdminOut)
async def admin_hub_link_update(
    link_id: ApiLifetimeId,
    payload: HubLinkAdminUpdateIn,
    db: AsyncSession = Depends(get_db),
    _auth: Any = Depends(require_admin_write),
) -> HubLinkAdminOut:
    try:
        row = await admin_update_hub_link(
            db,
            link_id=link_id,
            title=payload.title,
            subtitle=payload.subtitle,
            url=payload.url,
            target_kind=payload.target_kind,
            open_mode=payload.open_mode,
            sort_order=payload.sort_order,
            is_active=payload.is_active,
            icon_key=payload.icon_key,
        )
        await db.commit()
        return HubLinkAdminOut.model_validate(row)
    except HubLinkAdminError as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception:
        await db.rollback()
        logger.exception("admin hub update failed")
        raise HTTPException(
            status_code=500,
            detail="ADMIN_HUB_UPDATE_UNAVAILABLE",
        ) from None


@router.post(
    "/links/{link_id}/toggle",
    response_model=HubLinkAdminOut,
)
async def admin_hub_link_toggle(
    link_id: ApiLifetimeId,
    payload: HubLinkAdminToggleIn,
    db: AsyncSession = Depends(get_db),
    _auth: Any = Depends(require_admin_write),
) -> HubLinkAdminOut:
    try:
        row = await admin_toggle_hub_link(
            db,
            link_id=link_id,
            is_active=payload.is_active,
        )
        await db.commit()
        return HubLinkAdminOut.model_validate(row)
    except HubLinkAdminError as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception:
        await db.rollback()
        logger.exception("admin hub toggle failed")
        raise HTTPException(
            status_code=500,
            detail="ADMIN_HUB_TOGGLE_UNAVAILABLE",
        ) from None


@router.post("/links/reorder", response_model=list[HubLinkAdminOut])
async def admin_hub_links_reorder(
    payload: HubLinkAdminReorderIn,
    db: AsyncSession = Depends(get_db),
    _auth: Any = Depends(require_admin_write),
) -> list[HubLinkAdminOut]:
    try:
        row_items = [item.model_dump() for item in payload.items]
        rows = await admin_reorder_hub_links(db, items=row_items)
        await db.commit()
        return [HubLinkAdminOut.model_validate(row) for row in rows]
    except HubLinkAdminError as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception:
        await db.rollback()
        logger.exception("admin hub reorder failed")
        raise HTTPException(
            status_code=500,
            detail="ADMIN_HUB_REORDER_UNAVAILABLE",
        ) from None


@router.get("/support-links", response_model=list[HubLinkAdminOut])
async def admin_support_links_list(
    active_only: bool = False,
    db: AsyncSession = Depends(get_db),
    _auth: Any = Depends(require_admin),
) -> list[HubLinkAdminOut]:
    rows = await admin_list_support_links(db, active_only=active_only)
    return [HubLinkAdminOut.model_validate(row) for row in rows]


@router.post("/support-links", response_model=HubLinkAdminOut)
async def admin_support_link_create(
    payload: HubSupportLinkAdminCreateIn,
    db: AsyncSession = Depends(get_db),
    _auth: Any = Depends(require_admin_write),
) -> HubLinkAdminOut:
    try:
        row = await admin_create_support_link(
            db,
            code=payload.code,
            title=payload.title,
            subtitle=payload.subtitle,
            url=payload.url,
            sort_order=payload.sort_order,
            is_active=payload.is_active,
            icon_key=payload.icon_key,
        )
        await db.commit()
        return HubLinkAdminOut.model_validate(row)
    except HubLinkAdminError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        await db.rollback()
        logger.exception("admin support link create failed")
        raise HTTPException(
            status_code=500, detail="ADMIN_SUPPORT_LINK_CREATE_UNAVAILABLE"
        ) from None


@router.put(
    "/support-links/{link_id}",
    response_model=HubLinkAdminOut,
)
async def admin_support_link_update(
    link_id: ApiLifetimeId,
    payload: HubSupportLinkAdminUpdateIn,
    db: AsyncSession = Depends(get_db),
    _auth: Any = Depends(require_admin_write),
) -> HubLinkAdminOut:
    try:
        row = await admin_update_support_link(
            db,
            link_id=link_id,
            title=payload.title,
            subtitle=payload.subtitle,
            url=payload.url,
            sort_order=payload.sort_order,
            is_active=payload.is_active,
            icon_key=payload.icon_key,
        )
        await db.commit()
        return HubLinkAdminOut.model_validate(row)
    except HubLinkAdminError as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception:
        await db.rollback()
        logger.exception("admin support link update failed")
        raise HTTPException(
            status_code=500, detail="ADMIN_SUPPORT_LINK_UPDATE_UNAVAILABLE"
        ) from None


@router.post(
    "/support-links/{link_id}/toggle",
    response_model=HubLinkAdminOut,
)
async def admin_support_link_toggle(
    link_id: ApiLifetimeId,
    payload: HubLinkAdminToggleIn,
    db: AsyncSession = Depends(get_db),
    _auth: Any = Depends(require_admin_write),
) -> HubLinkAdminOut:
    try:
        row = await admin_toggle_support_link(
            db, link_id=link_id, is_active=payload.is_active
        )
        await db.commit()
        return HubLinkAdminOut.model_validate(row)
    except HubLinkAdminError as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception:
        await db.rollback()
        logger.exception("admin support link toggle failed")
        raise HTTPException(
            status_code=500, detail="ADMIN_SUPPORT_LINK_TOGGLE_UNAVAILABLE"
        ) from None


@router.post(
    "/support-links/reorder", response_model=list[HubLinkAdminOut]
)
async def admin_support_links_reorder(
    payload: HubLinkAdminReorderIn,
    db: AsyncSession = Depends(get_db),
    _auth: Any = Depends(require_admin_write),
) -> list[HubLinkAdminOut]:
    try:
        rows = await admin_reorder_support_links(
            db, items=[item.model_dump() for item in payload.items]
        )
        await db.commit()
        return [HubLinkAdminOut.model_validate(row) for row in rows]
    except HubLinkAdminError as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception:
        await db.rollback()
        logger.exception("admin support links reorder failed")
        raise HTTPException(
            status_code=500, detail="ADMIN_SUPPORT_LINK_REORDER_UNAVAILABLE"
        ) from None
