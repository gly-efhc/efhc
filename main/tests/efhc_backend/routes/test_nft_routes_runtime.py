from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from app.lib.ton_address import to_friendly_ton_address
from app.routes import nft_routes
from fastapi import HTTPException

pytestmark = pytest.mark.asyncio


def _wallet() -> str:
    raw = "0:" + ("11" * 32)
    return to_friendly_ton_address(raw)


async def test_has_vip_route_uses_valid_kwargs(monkeypatch):
    checker = AsyncMock(return_value=True)
    monkeypatch.setattr(
        nft_routes,
        "wallet_has_nft_in_collection",
        checker,
    )
    monkeypatch.setattr(
        nft_routes.settings,
        "TON_NFT_COLLECTION",
        "COLL",
    )

    result = await nft_routes.has_vip_nft(wallet=_wallet())

    checker.assert_awaited_once_with(
        wallet=_wallet(),
        collection="COLL",
    )
    assert result["has_vip"] is True
    assert result["has_nft"] is True


async def test_has_vip_route_invalid_wallet_is_400(monkeypatch):
    checker = AsyncMock(return_value=True)
    monkeypatch.setattr(
        nft_routes,
        "wallet_has_nft_in_collection",
        checker,
    )
    monkeypatch.setattr(
        nft_routes.settings,
        "TON_NFT_COLLECTION",
        "COLL",
    )

    with pytest.raises(HTTPException) as exc:
        await nft_routes.has_vip_nft(wallet="not-a-ton-address")

    assert exc.value.status_code == 400
    checker.assert_not_awaited()
