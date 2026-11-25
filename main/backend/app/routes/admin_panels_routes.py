# backend/app/routes/admin_panels_routes.py
# ======================================================================
# Админские HTTP-ручки «Панели» EFHC Bot.
#
# UI:
# - GET /admin/panels?global_id=...&is_active=true
# - PATCH /admin/panels/{panel_id}/activate
# - PATCH /admin/panels/{panel_id}/deactivate
#
# Канон:
# - require_admin
# - Idempotency-Key для изменений
# - логирование действия
# ======================================================================

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.core.utils_core import format_decimal_str
from app.deps import (
    d8,
    decode_cursor_or_400,
    get_db,
    require_admin,
    require_admin_write,
)
from app.identity.api_contract import ApiExternalGlobalId
from app.lib.time import utcnow
from app.models.panels_models import Panel, panel_is_operational_clause
from app.schemas.id_schemas import ApiLifetimeId
from app.services.admin.admin_notifications import AdminNotifier
from app.services.admin.admin_panel_protective_service import (
    PanelProtectiveError,
)
from app.services.admin.admin_panels_service import (
    AdminPanelsService,
    FreePanelActivationForbidden,
    PanelNotFound,
)
from app.services.admin.admin_rbac import RBAC
from app.utils.cursor_codec import encode_cursor
from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Query,
    status,
)
from pydantic import BaseModel, Field
from app.schemas.panel_public_id import (
    PanelPublicIdMixin,
    is_valid_panel_public_id,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/admin/panels", tags=["admin:panels"])


def _iso(dt: Any) -> str | None:
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    if isinstance(dt, datetime):
        return dt.isoformat()
    return str(dt)


def _require_idempotency(idem: str | None) -> str:
    k = (idem or "").strip()
    if not k:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key header is required",
        )
    return k


class PanelItem(PanelPublicIdMixin):
    id: ApiLifetimeId
    global_id: ApiExternalGlobalId
    is_active: bool
    created_at: str
    activated_at: str | None = None
    expires_at: str | None = None
    archived_at: str | None = None
    last_generated_at: str | None = None
    base_gen_per_sec: str
    generated_kwh: str
    protectively_voided: bool = False
    remaining_seconds: int | None = None


class PanelsOut(BaseModel):
    ok: bool = True
    items: list[PanelItem] = Field(default_factory=list)
    next_cursor: str | None = None


def _panel_item(panel: Panel) -> PanelItem:
    meta = dict(panel.meta or {})
    is_dead = meta.get("protectively_voided") is True
    now = utcnow() if panel.expires_at is not None else None
    remaining_seconds = (
        max(0, int((panel.expires_at - now).total_seconds()))
        if (
            panel.is_active
            and panel.expires_at is not None
            and now is not None
        )
        else 0
    )
    return PanelItem(
        id=int(panel.id),
        public_id=panel.public_id,
        global_id=f"{int(panel.global_id):010d}",
        is_active=bool(panel.is_active),
        created_at=_iso(panel.created_at) or "",
        activated_at=_iso(panel.activated_at),
        expires_at=_iso(panel.expires_at),
        archived_at=_iso(panel.archived_at),
        last_generated_at=_iso(panel.last_generated_at),
        base_gen_per_sec=format_decimal_str(
            d8(panel.base_gen_per_sec or 0)
        ),
        generated_kwh=format_decimal_str(d8(panel.generated_kwh or 0)),
        protectively_voided=is_dead,
        remaining_seconds=remaining_seconds,
    )


@router.get("/", response_model=PanelsOut)
async def admin_panels_list(
    global_id: ApiExternalGlobalId | None = Query(default=None),
    is_active: bool = Query(default=False),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=512),
    ctx=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> PanelsOut:
    stmt = (
        select(Panel)
        .where(panel_is_operational_clause())
        .order_by(Panel.id.desc())
        .limit(int(limit) + 1)
    )

    if global_id is not None:
        stmt = stmt.where(Panel.global_id == int(global_id))
    if is_active:
        stmt = stmt.where(Panel.is_active.is_(True))
    if cursor:
        payload = decode_cursor_or_400(cursor)
        cursor_id = payload.get("id")
        if cursor_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="ADMIN_PANELS_CURSOR_INVALID",
            )
        stmt = stmt.where(Panel.id < int(cursor_id))

    res = await db.execute(stmt)
    rows = list(res.scalars().all())
    next_cursor: str | None = None
    if len(rows) > limit:
        rows = rows[:limit]
        next_cursor = encode_cursor({"id": int(rows[-1].id)})

    return PanelsOut(
        ok=True,
        items=[_panel_item(panel) for panel in rows],
        next_cursor=next_cursor,
    )


@router.get("/{panel_id}", response_model=PanelItem)
async def admin_panel_get(
    panel_id: str,
    ctx=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> PanelItem:
    # A PNL is public and immutable; numeric internal IDs remain technical
    # compatibility input only, never a replacement for a public PNL.
    if is_valid_panel_public_id(panel_id):
        panel = (
            await db.execute(
                select(Panel).where(Panel.public_id == panel_id)
            )
        ).scalar_one_or_none()
    elif panel_id.isascii() and panel_id.isdigit():
        panel = await db.get(Panel, int(panel_id))
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ADMIN_PANEL_IDENTIFIER_INVALID",
        )
    if panel is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ADMIN_PANEL_NOT_FOUND",
        )
    return _panel_item(panel)


@router.patch("/{panel_id}/activate", status_code=204)
async def admin_panels_activate(
    panel_id: ApiLifetimeId,
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
    ),
    ctx=Depends(require_admin_write),
    db: AsyncSession = Depends(get_db),
) -> None:
    idem = _require_idempotency(idempotency_key)
    try:
        result = await AdminPanelsService.set_panel_active(
            db,
            panel_id=panel_id,
            activate=True,
            admin=RBAC.admin_from_auth_context(ctx),
            idempotency_key=idem,
        )
        if result.replay:
            await db.rollback()
        else:
            await db.commit()
    except FreePanelActivationForbidden as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="ADMIN_FREE_PANEL_ACTIVATION_FORBIDDEN",
        ) from exc
    except PanelNotFound as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ADMIN_PANEL_NOT_FOUND",
        ) from exc
    except PanelProtectiveError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.code,
        ) from exc
    except Exception:
        await db.rollback()
        raise

    if not result.replay and result.notification_id and result.notification_event and result.notification_message:
        await AdminNotifier.send_telegram_after_commit(
            notification_id=result.notification_id,
            event=result.notification_event,
            message=result.notification_message,
        )
    return None


@router.patch("/{panel_id}/deactivate", status_code=204)
async def admin_panels_deactivate(
    panel_id: ApiLifetimeId,
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
    ),
    ctx=Depends(require_admin_write),
    db: AsyncSession = Depends(get_db),
) -> None:
    idem = _require_idempotency(idempotency_key)
    try:
        result = await AdminPanelsService.set_panel_active(
            db,
            panel_id=panel_id,
            activate=False,
            admin=RBAC.admin_from_auth_context(ctx),
            idempotency_key=idem,
        )
        if result.replay:
            await db.rollback()
        else:
            await db.commit()
    except PanelNotFound as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ADMIN_PANEL_NOT_FOUND",
        ) from exc
    except PanelProtectiveError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.code,
        ) from exc
    except Exception:
        await db.rollback()
        raise

    if not result.replay and result.notification_id and result.notification_event and result.notification_message:
        await AdminNotifier.send_telegram_after_commit(
            notification_id=result.notification_id,
            event=result.notification_event,
            message=result.notification_message,
        )
    return None

