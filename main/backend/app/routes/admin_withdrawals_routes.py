# backend/app/routes/admin_withdrawals_routes.py
# ======================================================================
# EFHC Bot — Admin: withdrawals.
# - Внешняя идентификация: только global_id.
# - Финансовая модерация требует Idempotency-Key.
# - Роуты тонкие, логика в сервисах.
# ======================================================================

from __future__ import annotations

from typing import Any

from app.core.logging_core import get_logger
from app.deps import (
    get_db,
    require_admin,
    require_admin_write,
    require_idempotency_key_header_only,
)
from app.identity.api_contract import ApiExternalGlobalId
from app.schemas.id_schemas import ApiLifetimeId
from app.schemas.outcome_schemas import (
    OutcomeCommentSchema,
    OutcomePromoSchema,
    WithdrawOutcomeBundleSchema,
    WithdrawOutcomePreviewSchema,
)
from app.services.admin.admin_logging import AdminLogger
from app.services.admin.admin_rbac import AdminUser
from app.services.admin.admin_withdrawals_service import (
    WithdrawalApproveRequest,
    WithdrawalFilters,
    WithdrawalPayoutReserveRequest,
    WithdrawalRecord,
    WithdrawalsService,
)
from app.services.common_errors import EfhcConflictError
from app.services.outcome_service import (
    get_admin_withdraw_outcome_preview,
)
from app.services.withdraw_service import ensure_consistency
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(
    prefix="/admin/withdrawals",
    tags=["admin:withdrawals"],
)
logger = get_logger(__name__)


def _admin_from_context(auth: Any) -> AdminUser:
    """Преобразовать проверенный admin context без повышения роли."""

    return AdminUser(
        id=int(auth.admin_id),
        global_id=int(auth.global_id),
        tg_id=None,
        role=str(auth.role),
        is_active=True,
    )


def _withdraw_paid_request(
    raw: dict[str, Any] | None,
    *,
    idempotency_key: str,
) -> WithdrawalApproveRequest:
    data = raw or {}
    return WithdrawalApproveRequest(
        tx_hash=data.get("tx_hash"),
        payout_ref=data.get("payout_ref"),
        wallet_send_confirmed=bool(
            data.get("wallet_send_confirmed", False)
        ),
        wallet_provider=data.get("wallet_provider"),
        sender_wallet_address=data.get("sender_wallet_address"),
        confirmation_mode=data.get("confirmation_mode"),
        reason=data.get("reason"),
        comment_override=data.get("comment_override"),
        comment_auto_translated=bool(
            data.get("comment_auto_translated", False)
        ),
        idempotency_key=str(idempotency_key),
    )


class RejectIn(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)
    comment_override: str | None = Field(default=None, max_length=1500)
    comment_auto_translated: bool = False


class WithdrawRepairOut(BaseModel):
    ok: bool
    auto_fixed_hold: int
    auto_fixed_refund: int


@router.post("/repair-consistency", response_model=WithdrawRepairOut)
async def admin_repair_consistency(
    scan_minutes: int = Query(default=240, ge=1, le=1440),
    batch_limit: int = Query(default=200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    auth: Any = Depends(require_admin_write),
    idempotency_key: str = Depends(
        require_idempotency_key_header_only,
    ),
) -> WithdrawRepairOut:
    admin = _admin_from_context(auth)
    try:
        stats = await ensure_consistency(
            db,
            scan_minutes=int(scan_minutes),
            batch_limit=int(batch_limit),
            actor_global_id=admin.global_id,
            admin_id=admin.id,
            operation_idempotency_key=str(idempotency_key),
        )
    except EfhcConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return WithdrawRepairOut(
        ok=True,
        auto_fixed_hold=int(stats.get("auto_fixed_hold", 0) or 0),
        auto_fixed_refund=int(stats.get("auto_fixed_refund", 0) or 0),
    )


@router.get("", response_model=list[WithdrawalRecord])
async def admin_list_withdrawals(
    global_id: ApiExternalGlobalId | None = Query(default=None),
    status_filter: str | None = Query(
        default=None,
        alias="status",
    ),
    vip_only: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _auth: Any = Depends(require_admin),
) -> list[WithdrawalRecord]:
    filters = WithdrawalFilters(
        global_id=global_id,
        status=(status_filter or None),
        vip_only=bool(vip_only),
        limit=int(limit),
        offset=int(offset),
    )
    try:
        rows = await WithdrawalsService.list_withdrawals(
            db,
            filters=filters,
        )
        return list(rows)
    except Exception:
        logger.exception("withdrawals list failed")
        raise HTTPException(
            status_code=500,
            detail="ADMIN_WITHDRAWALS_UNAVAILABLE",
        ) from None


@router.post("/{request_id}/payout-reserve")
async def admin_payout_reserve(
    request_id: ApiLifetimeId,
    payload: WithdrawalPayoutReserveRequest,
    db: AsyncSession = Depends(get_db),
    auth: Any = Depends(require_admin_write),
    idempotency_key: str = Depends(
        require_idempotency_key_header_only,
    ),
) -> dict:
    """Reserve one server-authoritative payout attempt before wallet Send."""
    admin = _admin_from_context(auth)
    try:
        out = await WithdrawalsService.reserve_payout_attempt(
            db,
            withdrawal_id=int(request_id),
            req=payload,
            idempotency_key=str(idempotency_key),
            admin=admin,
        )
        return {"ok": True, "result": out}
    except EfhcConflictError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        await db.rollback()
        logger.exception("withdraw payout reserve failed")
        raise HTTPException(
            status_code=500, detail="WITHDRAW_PAYOUT_RESERVE_UNAVAILABLE"
        ) from exc


@router.get("/{request_id}/payout-reservation")
async def admin_payout_reservation(
    request_id: ApiLifetimeId,
    db: AsyncSession = Depends(get_db),
    auth: Any = Depends(require_admin),
) -> dict:
    """Recover an existing reservation without granting a new Send authority."""
    admin = _admin_from_context(auth)
    try:
        out = await WithdrawalsService.get_payout_reservation(
            db, withdrawal_id=int(request_id), admin=admin
        )
        return {"ok": True, "result": out}
    except EfhcConflictError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        await db.rollback()
        logger.exception("withdraw payout reservation read failed")
        raise HTTPException(
            status_code=500, detail="WITHDRAW_PAYOUT_RESERVATION_UNAVAILABLE"
        ) from exc


@router.post("/{request_id}/payout-evidence")
async def admin_payout_evidence(
    request_id: ApiLifetimeId,
    payload: dict | None = None,
    db: AsyncSession = Depends(get_db),
    auth: Any = Depends(require_admin_write),
    idempotency_key: str = Depends(
        require_idempotency_key_header_only,
    ),
) -> dict:
    """Сохранить успешный wallet-send как evidence; статус остаётся PENDING."""
    admin = _admin_from_context(auth)
    try:
        req = _withdraw_paid_request(
            payload, idempotency_key=str(idempotency_key)
        )
        out = await WithdrawalsService.record_payout_evidence(
            db, withdrawal_id=int(request_id), req=req, admin=admin
        )
        return {"ok": True, "result": out}
    except EfhcConflictError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        await db.rollback()
        logger.exception("withdraw payout evidence failed")
        raise HTTPException(
            status_code=500, detail="WITHDRAW_PAYOUT_EVIDENCE_UNAVAILABLE"
        ) from exc


@router.post("/{request_id}/mark-paid")
async def admin_mark_paid(
    request_id: ApiLifetimeId,
    payload: dict | None = None,
    db: AsyncSession = Depends(get_db),
    auth: Any = Depends(require_admin_write),
    idempotency_key: str = Depends(
        require_idempotency_key_header_only,
    ),
) -> dict:
    """Явное действие «Оплачено»; отделено от wallet-send evidence."""
    admin = _admin_from_context(auth)
    try:
        req = _withdraw_paid_request(
            payload, idempotency_key=str(idempotency_key)
        )
        out = await WithdrawalsService.mark_withdrawal_paid(
            db, withdrawal_id=int(request_id), req=req, admin=admin
        )
        return {"ok": True, "result": out}
    except EfhcConflictError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        await db.rollback()
        logger.exception("withdraw mark-paid failed")
        raise HTTPException(
            status_code=500, detail="WITHDRAW_MARK_PAID_UNAVAILABLE"
        ) from exc


@router.post("/{request_id}/approve")
async def admin_approve(
    request_id: ApiLifetimeId,
    payload: dict | None = None,
    db: AsyncSession = Depends(get_db),
    auth: Any = Depends(require_admin_write),
    idempotency_key: str = Depends(
        require_idempotency_key_header_only,
    ),
) -> dict:
    """Compatibility endpoint: явное подтверждение «Оплачено» → PAID."""
    admin = _admin_from_context(auth)
    try:
        req = _withdraw_paid_request(
            payload, idempotency_key=str(idempotency_key)
        )
        out = await WithdrawalsService.approve_withdrawal(
            db,
            withdrawal_id=int(request_id),
            req=req,
            admin=admin,
        )
        return {"ok": True, "result": out}
    except EfhcConflictError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        await db.rollback()
        try:
            await AdminLogger.write(
                db,
                actor_global_id=admin.global_id,
                admin_id=admin.id,
                action="WITHDRAW_APPROVE_ATTEMPT_FAIL",
                entity="withdraw_request",
                entity_id=int(request_id),
                details=str(exc),
            )
            await db.commit()
        except Exception:
            await db.rollback()
        logger.exception("withdraw approve failed")
        raise HTTPException(
            status_code=500,
            detail="WITHDRAW_APPROVE_UNAVAILABLE",
        ) from exc


@router.post("/{request_id}/reject")
async def admin_reject(
    request_id: ApiLifetimeId,
    payload: RejectIn,
    db: AsyncSession = Depends(get_db),
    auth: Any = Depends(require_admin_write),
    idempotency_key: str = Depends(
        require_idempotency_key_header_only,
    ),
) -> dict:
    """Отклонить заявку (рефанд делает сервис)."""
    admin = _admin_from_context(auth)
    try:
        out = await WithdrawalsService.reject_withdrawal(
            db,
            withdrawal_id=int(request_id),
            reason=str(payload.reason),
            idempotency_key=str(idempotency_key),
            admin=admin,
            comment_override=payload.comment_override,
            comment_auto_translated=bool(
                payload.comment_auto_translated
            ),
        )
        return {"ok": True, "result": out}
    except EfhcConflictError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        await db.rollback()
        try:
            await AdminLogger.write(
                db,
                actor_global_id=admin.global_id,
                admin_id=admin.id,
                action="WITHDRAW_REJECT_ATTEMPT_FAIL",
                entity="withdraw_request",
                entity_id=int(request_id),
                details=str(exc),
            )
            await db.commit()
        except Exception:
            await db.rollback()
        logger.exception("withdraw reject failed")
        raise HTTPException(
            status_code=500,
            detail="WITHDRAW_REJECT_UNAVAILABLE",
        ) from exc


@router.get(
    "/{request_id}/outcome-preview",
    response_model=WithdrawOutcomePreviewSchema,
)
async def admin_withdraw_outcome_preview(
    request_id: ApiLifetimeId,
    mode: str = Query(default="auto"),
    db: AsyncSession = Depends(get_db),
    _auth: Any = Depends(require_admin),
) -> WithdrawOutcomePreviewSchema:
    preview = await get_admin_withdraw_outcome_preview(
        db,
        request_id=int(request_id),
        mode=str(mode or "auto"),
    )
    bundle = preview.bundle
    promo = bundle.promo
    return WithdrawOutcomePreviewSchema(
        request_id=int(preview.request_id),
        withdrawal_status=str(preview.withdrawal_status),
        preview_mode=str(preview.preview_mode),
        bundle=WithdrawOutcomeBundleSchema(
            request_id=int(bundle.request_id),
            global_id=f"{int(bundle.global_id):010d}",
            outcome_kind=str(bundle.outcome_kind),
            locale=str(bundle.locale),
            comment=OutcomeCommentSchema(
                text=str(bundle.comment.text),
                template_key=bundle.comment.template_key,
                source=str(bundle.comment.source),
                locale=str(bundle.comment.locale),
                manual_override_used=bool(
                    bundle.comment.manual_override_used
                ),
                auto_translated=bool(bundle.comment.auto_translated),
            ),
            promo=(
                OutcomePromoSchema(
                    enabled=bool(promo.enabled),
                    key=promo.key,
                    title=promo.title,
                    body=promo.body,
                    cta_label=promo.cta_label,
                    cta_url=promo.cta_url,
                    source=promo.source,
                )
                if promo is not None
                else None
            ),
            top_zone_enabled=bool(bundle.top_zone_enabled),
            metadata=dict(bundle.metadata or {}),
        ),
    )


__all__ = ["router"]
