# backend/app/routes/deposit_routes.py
# ----------------------------------------------------------------------
# Deposit EFHC (on-chain): A+B контур.
# • packages list (pricing)
# • POST /deposit/efhc → PaymentIntent + TonConnect tx
# ----------------------------------------------------------------------

from __future__ import annotations

from app.core.config_core import get_settings
from app.deps import (
    get_db,
    require_idempotency_key,
    require_wallet_connected,
)
from app.identity.financial_owner import FinancialReadOwner
from app.identity.financial_read_dependency import (
    get_financial_read_owner,
)
from app.identity.types import global_id_from_database
from app.integrations.ton_memo import build_deposit_global_memo
from app.lib.ton_address import TonAddressError, canonicalize_ton_address
from app.schemas.deposit_schemas import (
    DepositEFHCIn,
    DepositEFHCOut,
    DepositPackagesOut,
    DirectDepositOpenOut,
)
from app.services.payment_intents_service import (
    create_intent_deposit_by_package,
)
from app.services.transactions_service import (
    IdempotencyPayloadConflictError,
)
from app.scheduler.check_ton_inbox import run_once as run_ton_watcher_once
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    status,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/deposit", tags=["deposit"])


def _payments_receiver_address() -> str:
    """Fail closed before TON signing if direct deposit cannot be watched.

    Receiver and watcher must monitor the same canonical TON owner address.
    A missing watcher address cannot be replaced by a different payments
    destination: that would allow sending real EFHC without credit monitoring.
    """
    settings = get_settings()
    watched = str(settings.TON_MAIN_WALLET or "").strip()
    if not watched:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DIRECT_DEPOSIT_WATCHER_WALLET_NOT_SET",
        )

    receiver = str(settings.PAYMENTS_RECEIVER_ADDRESS or watched).strip()
    try:
        if canonicalize_ton_address(receiver) != canonicalize_ton_address(watched):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="DIRECT_DEPOSIT_RECEIVER_WATCHER_MISMATCH",
            )
    except TonAddressError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DIRECT_DEPOSIT_RECEIVER_INVALID",
        ) from exc
    return receiver


@router.get(
    "/direct-open",
    response_model=DirectDepositOpenOut,
    status_code=status.HTTP_200_OK,
    summary="Read direct EFHC deposit transfer metadata",
)
@router.post(
    "/direct-open",
    response_model=DirectDepositOpenOut,
    status_code=status.HTTP_200_OK,
    summary="Open direct EFHC deposit wallet link",
)
async def open_direct_deposit(
    owner: FinancialReadOwner = Depends(get_financial_read_owner),
) -> DirectDepositOpenOut:
    """Returns metadata for a direct EFHC jetton transfer.

    This route is not a native TON payment and not a shop purchase.
    The amount is chosen in EFHC by the user in the public modal.
    """

    to_addr = _payments_receiver_address()
    if not to_addr:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="DIRECT_DEPOSIT_RECEIVER_NOT_SET",
        )

    settings = get_settings()
    memo = build_deposit_global_memo(str(global_id_from_database(owner.global_id)))
    master = str(settings.EFHC_JETTON_MASTER_ADDRESS or "").strip()
    if not master:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="EFHC_JETTON_MASTER_NOT_SET",
        )
    return DirectDepositOpenOut(
        receiver_owner_address=to_addr,
        jetton_master_address=master,
        jetton_decimals=int(settings.EFHC_JETTON_DECIMALS or 8),
        forward_payload_text=memo,
        fee_message_ton_amount=str(
            settings.JETTON_TRANSFER_FEE_NANO or "50000000"
        ),
        forward_ton_amount=str(
            settings.JETTON_FORWARD_TON_AMOUNT_NANO or "1"
        ),
    )


@router.post(
    "/direct-check",
    status_code=status.HTTP_200_OK,
    summary="Trigger shared TON deposit verification by authenticated user activity",
)
async def check_direct_deposit(
    owner: FinancialReadOwner = Depends(get_financial_read_owner),
) -> dict[str, bool | str]:
    """The user triggers a global verified watcher pass, never an admin credit.

    No Global ID, tx_hash or amount is trusted from the caller. The shared
    watcher reads TON itself and resolves every recipient through its memo.
    Other users' transactions or balances are never exposed to the caller.
    """
    _ = owner.global_id  # Verified server-side identity, not a client selector.
    result = await run_ton_watcher_once(activity_trigger=True)
    if result.get("status") in {"error", "timeout_error"}:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DIRECT_DEPOSIT_CHECK_UNAVAILABLE",
        )
    if result.get("status") == "skipped":
        reason = str(result.get("reason") or "")
        state = "cooldown" if reason == "cooldown" else "busy"
    else:
        state = "checked"
    return {"ok": True, "state": state}


@router.get(
    "/packages",
    response_model=DepositPackagesOut,
    summary="Active EFHC sale packages (for deposit)",
)
async def list_deposit_packages(
    db: AsyncSession = Depends(get_db),
) -> DepositPackagesOut:
    # Канон: пакеты депозита берём из ORM-таблицы efhc_core.shop_items.
    # Важно: это устраняет зависимость от не-ORM таблиц (efhc_admin.*).
    # локально, чтобы не тянуть лишнее при импорте модуля
    from app.deps import d8
    from app.models.shop_models import ShopItem

    stmt = (
        select(ShopItem)
        .where(ShopItem.is_active.is_(True))
        .where(ShopItem.quantity_efhc.is_not(None))
        .order_by(ShopItem.id.asc())
    )
    rows = (await db.execute(stmt)).scalars().all()

    items = []
    for obj in rows:
        extra = obj.extra or {}
        asset = str(extra.get("asset") or "TON").upper()
        price_asset_d8 = extra.get("price_asset_d8")
        if price_asset_d8 is None:
            # Если цена не задана — не показываем позицию в депозит-
            # пакетах.
            continue
        items.append(
            {
                "id": int(obj.id),
                "title": str(obj.title or ""),
                "asset": asset,
                "price_asset_d8": str(d8(price_asset_d8)),
                # quantity_efhc хранится как Decimal(30,8) — это и есть
                # d8.
                "efhc_amount_d8": str(d8(obj.quantity_efhc)),
                "is_active": bool(obj.is_active),
            }
        )

    return DepositPackagesOut(items=items)


@router.post(
    "/efhc",
    response_model=DepositEFHCOut,
    status_code=status.HTTP_200_OK,
    summary="Deposit EFHC (on-chain, TonConnect required)",
)
async def deposit_efhc(
    request: Request,
    payload: DepositEFHCIn,
    db: AsyncSession = Depends(get_db),
    _idk: str = Depends(require_idempotency_key),
    owner: FinancialReadOwner = Depends(get_financial_read_owner),
) -> DepositEFHCOut:
    """Создаёт deposit-intent и возвращает TonConnect transaction."""

    await require_wallet_connected(
        request,
        db=db,
        current_global_id=str(global_id_from_database(owner.global_id)),
        feature="deposit",
    )

    try:
        result = await create_intent_deposit_by_package(
            db,
            global_id=str(global_id_from_database(owner.global_id)),
            idempotency_key=str(_idk),
            package_id=int(payload.package_id),
        )
    except IdempotencyPayloadConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD",
        ) from exc
    return DepositEFHCOut(
        intent_id=int(result["intent_id"]),
        asset=str(result["asset"]),
        amount_asset_d8=str(result["amount_asset_d8"]),
        external_amount_atomic=str(result["external_amount_atomic"]),
        external_decimals=int(result["external_decimals"]),
        external_amount_display=str(result["external_amount_display"]),
        efhc_amount_d8=str(result["efhc_amount_d8"]),
        payload=str(result["payload"]),
        tonconnect_tx=result["tonconnect_tx"],
    )
