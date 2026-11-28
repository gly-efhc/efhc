# backend/app/routes/nft_routes.py
# =====================================================================
# Read-only эндпоинты NFT/VIP: проверка наличия NFT у кошелька.
# Никакой выдачи/доставки NFT здесь нет.
# =====================================================================

from __future__ import annotations

from app.core.config_core import get_settings
from app.identity.nonfinancial_owner import NonFinancialReadOwner
from app.identity.nonfinancial_read_dependency import (
    get_nonfinancial_read_owner,
)
from app.integrations.nft_api import wallet_has_nft_in_collection
from app.lib.ton_address import TonAddressError, parse_ton_address
from fastapi import APIRouter, Depends, HTTPException, Query

settings = get_settings()
router = APIRouter(prefix="/nft", tags=["nft"])


@router.get("/has_vip")
async def has_vip_nft(
    wallet: str = Query(..., description="TON wallet address"),
    _owner: NonFinancialReadOwner = Depends(get_nonfinancial_read_owner),
) -> dict:
    collection = settings.TON_NFT_COLLECTION
    try:
        parse_ton_address(wallet)
    except TonAddressError as err:
        raise HTTPException(
            status_code=400,
            detail="Invalid TON wallet address",
        ) from err
    if not collection:
        raise HTTPException(
            status_code=500,
            detail="TON_NFT_COLLECTION not configured",
        )
    ok = await wallet_has_nft_in_collection(
        wallet=wallet,
        collection=collection,
    )
    return {
        "wallet": wallet,
        "collection": collection,
        "has_vip": bool(ok),
        "has_nft": bool(ok),
    }
