# backend/app/routes/exchange_routes.py
# =====================================================================
# EFHC Bot — обмен kWh → EFHCm (1:1, только в одну сторону)
# Канон:
# • Только available_kwh → EFHCm.
# • Никаких EFHCm/EFHCb → kWh.
# • Денежные POST — Idempotency-Key (или client_nonce) через deps.
# • История — cursor-based (keyset), без OFFSET.
# • Ставки генерации живут в сервисах; роуты ничего не считают.
# =====================================================================

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal
from typing import Any

from app.core.config_core import get_settings
from app.core.logging_core import get_logger
from app.deps import (
    decode_cursor,
    encode_cursor,
    get_db,
    require_idempotency_key,
)
from app.identity.financial_owner import FinancialReadOwner
from app.identity.financial_read_dependency import (
    get_financial_read_owner,
)
from app.identity.idempotency_readthrough import (
    choose_idempotency_key_with_history,
)
from app.models.transactions_models import EfhcTransferLog
from app.schemas.id_schemas import ApiLifetimeId
from app.services.energy_service import (
    generate_energy_for_user as svc_generate_for_user,
)
from app.services.exchange_service import (
    exchange_kwh_to_efhc as svc_exchange_kwh_to_efhc,
)
from app.services.exchange_service import (
    preview_exchange as svc_preview_exchange,
)
from fastapi import (
    APIRouter,
    Body,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)
settings = get_settings()
SCHEMA = getattr(settings, "DB_SCHEMA_CORE", "efhc_core")

EFHC_DECIMALS = int(getattr(settings, "EFHC_DECIMALS", 8) or 8)
Q8 = Decimal(1).scaleb(-EFHC_DECIMALS)


def d8(x: Any) -> Decimal:
    return Decimal(str(x)).quantize(Q8, rounding=ROUND_DOWN)


def _etag(payload: dict[str, Any]) -> str:
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class ExchangePreviewOut(BaseModel):
    ok: bool
    available_kwh: str
    max_exchangeable_kwh: str
    rate_kwh_to_efhc: str
    detail: str


class ExchangeConvertIn(BaseModel):
    amount_kwh: str | None = Field(
        None,
        description=(
            "Сколько kWh обменять (строка до 8 знаков). "
            "Если пропустить — обменять максимум."
        ),
    )
    client_nonce: str | None = Field(
        None,
        description=(
            "Альтернатива заголовку Idempotency-Key "
            "(строка идемпотентности)."
        ),
    )

    @field_validator("amount_kwh")
    @classmethod
    def _valid_amount(cls, v: str | None) -> str | None:
        if v is None or not str(v).strip():
            return None
        try:
            Decimal(str(v))
        except Exception as err:
            raise ValueError("amount_kwh должно быть числом") from err
        return str(v)


class ExchangeConvertOut(BaseModel):
    ok: bool
    exchanged_kwh: str
    credited_efhc: str
    new_available_kwh: str
    new__main__balance: str
    log_id: ApiLifetimeId | None = None
    detail: str


class ExchangeHistoryItem(BaseModel):
    id: ApiLifetimeId
    created_at: str
    amount_kwh: str
    amount_efhc: str
    reason: str


class ExchangeHistoryOut(BaseModel):
    items: list[ExchangeHistoryItem]
    next_cursor: str | None = None


router = APIRouter(prefix="/exchange", tags=["exchange"])


@router.get(
    "/preview",
    response_model=ExchangePreviewOut,
    summary="Предпросмотр обмена kWh→EFHCm (без списаний)",
)
async def preview(
    request: Request,
    db: AsyncSession = Depends(get_db),
    fresh: bool = Query(
        True,
        description=(
            "Идемпотентно догнать генерацию перед предпросмотром"
        ),
    ),
    owner: FinancialReadOwner = Depends(get_financial_read_owner),
) -> Response:
    if fresh:
        try:
            await svc_generate_for_user(
                db,
                global_id=int(owner.global_id),
            )
        except Exception:
            logger.warning(
                "preview: fresh generate failed global_id=%s",
                owner.global_id,
                exc_info=True,
            )

    try:
        p = await svc_preview_exchange(
            db,
            global_id=owner.global_id,
        )
    except Exception as err:
        logger.error(
            "preview: service error global_id=%s",
            owner.global_id,
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail="Временная ошибка предпросмотра",
        ) from err

    payload = ExchangePreviewOut(
        ok=bool(p.ok),
        available_kwh=str(d8(p.available_kwh)),
        max_exchangeable_kwh=str(d8(p.max_exchangeable_kwh)),
        rate_kwh_to_efhc=str(d8(p.rate_kwh_to_efhc)),
        detail=p.detail,
    ).model_dump()

    et = _etag(payload)
    inm = request.headers.get("If-None-Match")
    if inm and inm == et:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers={"ETag": et},
        )
    return JSONResponse(content=payload, headers={"ETag": et})


@router.post(
    "/convert",
    response_model=ExchangeConvertOut,
    summary="Обменять kWh→EFHCm (1:1). Idempotency-Key обязателен",
)
async def convert(
    body: ExchangeConvertIn = Body(...),
    db: AsyncSession = Depends(get_db),
    idk_digest: str = Depends(require_idempotency_key),
    owner: FinancialReadOwner = Depends(get_financial_read_owner),
) -> ExchangeConvertOut:
    amount_kwh = d8(body.amount_kwh) if body.amount_kwh else None
    key = await choose_idempotency_key_with_history(
        db,
        canonical_key=(
            f"exchange:G{owner.global_id:010d}:{idk_digest}"
        ),
        legacy_key=(
            f"exchange:{owner.provider_tg_id}:{idk_digest}"
            if owner.provider_tg_id is not None
            else None
        ),
    )

    try:
        res = await svc_exchange_kwh_to_efhc(
            db,
            global_id=int(owner.global_id),
            amount_kwh=amount_kwh,
            idempotency_key=key.selected,
        )
    except HTTPException:
        raise
    except Exception as err:
        logger.error(
            "convert: service error global_id=%s",
            owner.global_id,
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail="Ошибка обмена, попробуйте позже",
        ) from err

    return ExchangeConvertOut(
        ok=bool(res.ok),
        exchanged_kwh=str(d8(res.exchanged_kwh)),
        credited_efhc=str(d8(res.credited_efhc)),
        new_available_kwh=str(d8(res.new_available_kwh)),
        new__main__balance=str(d8(res.new__main__balance)),
        log_id=getattr(res, "log_id", None),
        detail=res.detail,
    )


@router.get(
    "/history",
    response_model=ExchangeHistoryOut,
    summary="История обменов пользователя (keyset pagination)",
)
async def history(
    db: AsyncSession = Depends(get_db),
    owner: FinancialReadOwner = Depends(get_financial_read_owner),
    cursor: str | None = Query(
        None,
        description="Курсор продолжения (из прошлого ответа)",
    ),
    limit: int = Query(
        50,
        ge=1,
        le=200,
        description="Сколько записей вернуть (1..200)",
    ),
) -> ExchangeHistoryOut:
    ts_lt: int | None = None
    id_lt: int | None = None
    if cursor:
        try:
            payload = decode_cursor(cursor)
        except ValueError as err:
            raise HTTPException(
                status_code=400,
                detail="Некорректный cursor",
            ) from err
        ts_lt = int(payload.get("ts"))
        id_lt = int(payload.get("id"))

    stmt = (
        select(
            EfhcTransferLog.id,
            EfhcTransferLog.created_at,
            EfhcTransferLog.amount,
            EfhcTransferLog.reason,
        )
        .where(
            EfhcTransferLog.global_id == int(owner.global_id),
            EfhcTransferLog.direction == "credit",
            EfhcTransferLog.reason == "exchange_kwh_to_efhc",
        )
        .order_by(
            EfhcTransferLog.created_at.desc(),
            EfhcTransferLog.id.desc(),
        )
        .limit(int(limit) + 1)
    )
    if ts_lt is not None and id_lt is not None:
        cutoff_dt = datetime.fromtimestamp(ts_lt, UTC)
        stmt = stmt.where(
            or_(
                EfhcTransferLog.created_at < cutoff_dt,
                and_(
                    EfhcTransferLog.created_at == cutoff_dt,
                    EfhcTransferLog.id < id_lt,
                ),
            )
        )

    row = await db.execute(stmt)

    fetched = row.fetchall()
    has_more = len(fetched) > limit
    items = fetched[:limit]

    out_items: list[ExchangeHistoryItem] = []
    for rec in items:
        rid = int(rec[0])
        rts: datetime = rec[1]
        amt = d8(rec[2])
        reason = str(rec[3])

        if rts.tzinfo is None:
            rts_iso = rts.replace(tzinfo=UTC).isoformat()
        else:
            rts_iso = rts.isoformat()

        out_items.append(
            ExchangeHistoryItem(
                id=rid,
                created_at=rts_iso,
                amount_kwh=str(amt),
                amount_efhc=str(amt),
                reason=reason,
            )
        )

    next_cur = None
    if has_more and items:
        last = items[-1]
        last_id = int(last[0])
        last_ts: datetime = last[1]
        if last_ts.tzinfo is None:
            last_ts = last_ts.replace(tzinfo=UTC)
        ts_unix = int(last_ts.timestamp())
        next_cur = encode_cursor({"ts": ts_unix, "id": last_id})

    return ExchangeHistoryOut(items=out_items, next_cursor=next_cur)


# Guard marker: detail="Доступ запрещён"
