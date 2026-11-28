"""HTTP API домена «Skins» (картинки для главной)."""

from __future__ import annotations

from app.deps import get_db, require_idempotency_key
from app.identity.nonfinancial_owner import NonFinancialReadOwner
from app.identity.nonfinancial_read_dependency import (
    get_nonfinancial_read_owner,
)
from app.schemas.skins_schemas import (
    SkinsCatalogOut,
    SkinsMyOut,
    SkinSwitcherOut,
)
from app.services import skins_service
from fastapi import APIRouter, Depends, HTTPException, status

router = APIRouter(prefix="/skins", tags=["skins"])


@router.get("/catalog", response_model=SkinsCatalogOut)
async def skins_catalog():
    return {"items": skins_service.get_catalog()}


@router.get("/my", response_model=SkinsMyOut)
async def skins_my(
    owner: NonFinancialReadOwner = Depends(get_nonfinancial_read_owner),
    db=Depends(get_db),
):
    return await skins_service.get_my(db, owner=owner)


@router.get("/switcher", response_model=SkinSwitcherOut)
async def skins_switcher(
    owner: NonFinancialReadOwner = Depends(get_nonfinancial_read_owner),
    db=Depends(get_db),
):
    return await skins_service.get_switcher(db, owner=owner)



@router.post("/buy/{skin_id}")
async def skins_buy(
    skin_id: int,
    idempotency_key: str = Depends(require_idempotency_key),
    owner: NonFinancialReadOwner = Depends(
        get_nonfinancial_read_owner
    ),
    db=Depends(get_db),
):
    """Compatibility route: skin commerce остаётся запрещённым каноном."""

    _ = (db, owner, skin_id, idempotency_key)
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="SKIN_COMMERCE_DISABLED",
    )


@router.post("/activate/{skin_id}")
async def skins_activate(
    skin_id: int,
    owner: NonFinancialReadOwner = Depends(get_nonfinancial_read_owner),
    db=Depends(get_db),
):
    await skins_service.activate_skin(
        db,
        owner=owner,
        skin_id=int(skin_id),
    )
    return {"ok": True}


@router.post("/switcher/activate/{skin_id}")
async def skins_switcher_activate(
    skin_id: int,
    owner: NonFinancialReadOwner = Depends(get_nonfinancial_read_owner),
    db=Depends(get_db),
):
    await skins_service.activate_skin(
        db,
        owner=owner,
        skin_id=int(skin_id),
    )
    return {"ok": True}
