from __future__ import annotations

from app.crud.transactions_crud import list_user_transfers_desc_cursor
from app.deps import (
    get_current_telegram_subject_id,
    get_db,
    require_idempotency_key_header_only,
)
from app.identity.financial_owner import FinancialReadOwner
from app.identity.financial_read_dependency import (
    get_financial_read_owner,
)
from app.identity.types import global_id_from_database
from app.schemas.id_schemas import ApiLifetimeId
from app.schemas.wallet_schemas import (
    WalletBalanceHistoryItem,
    WalletBalanceHistoryOut,
    WalletConnectIn,
    WalletConnectOut,
    WalletItemOut,
    WalletMeOut,
    WalletTonProofCheckIn,
    WalletTonProofCheckOut,
    WalletTonProofPayloadOut,
)
from app.services import tonconnect_proof_service, wallets_service
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/wallets", tags=["wallets"])


@router.get(
    "/me",
    response_model=WalletMeOut,
    summary="Список привязанных кошельков пользователя",
)
async def wallets_me(
    request: Request,
    db: AsyncSession = Depends(get_db),
    owner: FinancialReadOwner = Depends(get_financial_read_owner),
) -> WalletMeOut:
    gid = str(global_id_from_database(owner.global_id))
    project_lease_hash = getattr(request.state, "genesis_project_wallet_lease_hash", None)
    items = await wallets_service.list_wallets(
        db, global_id=gid, **({"project_lease_hash": project_lease_hash} if project_lease_hash else {})
    )
    wallets = [WalletItemOut.model_validate(w, from_attributes=True) for w in items]
    return WalletMeOut(
        is_connected=any(w.is_active and w.proof_verified for w in wallets),
        wallets=wallets,
    )


@router.get(
    "/tonconnect/proof-payload",
    response_model=WalletTonProofPayloadOut,
    summary="Выдать payload для TonConnect ton_proof",
)
async def tonconnect_proof_payload(
    request: Request,
    telegram_subject_id: int = Depends(get_current_telegram_subject_id),
) -> WalletTonProofPayloadOut:
    out = tonconnect_proof_service.issue_payload(
        tg_id=int(telegram_subject_id),
        host=request.url.hostname,
    )
    return WalletTonProofPayloadOut(
        ton_proof_payload=out.payload,
        payload_token=out.payload_token,
        expires_at=out.expires_at,
        domain=out.domain,
    )


@router.post(
    "/tonconnect/check-proof",
    response_model=WalletTonProofCheckOut,
    summary="Проверить TonConnect ton_proof",
)
async def tonconnect_check_proof(
    request: Request,
    payload: WalletTonProofCheckIn,
    telegram_subject_id: int = Depends(get_current_telegram_subject_id),
) -> WalletTonProofCheckOut:
    try:
        out = await tonconnect_proof_service.check_proof(
            tg_id=int(telegram_subject_id),
            host=request.url.hostname,
            address=payload.address,
            payload_token=payload.payload_token,
            proof=payload.proof.model_dump(),
            public_key=payload.public_key,
            network=payload.network,
        )
        return WalletTonProofCheckOut(
            accepted=out.accepted,
            cryptographically_verified=out.cryptographically_verified,
            reason=out.reason,
        )
    except tonconnect_proof_service.TonProofExpired as err:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "E001_VALIDATION",
                "message": str(err),
                "details": {"source": "tonconnect_proof"},
            },
        ) from err
    except tonconnect_proof_service.TonProofInvalid as err:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "E001_VALIDATION",
                "message": str(err),
                "details": {"source": "tonconnect_proof"},
            },
        ) from err


@router.get(
    "/balance-history",
    response_model=WalletBalanceHistoryOut,
    summary="История изменения main/bonus балансов пользователя",
)
async def balance_history(
    request: Request,
    db: AsyncSession = Depends(get_db),
    owner: FinancialReadOwner = Depends(get_financial_read_owner),
    cursor: str | None = Query(
        None,
        description="Курсор следующей страницы.",
    ),
    limit: int = Query(
        20,
        ge=1,
        le=100,
        description="Сколько записей вернуть.",
    ),
) -> WalletBalanceHistoryOut:
    items, next_cursor = await list_user_transfers_desc_cursor(
        db,
        global_id=str(global_id_from_database(owner.global_id)),
        limit=limit,
        next_cursor=cursor,
    )
    rows = [
        WalletBalanceHistoryItem(
            id=int(r.id),
            amount_efhc=str(r.amount),
            direction=str(r.direction),
            balance_type=str(r.balance_type),
            reason=str(r.reason),
            created_at=r.created_at,
        )
        for r in items
    ]
    return WalletBalanceHistoryOut(
        items=rows,
        next_cursor=next_cursor,
    )


@router.post(
    "/connect",
    response_model=WalletConnectOut,
    summary="Привязать TON-кошелёк к tg_id (TonConnect)",
)
async def connect_wallet(
    request: Request,
    payload: WalletConnectIn,
    db: AsyncSession = Depends(get_db),
    telegram_subject_id: int = Depends(get_current_telegram_subject_id),
    owner: FinancialReadOwner = Depends(get_financial_read_owner),
    _idk: str = Depends(require_idempotency_key_header_only),
) -> WalletConnectOut:
    tg_id = int(telegram_subject_id)

    try:
        proof_out = await tonconnect_proof_service.check_proof(
            tg_id=tg_id,
            host=request.url.hostname,
            address=payload.address,
            payload_token=payload.payload_token,
            proof=payload.proof.model_dump(),
            public_key=payload.public_key,
            network=payload.network,
        )
        if not (
            proof_out.accepted
            and proof_out.cryptographically_verified
        ):
            raise tonconnect_proof_service.TonProofInvalid(
                "TONCONNECT_PROOF_REQUIRED"
            )
        res = await wallets_service.connect_wallet(
            db,
            global_id=str(global_id_from_database(owner.global_id)),
            provider_tg_id=tg_id,
            address=payload.address,
            wallet_app=payload.wallet_app,
            idempotency_key=_idk,
            verified_proof_payload_token=payload.payload_token,
            verified_proof_source=proof_out.reason,
        )
        return WalletConnectOut(**res)
    except tonconnect_proof_service.TonProofExpired as err:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "E001_VALIDATION",
                "message": str(err),
                "details": {"source": "tonconnect_proof"},
            },
        ) from err
    except tonconnect_proof_service.TonProofInvalid as err:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "E001_VALIDATION",
                "message": str(err),
                "details": {"source": "tonconnect_proof"},
            },
        ) from err
    except wallets_service.InvalidWalletAddress as err:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "E001_VALIDATION",
                "message": "INVALID_WALLET_ADDRESS",
                "details": {"field": "address"},
            },
        ) from err
    except wallets_service.WalletConflict as err:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "E003_CONFLICT",
                "message": "WALLET_CONFLICT",
                "details": {"entity": "wallet_binding"},
            },
        ) from err
    except wallets_service.WalletProofRequired as err:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "E001_VALIDATION",
                "message": str(err),
                "details": {"source": "tonconnect_proof"},
            },
        ) from err
    except wallets_service.WalletProofReplay as err:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "E003_CONFLICT",
                "message": str(err),
                "details": {"entity": "wallet_proof"},
            },
        ) from err


@router.post(
    "/{wallet_id}/make-primary",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Сделать кошелёк primary",
)
async def make_primary(
    request: Request,
    wallet_id: ApiLifetimeId,
    db: AsyncSession = Depends(get_db),
    owner: FinancialReadOwner = Depends(get_financial_read_owner),
) -> None:
    gid = str(global_id_from_database(owner.global_id))
    lease_hash = getattr(request.state, "genesis_project_wallet_lease_hash", None)
    if lease_hash:
        try:
            if await wallets_service.manage_project_test_wallet(
                db, global_id=gid, wallet_id=wallet_id, lease_hash=lease_hash, remove=False,
            ):
                return
        except wallets_service.WalletConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    await wallets_service.make_primary(db, global_id=gid, wallet_id=wallet_id)


@router.delete(
    "/{wallet_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Деактивировать привязку кошелька",
)
async def delete_wallet(
    request: Request,
    wallet_id: ApiLifetimeId,
    db: AsyncSession = Depends(get_db),
    owner: FinancialReadOwner = Depends(get_financial_read_owner),
) -> None:
    gid = str(global_id_from_database(owner.global_id))
    lease_hash = getattr(request.state, "genesis_project_wallet_lease_hash", None)
    if lease_hash:
        try:
            if await wallets_service.manage_project_test_wallet(
                db, global_id=gid, wallet_id=wallet_id, lease_hash=lease_hash, remove=True,
            ):
                return
        except wallets_service.WalletConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    await wallets_service.deactivate_wallet(db, global_id=gid, wallet_id=wallet_id)
