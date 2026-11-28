# backend/app/routes/panels_routes.py
# =====================================================================
# Роуты панелей: summary, active, archive, activation.
# Канон:
# • Активация панели — 100 EFHC (bonus → main).
# • Денежные POST требуют Idempotency-Key.
# • Пагинация: cursor-based. ETag поддерживается.
# • force_sync=1 может догнать генерацию (safe).
# =====================================================================

from __future__ import annotations

from app.core.config_core import get_settings
from app.core.logging_core import get_logger
from app.deps import get_db, make_etag, require_idempotency_key
from app.identity.nonfinancial_owner import NonFinancialReadOwner
from app.identity.nonfinancial_read_dependency import (
    get_nonfinancial_read_owner,
)
from app.lib.time import utcnow
from app.models.panels_models import Panel
from app.schemas.id_schemas import ApiLifetimeId
from app.services import panels_service as svc
from app.services.energy_service import generate_energy_for_user
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Response,
    status,
)
from pydantic import BaseModel, Field
from app.schemas.panel_public_id import PanelPublicIdMixin
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)
settings = get_settings()

router = APIRouter(prefix="/panels", tags=["panels"])


class PanelItemOut(PanelPublicIdMixin):
    id: ApiLifetimeId
    activated_at: str | None = None
    created_at: str | None = None
    expires_at: str | None = None
    archived_at: str | None = None
    remaining_seconds: int | None = None
    base_gen_per_sec: str
    generated_kwh: str
    is_active: bool


class PanelsListOut(BaseModel):
    items: list[PanelItemOut]
    next_cursor: str | None = Field(
        None,
        description="Курсор следующей страницы",
    )
    server_now_utc: str = Field(
        ...,
        description="SSOT UTC now (ISO 8601, tz-aware)",
    )


class PanelsSummaryOut(BaseModel):
    active_count: int
    total_generated_by_panels: str
    nearest_expire_at: str | None = None


class PanelOut(PanelPublicIdMixin):
    id: ApiLifetimeId
    activated_at: str
    expires_at: str


class BuyPanelOut(BaseModel):
    panel: PanelOut
    server_now_utc: str


async def _activate_one_panel(
    *,
    idempotency_key: str,
    db: AsyncSession,
    owner: NonFinancialReadOwner,
) -> BuyPanelOut:
    if not idempotency_key or not idempotency_key.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=("Idempotency-Key header is required by canon."),
        )

    res = await svc.activate_panel(
        db,
        global_id=int(owner.global_id),
        qty=1,
        idempotency_key=idempotency_key.strip(),
    )
    if not res.created_panel_ids:
        raise HTTPException(
            status_code=500,
            detail="Panel creation failed",
        )
    panel_id = int(res.created_panel_ids[0])

    stmt = select(
        Panel.id,
        Panel.public_id,
        Panel.activated_at,
        Panel.expires_at,
    ).where(Panel.id == panel_id)
    stmt = stmt.where(Panel.global_id == int(owner.global_id))
    row = await db.execute(stmt)
    rec = row.first()
    if not rec or not rec[1]:
        raise HTTPException(
            status_code=500,
            detail="Panel not found",
        )

    panel = PanelOut(
        id=int(rec[0]),
        public_id=str(rec[1]),
        activated_at=rec[2].isoformat(),
        expires_at=rec[3].isoformat(),
    )
    return BuyPanelOut(
        panel=panel,
        server_now_utc=utcnow().isoformat(),
    )


async def _list_panels_for_current_user(
    *,
    kind: str,
    response: Response,
    limit: int,
    cursor: str | None,
    force_sync: int | None,
    db: AsyncSession,
    owner: NonFinancialReadOwner,
) -> PanelsListOut:
    try:
        server_now_utc = utcnow().isoformat()
        if force_sync:
            await generate_energy_for_user(
                db, global_id=int(owner.global_id)
            )

        owner_kwargs = {"global_id": int(owner.global_id)}
        if kind == "active":
            page = await svc.list_active_panels(
                db,
                **owner_kwargs,
                limit=limit,
                cursor=cursor,
            )
        else:
            page = await svc.list_archived_panels(
                db,
                **owner_kwargs,
                limit=limit,
                cursor=cursor,
            )

        items_out = [
            PanelItemOut(
                id=int(i["id"]),
                public_id=i["public_id"],
                activated_at=i.get("activated_at"),
                created_at=i.get("created_at"),
                expires_at=i.get("expires_at"),
                archived_at=i.get("archived_at"),
                remaining_seconds=i.get("remaining_seconds"),
                base_gen_per_sec=str(i["base_gen_per_sec"]),
                generated_kwh=str(i["generated_kwh"]),
                is_active=bool(i["is_active"]),
            )
            for i in page.items
        ]
        payload = PanelsListOut(
            items=items_out,
            next_cursor=page.next_cursor,
            server_now_utc=server_now_utc,
        )

        e = make_etag(
            {
                "kind": f"panels_{kind}",
                "global_id": f"{int(owner.global_id):010d}",
                "ids": [int(i.id) for i in items_out],
                "next": page.next_cursor or "",
            }
        )
        response.headers["ETag"] = e
        return payload
    except Exception as err:
        logger.exception("panels.%s failed", kind)
        raise HTTPException(
            status_code=500,
            detail="Временная ошибка. Повторите.",
        ) from err


@router.get(
    "/active",
    response_model=PanelsListOut,
    summary="Активные панели текущего пользователя",
)
async def list_my_active_panels(
    response: Response,
    limit: int = 25,
    cursor: str | None = None,
    force_sync: int | None = 0,
    db: AsyncSession = Depends(get_db),
    owner: NonFinancialReadOwner = Depends(
        get_nonfinancial_read_owner
    ),
) -> PanelsListOut:
    return await _list_panels_for_current_user(
        kind="active",
        response=response,
        limit=limit,
        cursor=cursor,
        force_sync=force_sync,
        db=db,
        owner=owner,
    )


@router.get(
    "/archive",
    response_model=PanelsListOut,
    summary="Архивные панели текущего пользователя",
)
async def list_my_archived_panels(
    response: Response,
    limit: int = 25,
    cursor: str | None = None,
    force_sync: int | None = 0,
    db: AsyncSession = Depends(get_db),
    owner: NonFinancialReadOwner = Depends(
        get_nonfinancial_read_owner
    ),
) -> PanelsListOut:
    return await _list_panels_for_current_user(
        kind="archive",
        response=response,
        limit=limit,
        cursor=cursor,
        force_sync=force_sync,
        db=db,
        owner=owner,
    )


@router.post(
    "/activate",
    response_model=BuyPanelOut,
    summary="Активация панели",
)
async def activate_panel_route(
    idempotency_key: str = Depends(require_idempotency_key),
    db: AsyncSession = Depends(get_db),
    owner: NonFinancialReadOwner = Depends(get_nonfinancial_read_owner),
) -> BuyPanelOut:
    try:
        return await _activate_one_panel(
            idempotency_key=idempotency_key,
            db=db,
            owner=owner,
        )
    except svc.UserInDebtError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except svc.PanelLimitExceeded as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except svc.IdempotencyRequiredError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except svc.PanelPurchaseError as e:
        logger.warning("panels.activate business error: %s", e)
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as err:
        logger.exception("panels.activate failed")
        raise HTTPException(
            status_code=500,
            detail="Временная ошибка. Повторите.",
        ) from err


# Маркер guard: async def get_panels_summary
