from __future__ import annotations

import os
from datetime import timedelta
from typing import cast
from urllib.parse import (
    parse_qsl,
    urlencode,
    urlsplit,
    urlunsplit,
)
from uuid import uuid4

from app.core.config_core import get_settings
from app.core.database_core import new_session
from app.core.security_core import create_jwt_token, decode_jwt_token
from app.deps import get_db
from app.identity.financial_owner import FinancialReadOwner
from app.identity.financial_read_dependency import (
    get_financial_read_owner,
)
from app.identity.types import (
    global_id_from_database,
    global_id_to_database,
    parse_global_id,
)
from app.lib.time import utcnow
from app.schemas.hub_schemas import (
    BrowserShopActiveIntentOut,
    BrowserShopBootstrapOut,
    BrowserShopCatalogItemOut,
    BrowserShopCatalogOut,
    BrowserShopCreateIntentIn,
    BrowserShopCreateIntentOut,
    BrowserShopFlowTruthOut,
    HubEfhcHandoffOut,
    HubLinkOut,
    HubShopTruthOut,
    HubSupportLinkOut,
)
from app.schemas.id_schemas import ApiLifetimeId
from app.schemas.payment_intents_schemas import PaymentIntentStatusOut
from app.schemas.shop_schemas import ShopOrderExternalIn
from app.schemas.wallet_schemas import WalletItemOut
from app.services import wallets_service
from app.services.admin.admin_hub_links_service import admin_list_hub_links
from app.services.hub_support_service import list_active_support_links
from app.services.payment_intents_service import (
    _wallet_readiness_payload,
    create_intent_shop_external_in_transaction,
    get_intent_status_for_user,
    get_usdt_checkout_mode,
)
from app.services.shop_prepayment_store import ShopPreparationActiveError
from app.services.shop_service import (
    ShopService,
    bind_vip_number_reservation_in_transaction,
)
from app.services.transactions_service import (
    IdempotencyPayloadConflictError,
)
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/hub", tags=["hub"])


_ACTIVE_INTENT_STATUSES = ("PENDING", "SENT")


@router.get("/links", response_model=list[HubLinkOut])
async def hub_links(
    db: AsyncSession = Depends(get_db),
) -> list[HubLinkOut]:
    """Public read-only projection of active non-support Hub links."""
    rows = await admin_list_hub_links(db, active_only=True)
    return [HubLinkOut.model_validate(row) for row in rows]


@router.get("/support-links", response_model=list[HubSupportLinkOut])
async def hub_support_links(
    db: AsyncSession = Depends(get_db),
) -> list[HubSupportLinkOut]:
    rows = await list_active_support_links(db)
    return [HubSupportLinkOut.model_validate(row) for row in rows]


def _global_id_db(global_id: str) -> int:
    return cast(int, global_id_to_database(parse_global_id(global_id)))


def _owner_global_id(owner: FinancialReadOwner) -> str:
    return str(global_id_from_database(owner.global_id))


def _handoff_base_url() -> str:
    settings = get_settings()
    return str(getattr(settings, "HUB_EFHC_BUY_URL", "") or "").strip()


async def _get_active_intent_truth(
    *,
    db,
    global_id: str,
) -> BrowserShopActiveIntentOut | None:
    row = (
        (
            await db.execute(
                text(
                    "\n".join(
                        [
                            "SELECT pi.id, pi.purpose, pi.asset,",
                            "       pi.amount_asset_d8::numeric,",
                            "       pi.efhc_amount_d8::numeric,",
                            "       pi.status, pi.payload,",
                            "       pi.to_address, pi.created_at,",
                            "       pi.expires_at,",
                            "       so.id AS order_id,",
                            "       so.status AS order_status",
                            "  FROM efhc_core.payment_intents pi",
                            "  LEFT JOIN efhc_core.shop_orders so",
                            "    ON (so.extra ->> 'intent_id') =",
                            "       CAST(pi.id AS text)",
                            " WHERE pi.global_id = :global_id",
                            "   AND pi.purpose = 'shop_external'",
                            "   AND pi.status = 'PENDING'",
                            "   AND pi.expires_at > NOW()",
                            " ORDER BY pi.created_at DESC, pi.id DESC",
                            " LIMIT 1",
                        ]
                    )
                ),
                {
                    "global_id": _global_id_db(global_id),
                },
            )
        )
        .mappings()
        .first()
    )
    if not row:
        return None
    order_id = row.get("order_id")
    flow_row = await get_intent_status_for_user(
        db,
        global_id=global_id,
        intent_id=int(row["id"]),
    )
    flow_truth = (
        flow_row.get("flow_truth") if flow_row.get("ok") else None
    )
    return BrowserShopActiveIntentOut(
        intent_id=int(row["id"]),
        purpose=str(row["purpose"]),
        asset=str(row["asset"]),
        amount_asset_d8=str(row["amount_asset_d8"]),
        external_amount_atomic=flow_row.get("external_amount_atomic"),
        external_decimals=flow_row.get("external_decimals"),
        external_amount_display=flow_row.get("external_amount_display"),
        efhc_amount_d8=(
            str(row["efhc_amount_d8"])
            if row["efhc_amount_d8"] is not None
            else None
        ),
        status=str(row["status"]),
        payload=str(row["payload"]),
        to_address=str(row["to_address"]),
        order_id=int(order_id) if order_id is not None else None,
        order_status=(
            str(row["order_status"])
            if row.get("order_status") is not None
            else None
        ),
        created_at=row["created_at"],
        expires_at=row["expires_at"],
        flow_truth=flow_truth,
    )


async def _resolve_handoff_owner(
    db,
    claims: dict,
) -> str:
    """Разрешить подписанный handoff в десятизначный global_id."""

    raw_global = claims.get("global_id")
    if raw_global is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid handoff identity",
        )
    try:
        if isinstance(raw_global, str):
            canonical_global_id = str(parse_global_id(raw_global))
        else:
            # Короткая совместимость с уже выданными подписанными токенами
            # предыдущего HEAD; новые токены содержат только строку.
            canonical_global_id = str(global_id_from_database(raw_global))
        global_id_db = global_id_to_database(
            parse_global_id(canonical_global_id)
        )
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid handoff identity",
        ) from err

    active = (
        await db.execute(
            text(
                """
                SELECT 1
                  FROM efhc_core.users
                 WHERE global_id = :global_id
                   AND is_active IS TRUE
                 LIMIT 1
                """
            ),
            {"global_id": global_id_db},
        )
    ).scalar_one_or_none()
    if active is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid handoff identity",
        )
    return canonical_global_id


def _build_flow_truth(
    *,
    handoff_configured: bool,
    wallet_linked: bool,
    wallet_sync_required: bool,
    active_intent: BrowserShopActiveIntentOut | None,
    require_handoff: bool,
) -> BrowserShopFlowTruthOut:
    blocker_codes: list[str] = []
    if require_handoff:
        blocker_codes.append("telegram_handoff_required")
    if not handoff_configured:
        blocker_codes.append("external_buy_flow_missing")
    if wallet_sync_required:
        blocker_codes.append("wallet_sync_required")

    next_step = "create_intent"
    product_state = "created"
    next_action = "open_browser_shop"
    return_path = "web_profile"
    canonical_center = "web_profile"
    if require_handoff:
        next_step = "connect_handoff"
        next_action = "open_telegram_handoff"
        return_path = "telegram"
    elif wallet_sync_required:
        next_step = "sync_wallet"
        next_action = "sync_wallet"
    elif active_intent is not None:
        next_step = "resume_intent"
        if active_intent.flow_truth is not None:
            product_state = str(active_intent.flow_truth.product_state)
            next_action = str(active_intent.flow_truth.next_action)
            return_path = str(active_intent.flow_truth.return_path)
            canonical_center = str(
                active_intent.flow_truth.canonical_center
                or "web_profile"
            )
        else:
            product_state = "active"
            next_action = "resume_browser_shop"
            return_path = "browser_shop"

    readiness = _wallet_readiness_payload(
        require_handoff=require_handoff,
        handoff_configured=handoff_configured,
        wallet_linked=wallet_linked,
        wallet_sync_required=wallet_sync_required,
        has_active_intent=active_intent is not None,
        next_action=next_action,
    )

    return BrowserShopFlowTruthOut(
        handoff_configured=handoff_configured,
        handoff_mode=(
            "connected" if handoff_configured else "missing_config"
        ),
        wallet_linked=wallet_linked,
        wallet_sync_required=wallet_sync_required,
        wallet_ready=bool(readiness["wallet_ready"]),
        wallet_blocked=bool(readiness["wallet_blocked"]),
        action_allowed=bool(readiness["action_allowed"]),
        action_denied=bool(readiness["action_denied"]),
        readiness_state=str(readiness["readiness_state"]),
        primary_cta=str(readiness["primary_cta"]),
        active_intent=active_intent,
        active_order_id=(
            int(active_intent.order_id)
            if active_intent is not None
            and active_intent.order_id is not None
            else None
        ),
        active_order_status=(
            str(active_intent.order_status)
            if active_intent is not None
            and active_intent.order_status is not None
            else None
        ),
        product_state=product_state,
        next_action=next_action,
        return_path=return_path,
        canonical_center=canonical_center,
        next_step=next_step,
        blocker_codes=blocker_codes,
    )


def _append_token(base_url: str, token: str) -> str:
    """Добавить handoff bearer только во fragment URL.

    Fragment не отправляется HTTP-серверу, reverse proxy и link-preview
    fetch. Query string исходного base URL сохраняется без изменений.
    """

    parts = urlsplit(base_url)
    fragment = dict(parse_qsl(parts.fragment, keep_blank_values=True))
    fragment["token"] = token
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            parts.query,
            urlencode(fragment),
        )
    )


def _bot_open_url() -> str | None:
    uname = str(os.getenv("BOT_USERNAME") or "").strip().lstrip("@")
    if not uname:
        return None
    return f"https://t.me/{uname}"


def _telegram_sync_url() -> str | None:
    uname = str(os.getenv("BOT_USERNAME") or "").strip().lstrip("@")
    if not uname:
        return None
    return f"https://t.me/{uname}?start=browser_shop_sync"


def _wallet_sync_url() -> str | None:
    uname = str(os.getenv("BOT_USERNAME") or "").strip().lstrip("@")
    if not uname:
        return None
    return f"https://t.me/{uname}?start=browser_shop_wallet"


@router.post(
    "/efhc-handoff",
    response_model=HubEfhcHandoffOut,
    summary="Create signed Hub EFHC handoff URL",
)
async def create_efhc_handoff(
    owner: FinancialReadOwner = Depends(get_financial_read_owner),
) -> HubEfhcHandoffOut:
    base_url = _handoff_base_url()
    if not base_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=("Hub EFHC buy-flow is not connected yet"),
        )

    settings = get_settings()
    ttl = int(getattr(settings, "HUB_EFHC_HANDOFF_TTL_SEC", 300) or 300)
    expires = utcnow() + timedelta(seconds=ttl)
    token = create_jwt_token(
        "hub_efhc_handoff",
        expires_delta=timedelta(seconds=ttl),
        extra={
            "kind": "hub_efhc_handoff",
            "aud": "efhc_buy_site",
            "global_id": _owner_global_id(owner),
        },
    )
    return HubEfhcHandoffOut(
        redirect_url=_append_token(base_url, token),
        expires_at=expires,
    )


@router.get(
    "/shop-truth",
    response_model=HubShopTruthOut,
    summary="Get Hub → browser-shop truth-layer state",
)
async def get_hub_shop_truth(
    owner: FinancialReadOwner = Depends(get_financial_read_owner),
) -> HubShopTruthOut:
    async with new_session() as db:
        wallets = await wallets_service.list_wallets(
            db,
            global_id=_owner_global_id(owner),
        )
        active_intent = await _get_active_intent_truth(
            db=db,
            global_id=_owner_global_id(owner),
        )

    active_wallet = next(
        (w for w in wallets if bool(getattr(w, "is_active", False))),
        None,
    )
    active_addr = (
        str(getattr(active_wallet, "wallet_address", ""))
        if active_wallet is not None
        else None
    )
    wallet_linked = active_wallet is not None
    flow_truth = _build_flow_truth(
        handoff_configured=bool(_handoff_base_url()),
        wallet_linked=wallet_linked,
        wallet_sync_required=not wallet_linked,
        active_intent=active_intent,
        require_handoff=False,
    )
    return HubShopTruthOut(
        handoff_configured=flow_truth.handoff_configured,
        handoff_mode=flow_truth.handoff_mode,
        wallet_linked=wallet_linked,
        wallet_sync_required=not wallet_linked,
        active_wallet_address=active_addr,
        bot_open_url=_bot_open_url(),
        telegram_sync_url=_telegram_sync_url(),
        wallet_sync_url=_wallet_sync_url(),
        flow_truth=flow_truth,
    )


@router.get(
    "/browser-shop-bootstrap",
    response_model=BrowserShopBootstrapOut,
    summary="Get browser-shop bootstrap state",
    include_in_schema=False,
)
async def get_browser_shop_bootstrap(
    token: str | None = None,
) -> BrowserShopBootstrapOut:
    """Compatibility alias к canonical shopfront bootstrap helper."""
    return await _browser_shop_bootstrap(token=token)


async def _browser_shop_bootstrap(
    token: str | None = None,
) -> BrowserShopBootstrapOut:
    if not token:
        flow_truth = _build_flow_truth(
            handoff_configured=bool(_handoff_base_url()),
            wallet_linked=False,
            wallet_sync_required=True,
            active_intent=None,
            require_handoff=True,
        )
        return BrowserShopBootstrapOut(
            mode="guest",
            tg_linked=False,
            global_id=None,
            wallet_linked=False,
            active_wallet_address=None,
            wallets=[],
            wallet_sync_required=True,
            bot_open_url=_bot_open_url(),
            telegram_sync_url=_telegram_sync_url(),
            wallet_sync_url=_wallet_sync_url(),
            usdt_checkout_mode=get_usdt_checkout_mode(),
            flow_truth=flow_truth,
            active_payment=None,
        )

    payload = decode_jwt_token(
        str(token), expected_audience="efhc_buy_site"
    )
    if payload.get("kind") != "hub_efhc_handoff":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid handoff kind",
        )
    if payload.get("aud") != "efhc_buy_site":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid handoff audience",
        )

    async with new_session() as db:
        global_id = await _resolve_handoff_owner(db, payload)
        wallets = await wallets_service.list_wallets(
            db, global_id=global_id
        )
        active_intent = await _get_active_intent_truth(
            db=db,
            global_id=global_id,
        )
        active_payment = None
        if active_intent is not None:
            row = await get_intent_status_for_user(
                db,
                global_id=global_id,
                intent_id=int(active_intent.intent_id),
            )
            if row.get("ok"):
                active_payment = PaymentIntentStatusOut(**row)

    active_wallet = next(
        (w for w in wallets if bool(getattr(w, "is_active", False))),
        None,
    )
    active_addr = (
        str(getattr(active_wallet, "wallet_address", ""))
        if active_wallet is not None
        else None
    )
    wallet_items = [WalletItemOut(**w.__dict__) for w in wallets]

    wallet_linked = active_wallet is not None
    flow_truth = _build_flow_truth(
        handoff_configured=bool(_handoff_base_url()),
        wallet_linked=wallet_linked,
        wallet_sync_required=not wallet_linked,
        active_intent=active_intent,
        require_handoff=False,
    )
    return BrowserShopBootstrapOut(
        mode="handoff_bound",
        tg_linked=True,
        global_id=global_id,
        wallet_linked=wallet_linked,
        active_wallet_address=active_addr,
        wallets=wallet_items,
        wallet_sync_required=not wallet_linked,
        bot_open_url=_bot_open_url(),
        telegram_sync_url=_telegram_sync_url(),
        wallet_sync_url=_wallet_sync_url(),
        usdt_checkout_mode=get_usdt_checkout_mode(),
        flow_truth=flow_truth,
        active_payment=active_payment,
    )


@router.get(
    "/browser-shop-catalog",
    response_model=BrowserShopCatalogOut,
    summary="Get browser-shop storefront cards",
    include_in_schema=False,
)
async def get_browser_shop_catalog() -> BrowserShopCatalogOut:
    """Compatibility alias к canonical shopfront catalog helper."""
    return await _browser_shop_catalog()


async def _browser_shop_catalog() -> BrowserShopCatalogOut:
    async with new_session() as db:
        svc = ShopService(db)
        catalog = await svc.get_catalog(0)

    items: list[BrowserShopCatalogItemOut] = []
    for item in catalog.items:
        items.append(
            BrowserShopCatalogItemOut(
                sku=str(item.sku),
                title=str(item.title),
                description=item.description,
                item_type=str(item.type),
                ton_enabled=bool(item.ton_enabled),
                usdt_enabled=bool((item.methods or {}).get("USDT")),
                methods=item.methods,
                image_url=item.image_url,
                category=str(item.category or "other"),
                badge=str(item.badge or ""),
                status=str(item.status or "live"),
                action_mode=str(item.action_mode or "checkout"),
                external_url=item.external_url,
                delivery_mode=str(item.delivery_mode or "manual"),
                quantity_efhc=item.quantity_efhc,
                sort_order=int(item.sort_order or 0),
            )
        )

    return BrowserShopCatalogOut(items=items)


@router.post(
    "/browser-shop-create-intent",
    response_model=BrowserShopCreateIntentOut,
    summary="Create browser-shop external intent",
    include_in_schema=False,
)
async def create_browser_shop_intent(
    payload: BrowserShopCreateIntentIn,
) -> BrowserShopCreateIntentOut:
    """Compatibility alias к canonical shopfront create-intent helper."""
    return await _browser_shop_create_intent(payload)


async def _browser_shop_create_intent(
    payload: BrowserShopCreateIntentIn,
) -> BrowserShopCreateIntentOut:
    token = str(payload.token or "").strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Browser-shop linking is required",
        )

    claims = decode_jwt_token(token, expected_audience="efhc_buy_site")
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

    pay_method = str(payload.pay_method or "").upper()
    if pay_method not in {"TON", "USDT"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported pay method",
        )
    try:
        qty = int(payload.quantity)
    except Exception as err:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid quantity",
        ) from err
    if qty != 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Browser-shop allows one item per operation",
        )

    sku = str(payload.sku or "").strip()
    client_nonce = str(payload.client_nonce or uuid4().hex)
    order_payload = ShopOrderExternalIn(
        sku=sku,
        quantity=qty,
        pay_method=pay_method,
        custom_efhc_amount_d8=payload.custom_efhc_amount_d8,
    )

    async with new_session() as db:
        global_id = await _resolve_handoff_owner(db, claims)
        active_intent = await _get_active_intent_truth(
            db=db,
            global_id=global_id,
        )
        if active_intent is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Active intent already exists; resume the current payment path",
            )

        svc = ShopService(db)
        catalog = await svc.get_catalog(0)
        item = next(
            (it for it in catalog.items if str(it.sku) == sku and bool(it.active)),
            None,
        )
        if item is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Storefront item not found",
            )
        if str(getattr(item, "action_mode", "checkout")) != "checkout":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Storefront item uses an external action",
            )
        methods = getattr(item, "methods", None) or {}
        if pay_method not in methods:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Selected pay method is not enabled for item",
            )

        wallets = await wallets_service.list_wallets(db, global_id=global_id)
        primary_wallet = next(
            (
                wallet
                for wallet in wallets
                if wallet.is_primary and wallet.is_active and wallet.proof_verified
            ),
            None,
        )
        if primary_wallet is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Verified primary wallet is required before intent creation",
            )
        payer_wallet_address = str(primary_wallet.wallet_address)

        try:
            out = await svc.create_external_order_in_transaction(
                _global_id_db(global_id),
                order_payload,
                client_nonce,
            )
        except IdempotencyPayloadConflictError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD",
            ) from exc
        except ValueError as exc:
            detail = str(exc)
            conflict = detail in {
                "VIP_NUMBER_RESERVED",
                "VIP_NUMBER_ALREADY_SOLD",
                "VIP_NUMBER_NOT_AVAILABLE",
            }
            raise HTTPException(
                status_code=(
                    status.HTTP_409_CONFLICT
                    if conflict
                    else status.HTTP_400_BAD_REQUEST
                ),
                detail=detail,
            ) from exc

        pay = getattr(out, "pay", None) or out.get("pay")
        order = getattr(out, "order", None) or out.get("order")
        if not pay or not order:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="External order payload is incomplete",
            )
        asset = str(pay.get("method") or pay_method).upper()
        external_amount_atomic = str(pay.get("external_amount_atomic") or "").strip()
        external_decimals = int(pay.get("external_decimals") or 0)
        if not external_amount_atomic or external_decimals <= 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="External atomic payment snapshot is missing",
            )
        to_addr = str(pay.get("to_wallet") or "").strip()
        item_type = str(getattr(item, "type", "UNKNOWN"))
        efhc_amount_d8 = (
            str(order.get("quantity_efhc") or "0")
            if item_type == "EFHC_PACKAGE"
            else "0"
        )
        try:
            intent = await create_intent_shop_external_in_transaction(
                db,
                global_id=global_id,
                idempotency_key=client_nonce,
                asset=asset,
                external_amount_atomic=external_amount_atomic,
                to_address=to_addr,
                efhc_amount_d8=efhc_amount_d8,
            )
        except ShopPreparationActiveError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except IdempotencyPayloadConflictError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD",
            ) from exc
        except ValueError as exc:
            if str(exc) == "PENDING_INTENT_LIMIT_REACHED":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Active intent already exists; resume the current payment path",
                ) from exc
            raise

        order_id = int(order.get("id") or 0)
        if order_id <= 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="External order id is missing",
            )
        reservation = await bind_vip_number_reservation_in_transaction(
            db,
            item_code=sku,
            global_id=_global_id_db(global_id),
            idempotency_key=client_nonce,
            order_id=order_id,
            intent_id=int(intent["intent_id"]),
            expires_at=intent["expires_at"],
        )
        delivery_wallet_address = (
            payer_wallet_address if item_type.startswith("NFT_VIP") else None
        )
        await db.execute(
            text(
                "UPDATE efhc_core.shop_orders "
                "SET memo = :m, "
                "    extra = COALESCE(extra, '{}'::jsonb) || "
                "    jsonb_build_object("
                "      'intent_payload', :m, "
                "      'intent_id', :iid, "
                "      'payment_owner_global_id', :global_id, "
                "      'payment_intent_kind', 'shop_external', "
                "      'payer_wallet_address', COALESCE(extra->>'payer_wallet_address', :payer_wallet_address), "
                "      'delivery_wallet_address', COALESCE(extra->>'delivery_wallet_address', :delivery_wallet_address), "
                "      'vip_number_reserved', :vip_number_reserved"
                "    ), "
                "    updated_at = :updated_at "
                "WHERE id = :oid"
            ),
            {
                "m": str(intent["payload"]),
                "iid": int(intent["intent_id"]),
                "global_id": global_id,
                "payer_wallet_address": payer_wallet_address,
                "delivery_wallet_address": delivery_wallet_address,
                "vip_number_reserved": (
                    str(reservation["number"]) if reservation else None
                ),
                "updated_at": utcnow(),
                "oid": order_id,
            },
        )
        await db.commit()

    return BrowserShopCreateIntentOut(
        global_id=global_id,
        intent_id=int(intent["intent_id"]),
        order_id=order_id,
        item_type=item_type,
        pay_method=asset,
        amount=str(intent["external_amount_display"]),
        external_amount_atomic=str(intent["external_amount_atomic"]),
        external_decimals=int(intent["external_decimals"]),
        external_amount_display=str(intent["external_amount_display"]),
        memo=str(intent["payload"]),
        to_wallet=to_addr,
        tonconnect_tx=intent.get("tonconnect_tx"),
        tonconnect_transport_kind=intent.get("tonconnect_transport_kind"),
        jetton_master_address=intent.get("jetton_master_address"),
        jetton_decimals=intent.get("jetton_decimals"),
        forward_payload_text=intent.get("forward_payload_text"),
        fee_message_ton_amount=intent.get("fee_message_ton_amount"),
        forward_ton_amount=intent.get("forward_ton_amount"),
        recipient_strategy=intent.get("recipient_strategy"),
        usdt_checkout_mode=intent.get("usdt_checkout_mode"),
        expires_at=intent["expires_at"],
    )


@router.get(
    "/browser-shop-intent-status",
    response_model=PaymentIntentStatusOut,
    summary="Get browser-shop intent status",
    include_in_schema=False,
)
async def get_browser_shop_intent_status(
    token: str,
    intent_id: ApiLifetimeId,
) -> PaymentIntentStatusOut:
    """Compatibility alias к canonical shopfront intent-status helper."""
    return await _browser_shop_intent_status(token=token, intent_id=intent_id)


async def _browser_shop_intent_status(
    token: str,
    intent_id: int,
) -> PaymentIntentStatusOut:
    claims = decode_jwt_token(
        str(token), expected_audience="efhc_buy_site"
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
        row = await get_intent_status_for_user(
            db,
            global_id=global_id,
            intent_id=int(intent_id),
        )
    if not row or row.get("ok") is not True:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment intent not found",
        )
    row.pop("ok", None)
    return PaymentIntentStatusOut(**row)
