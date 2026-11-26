# backend/app/routes/withdraw_routes.py
# ======================================================================
# Пользовательские ручки заявок на вывод EFHCm.
# - Денежные POST требуют Idempotency-Key.
# - Создание заявки холдирует сумму у пользователя.
#   Далее сумма уходит в Банк (через сервис).
# - Отмена делает рефанд (через сервис).
# - Список и детали: cursor + ETag/If-None-Match.
# ======================================================================

from __future__ import annotations

from datetime import UTC
from decimal import Decimal, InvalidOperation
from typing import Any

from app.core.config_core import get_settings
from app.core.logging_core import get_logger
from app.deps import (
    d8,
    get_db,
    require_idempotency_key,
    require_wallet_connected,
)
from app.identity.financial_owner import FinancialReadOwner
from app.identity.financial_read_dependency import (
    get_financial_read_owner,
)
from app.identity.types import global_id_from_database
from app.schemas.id_schemas import ApiLifetimeId
from app.services import wallets_service
from app.services.withdraw_service import (
    MIN_WITHDRAW_EFHC,
    WithdrawPageDTO,
    WithdrawRequestDTO,
    cancel_withdraw,
    list_user_withdraws,
    request_withdraw,
)
from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Request,
    Response,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)
settings = get_settings()
SCHEMA = getattr(settings, "DB_SCHEMA_CORE", "efhc_core")

router = APIRouter(prefix="/withdraw", tags=["withdraw"])


def _build_etag(payload: dict[str, Any]) -> str:
    import hashlib
    import json

    raw = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class WithdrawCreateIn(BaseModel):
    amount: str = Field(
        ...,
        description="Сумма EFHCm к выводу (d8 строкой)",
    )
    wallet_id: ApiLifetimeId = Field(
        ...,
        gt=0,
        description="ID выбранной verified active wallet binding текущего global_id",
    )


class WithdrawOut(BaseModel):
    id: ApiLifetimeId
    global_id: str
    amount: str
    status: str
    created_at: str
    updated_at: str


class WithdrawDetailOut(WithdrawOut):
    idempotency_key: str
    hold_done: bool
    refund_done: bool
    payout_ref: str | None = None


class WithdrawPageOut(BaseModel):
    items: list[WithdrawOut]
    next_cursor: str | None


def _parse_amount(amount: str) -> Decimal:
    try:
        return Decimal(str(d8(Decimal(amount))))
    except (InvalidOperation, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail=(
                "amount must be a valid decimal string "
                "with up to 8 digits after the point."
            ),
        ) from exc


def _as_detail(dto: WithdrawRequestDTO) -> WithdrawDetailOut:
    return WithdrawDetailOut(
        id=dto.id,
        global_id=f"{int(dto.global_id or 0):010d}",
        amount=str(d8(dto.amount)),
        status=dto.status,
        idempotency_key=dto.idempotency_key,
        hold_done=bool(dto.hold_done),
        refund_done=bool(dto.refund_done),
        payout_ref=dto.payout_ref,
        created_at=dto.created_at,
        updated_at=dto.updated_at,
    )


@router.post(
    "/request",
    response_model=WithdrawDetailOut,
    summary="Создать заявку на вывод EFHCm",
)
async def post_withdraw_request(
    request: Request,
    body: WithdrawCreateIn,
    db: AsyncSession = Depends(get_db),
    idempotency_key: str = Depends(require_idempotency_key),
    owner: FinancialReadOwner = Depends(get_financial_read_owner),
) -> WithdrawDetailOut:
    await require_wallet_connected(
        request,
        db=db,
        current_global_id=str(global_id_from_database(owner.global_id)),
        feature="withdraw",
    )
    selected_wallet = await wallets_service.get_verified_active_wallet(
        db,
        global_id=str(global_id_from_database(owner.global_id)),
        wallet_id=int(body.wallet_id),
    )
    if selected_wallet is None:
        raise HTTPException(
            status_code=400,
            detail="SELECTED_WALLET_NOT_AVAILABLE",
        )
    amt = _parse_amount(body.amount)
    if amt < MIN_WITHDRAW_EFHC:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Минимальная сумма вывода: {MIN_WITHDRAW_EFHC} EFHCm"
            ),
        )

    try:
        dto = await request_withdraw(
            db,
            global_id=int(owner.global_id),
            amount=amt,
            idempotency_key=str(idempotency_key),
            external_address=selected_wallet.wallet_address,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("post_withdraw_request failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Временная ошибка. Повторите позже.",
        ) from exc

    return _as_detail(dto)


@router.post(
    "/{request_id}/cancel",
    response_model=WithdrawDetailOut,
    summary="Отменить заявку",
)
async def post_withdraw_cancel(
    request_id: ApiLifetimeId,
    db: AsyncSession = Depends(get_db),
    idempotency_key: str = Depends(require_idempotency_key),
    owner: FinancialReadOwner = Depends(get_financial_read_owner),
) -> WithdrawDetailOut:
    try:
        dto = await cancel_withdraw(
            db,
            request_id=int(request_id),
            global_id=int(owner.global_id),
            idempotency_key=str(idempotency_key),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("post_withdraw_cancel failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Временная ошибка. Повторите позже.",
        ) from exc

    return _as_detail(dto)


@router.get(
    "/list/me",
    response_model=WithdrawPageOut,
    summary="Список заявок текущего пользователя",
)
@router.get(
    "/list",
    response_model=WithdrawPageOut,
    summary="Список заявок пользователя",
)
async def get_withdraw_list(
    limit: int = 100,
    cursor: str | None = None,
    status_filter: str | None = None,
    if_none_match: str | None = Header(
        None,
        convert_underscores=True,
    ),
    db: AsyncSession = Depends(get_db),
    owner: FinancialReadOwner = Depends(get_financial_read_owner),
) -> WithdrawPageOut:
    try:
        page: WithdrawPageDTO = await list_user_withdraws(
            db,
            global_id=owner.global_id,
            limit=int(limit),
            cursor=cursor,
            status_filter=(status_filter or None),
        )
    except Exception as exc:
        logger.error("get_withdraw_list failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Временная ошибка при чтении заявок.",
        ) from exc

    items = [
        WithdrawOut(
            id=i.id,
            global_id=f"{int(i.global_id or owner.global_id):010d}",
            amount=str(d8(i.amount)),
            status=i.status,
            created_at=i.created_at,
            updated_at=i.updated_at,
        )
        for i in page.items
    ]
    payload = {
        "scope": "withdraw_list",
        "global_id": int(owner.global_id),
        "next_cursor": page.next_cursor or "",
        "items": [it.model_dump() for it in items],
    }
    etag = _build_etag(payload)

    if if_none_match and if_none_match.strip() == etag:
        raise HTTPException(
            status_code=status.HTTP_304_NOT_MODIFIED,
            detail="Not Modified",
        )

    resp = Response(
        content=WithdrawPageOut(
            items=items,
            next_cursor=page.next_cursor,
        ).model_dump_json(),
        status_code=status.HTTP_200_OK,
        media_type="application/json",
        headers={"ETag": etag},
    )
    return resp  # type: ignore[return-value]


@router.get(
    "/{request_id}",
    response_model=WithdrawDetailOut,
    summary="Детали заявки",
)
async def get_withdraw_detail(
    request_id: ApiLifetimeId,
    if_none_match: str | None = Header(
        None,
        convert_underscores=True,
    ),
    db: AsyncSession = Depends(get_db),
    owner: FinancialReadOwner = Depends(get_financial_read_owner),
) -> WithdrawDetailOut:
    q = text(
        "\n".join(
            [
                "SELECT",
                "  id,",
                "  amount,",
                "  status,",
                "  idempotency_key AS idempotency_key,",
                "  hold_done,",
                "  refund_done,",
                "  payout_ref,",
                "  created_at,",
                "  updated_at,",
                "  global_id",
                f"FROM {SCHEMA}.withdraw_requests",
                "WHERE id = :rid AND global_id = :global_id",
                "LIMIT 1",
            ]
        )
    )
    params = {
        "rid": int(request_id),
        "global_id": int(owner.global_id),
    }
    r = await db.execute(q, params)
    row = r.fetchone()
    if not row:
        raise HTTPException(
            status_code=404,
            detail="Заявка не найдена.",
        )

    dto = WithdrawRequestDTO(
        id=int(row[0]),
        tg_id=None,
        amount=d8(row[1]),
        status=str(row[2]),
        idempotency_key=str(row[3]),
        hold_done=bool(row[4]),
        refund_done=bool(row[5]),
        payout_ref=(str(row[6]) if row[6] else None),
        created_at=row[7].astimezone(UTC).isoformat(),
        updated_at=row[8].astimezone(UTC).isoformat(),
        global_id=int(row[9]),
    )

    out = _as_detail(dto)
    payload = {
        "scope": "withdraw_detail",
        "id": out.id,
        "global_id": out.global_id,
        "amount": out.amount,
        "status": out.status,
        "idempotency_key": out.idempotency_key,
        "hold_done": bool(out.hold_done),
        "refund_done": bool(out.refund_done),
        "payout_ref": out.payout_ref or "",
        "updated_at": out.updated_at,
    }
    etag = _build_etag(payload)

    if if_none_match and if_none_match.strip() == etag:
        raise HTTPException(
            status_code=status.HTTP_304_NOT_MODIFIED,
            detail="Not Modified",
        )

    resp = Response(
        content=out.model_dump_json(),
        status_code=status.HTTP_200_OK,
        media_type="application/json",
        headers={"ETag": etag},
    )
    return resp  # type: ignore[return-value]


__all__ = ["router"]
