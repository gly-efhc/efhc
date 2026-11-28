from __future__ import annotations

import sqlalchemy as sa
from app.core.database_core import new_session
from app.core.security_core import decode_jwt_token
from app.identity.types import (
    global_id_from_database,
    global_id_to_database,
    parse_global_id,
)
from app.routes.hub_routes import (
    _bot_open_url,
    _browser_shop_bootstrap,
    _browser_shop_catalog,
    _browser_shop_create_intent,
    _browser_shop_intent_status,
    _build_flow_truth,
    _get_active_intent_truth,
    _handoff_base_url,
    _resolve_handoff_owner,
    _telegram_sync_url,
    _wallet_sync_url,
    create_efhc_handoff,
)
from app.schemas.hub_schemas import (
    BrowserShopBootstrapOut,
    BrowserShopCatalogOut,
    BrowserShopCreateIntentIn,
    BrowserShopCreateIntentOut,
    BrowserShopProfileOut,
    HubEfhcHandoffOut,
)
from app.schemas.id_schemas import ApiLifetimeId
from app.schemas.payment_intents_schemas import PaymentIntentStatusOut
from app.schemas.shop_schemas import ShopOrderViewOut
from app.schemas.wallet_schemas import WalletItemOut
from app.services import wallets_service
from app.services.outcome_service import (
    get_withdraw_outcome_bundle,
)
from app.services.payment_intents_service import (
    get_intent_status_for_user,
    list_recent_intents_for_user,
)
from app.services.shop_service import list_orders_for_owner
from fastapi import APIRouter, Depends, HTTPException, Request, status

router = APIRouter(prefix="/shopfront", tags=["shopfront"])


def _handoff_token_from_request(
    request: Request,
    query_token: str | None,
) -> str | None:
    """Разрешить current handoff header и legacy query token.

    Новые frontend requests используют X-EFHC-Handoff. Query token
    сохраняется только для уже выданных старых ссылок.
    """

    raw = str(request.headers.get("X-EFHC-Handoff") or "").strip()
    if raw:
        return raw
    token = str(query_token or "").strip()
    return token or None


@router.get(
    "/profile",
    response_model=BrowserShopProfileOut,
    summary="Get external web profile by signed access key",
)
async def shopfront_profile(
    request: Request,
    token: str | None = None,
) -> BrowserShopProfileOut:
    handoff_token = _handoff_token_from_request(request, token)
    if not handoff_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Browser-shop linking is required",
        )
    claims = decode_jwt_token(
        handoff_token, expected_audience="efhc_buy_site"
    )
    if claims.get("kind") != "hub_efhc_handoff":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid handoff kind",
        )
    if claims.get("aud") != "efhc_buy_site":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid handoff audience",
        )
    async with new_session() as db:
        global_id = await _resolve_handoff_owner(db, claims)
        wallets = await wallets_service.list_wallets(
            db, global_id=global_id
        )
        orders = await list_orders_for_owner(
            db,
            global_id=global_id_to_database(parse_global_id(global_id)),
            limit=200,
            paid_only=True,
        )
        active_intent = await _get_active_intent_truth(
            db=db,
            global_id=global_id,
        )
        intent_history_rows = await list_recent_intents_for_user(
            db,
            global_id=global_id,
            limit=10,
        )
        active_payment = None
        latest_withdraw_request_id = None
        latest_withdraw_status = None
        latest_withdraw_outcome = None
        if active_intent is not None:
            row = await get_intent_status_for_user(
                db,
                global_id=global_id,
                intent_id=int(active_intent.intent_id),
            )
            if row.get("ok"):
                active_payment = PaymentIntentStatusOut(**row)
        latest_withdraw = (
            await db.execute(
                sa.text(
                    """
                    SELECT id, status, global_id
                    FROM efhc_core.withdraw_requests
                    WHERE global_id = :global_id
                      AND status IN ('PAID', 'REJECTED', 'CANCELED')
                    ORDER BY COALESCE(
                        processed_at,
                        updated_at,
                        created_at
                    ) DESC, id DESC
                    LIMIT 1
                    """
                ),
                {"global_id": global_id_to_database(parse_global_id(global_id))},
            )
        ).first()
        if latest_withdraw:
            latest_withdraw_request_id = int(latest_withdraw[0])
            latest_withdraw_status = str(latest_withdraw[1])
            latest_withdraw_outcome = await get_withdraw_outcome_bundle(
                db,
                request_id=latest_withdraw_request_id,
                global_id=global_id_to_database(global_id_from_database(latest_withdraw[2])),
            )

    wallet_items = [WalletItemOut(**w.__dict__) for w in wallets]
    intent_history = [
        PaymentIntentStatusOut(**row) for row in intent_history_rows
    ]
    order_items = [
        ShopOrderViewOut(
            id=int(o.id),
            type=str(o.order_type or "EFHC_PACKAGE"),
            sku=str(o.sku or "UNKNOWN"),
            quantity=1,
            status=str(o.status),
            global_id=str(global_id_from_database(o.global_id)),
            tx_hash=o.tx_hash,
            payment_method=o.payment_method,
            expected_amount=o.expected_amount,
            paid_at=o.paid_at,
            debited_bonus_efhc=None,
            debited__main__efhc=None,
            idempotency_key=o.idempotency_key,
            created_at=o.created_at,
            updated_at=o.updated_at or o.created_at,
        )
        for o in orders
    ]
    wallet_linked = any(
        bool(getattr(wallet, "is_active", False)) for wallet in wallets
    )
    flow_truth = _build_flow_truth(
        handoff_configured=bool(_handoff_base_url()),
        wallet_linked=wallet_linked,
        wallet_sync_required=not wallet_linked,
        active_intent=active_intent,
        require_handoff=False,
    )
    return BrowserShopProfileOut(
        global_id=global_id,
        wallets=wallet_items,
        orders=order_items,
        bot_open_url=_bot_open_url(),
        wallet_sync_url=_wallet_sync_url(),
        telegram_sync_url=_telegram_sync_url(),
        flow_truth=flow_truth,
        active_payment=active_payment,
        intent_history=intent_history,
        latest_withdraw_request_id=latest_withdraw_request_id,
        latest_withdraw_status=latest_withdraw_status,
        latest_withdraw_outcome=latest_withdraw_outcome,
    )


@router.post(
    "/access-key",
    response_model=HubEfhcHandoffOut,
    summary="Create signed access URL for external shopfront",
)
async def shopfront_access_key(
    out: HubEfhcHandoffOut = Depends(create_efhc_handoff),
) -> HubEfhcHandoffOut:
    return out


@router.get(
    "/bootstrap",
    response_model=BrowserShopBootstrapOut,
    summary="Get shopfront bootstrap state",
)
async def shopfront_bootstrap(
    request: Request,
    token: str | None = None,
) -> BrowserShopBootstrapOut:
    handoff_token = _handoff_token_from_request(request, token)
    return await _browser_shop_bootstrap(token=handoff_token)


@router.get(
    "/catalog",
    response_model=BrowserShopCatalogOut,
    summary="Get shopfront catalog",
)
async def shopfront_catalog() -> BrowserShopCatalogOut:
    return await _browser_shop_catalog()


@router.post(
    "/create-intent",
    response_model=BrowserShopCreateIntentOut,
    summary="Create external shopfront intent",
)
async def shopfront_create_intent(
    payload: BrowserShopCreateIntentIn,
) -> BrowserShopCreateIntentOut:
    return await _browser_shop_create_intent(payload=payload)


@router.get(
    "/intent-status",
    response_model=PaymentIntentStatusOut,
    summary="Get external shopfront intent status",
)
async def shopfront_intent_status(
    request: Request,
    intent_id: ApiLifetimeId,
    token: str | None = None,
) -> PaymentIntentStatusOut:
    handoff_token = _handoff_token_from_request(request, token)
    if not handoff_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Browser-shop linking is required",
        )
    return await _browser_shop_intent_status(
        token=handoff_token,
        intent_id=int(intent_id),
    )
