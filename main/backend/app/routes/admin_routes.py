# backend/app/routes/admin_routes.py
# ======================================================================
# Назначение:
# Админ-API EFHC Bot: корректировки балансов «банк↔пользователь»,
# ручная реконсиляция входящих TON, сводные отчёты, тех.диагностика.
#
# Канон:
# - Любые денежные операции идут только через transactions_service.
# - Денежные POST требуют Idempotency-Key (строгая идемпотентность).
# - Пользователи не могут уходить в минус (правило сервисов/БД).
# - Банк может быть в минусе (фиксируется в логах).
# - Доступ: require_admin.
#
# Запреты:
# - Никаких прямых SQL для денег из роутов; только сервисные функции.
# - Никаких P2P user→user; корректировки только «пользователь↔банк».
# ======================================================================

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast

from app.core.logging_core import get_logger
from app.deps import (
    AuthContext,
    d8,
    get_db,
    require_admin,
    require_admin_write,
    require_idempotency_key_header_only,
)
from app.identity.api_contract import PydanticGlobalId
from app.models.user_models import User
from app.schemas.id_schemas import ApiLifetimeId
from app.services.admin.admin_bank_service import (
    BankService,
    BankUserTransferRequest,
    MintBurnRequest,
)
from app.services.admin.admin_logging import AdminLogger
from app.services.admin.admin_rbac import RBAC
from app.services.bank_metrics_snapshot_service import (
    refresh_bank_metrics_snapshot,
    snapshot_to_facts,
)
from app.services.efhc_deposits_service import (
    DepositError,
    process_efhc_deposit,
)
from app.services.reconcile_diagnostics_service import (
    summarize_reconcile_diagnostics,
)
from app.services.transactions_service import (
    IdempotencyPayloadConflictError,
)
from app.services.watcher_service import (
    process_incoming_payments,
    reconcile_last_hours,
    reprocess_single_tx,
)
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


class AdminTransferIn(BaseModel):
    global_id: PydanticGlobalId = Field(
        ...,
        description=(
            "Канонический global_id пользователя: десять ASCII-цифр"
        ),
    )
    direction: str = Field(
        ...,
        description="Направление перевода (credit|debit)",
        pattern=r"^(credit|debit)$",
    )
    balance: str = Field(
        "main",
        description="Баланс (main|bonus)",
        pattern=r"^(main|bonus)$",
    )
    amount: Decimal = Field(..., description="Сумма EFHC (>= 0)")
    reason: str | None = Field(
        None,
        description="Причина/комментарий (логируется)",
        max_length=255,
    )


class AdminAccessOut(BaseModel):
    """Server-side подтверждение доступа к админ-панели."""

    global_id: PydanticGlobalId
    role: str
    access_method: str
    access_method_label: str


@router.get("/access", response_model=AdminAccessOut)
async def admin_access(
    auth: AuthContext = Depends(require_admin),
) -> AdminAccessOut:
    """Вернуть доступ после проверки Admin list или подтверждённого Admin NFT."""

    via_nft = str(getattr(auth, "auth_source", "")) == "admin_nft_id"
    return AdminAccessOut(
        global_id=f"{int(auth.global_id):010d}",
        role=str(auth.role),
        access_method="admin_nft" if via_nft else "assigned_admin",
        access_method_label=(
            "Доступ подтверждён Admin NFT"
            if via_nft
            else "Доступ назначен системой"
        ),
    )


class AdminTransferOut(BaseModel):
    ok: bool
    global_id: str
    balance: str
    direction: str
    amount: str
    bank_balance_after: str | None = None
    user__main__after: str | None = None
    user_bonus_after: str | None = None
    idempotency_key: str
    reused: bool = False


class TonReconcileIn(BaseModel):
    """Режимы реконсиляции входящих TON."""

    since_utime: int | None = None
    last_hours: int | None = 6
    limit: int = 1000


class TonReconcileOut(BaseModel):
    ok: bool
    processed: int
    parsed: int
    credited: int
    duplicates: int
    errors: int
    diagnostics: dict[str, int] = Field(default_factory=dict)
    note: str | None = None


class ReportsOverviewOut(BaseModel):
    ok: bool
    ts: datetime
    counters: dict[str, int]
    facts: dict[str, str] = Field(default_factory=dict)
    notes: str | None = None


class AdminEfhcDepositIn(BaseModel):
    tx_hash: str = Field(..., min_length=1, max_length=255)


class AdminEfhcDepositOut(BaseModel):
    ok: bool
    detail: str | None = None
    error: str | None = None
    tx_hash: str
    amount: str
    global_id: str | None = None
    main_balance_after: str | None = None
    bonus_balance_after: str | None = None
    release_mode: str = "release_core_eligible"
    automation_mode: str = "operator_exception_path"
    release_gate_note: str = (
        "Основной путь депозитов автоматический. Ручная обработка "
        "предназначена только для подтверждённых исключительных случаев."
    )


class AdminEfhcDepositsRuntimeOut(BaseModel):
    ok: bool
    release_mode: str = "release_core_eligible"
    automation_mode: str = "automated_with_operator_fallback"
    release_gate_note: str = (
        "Основной путь депозитов автоматический; администратор вмешивается "
        "только при ошибке, спорной операции или восстановлении."
    )
    primary_path: str = "watcher_automation"
    fallback_path: str = "operator_exception_and_replay"
    pending_manual_count: int = 0
    error_retry_count: int = 0
    error_user_count: int = 0
    auto_credited_count: int = 0
    pending_intents_count: int = 0
    total_count: int = 0
    status_counters: dict[str, int] = Field(default_factory=dict)
    error_total: int = 0
    retry_waiting_count: int = 0
    unmatched_count: int = 0
    last_reconcile_success_at: str | None = None
    last_watcher_at: str | None = None
    last_watcher_status: str | None = None


class AdminEfhcDepositReplayOut(BaseModel):
    ok: bool
    tx_hash: str
    replay_status: str
    release_mode: str = "release_core_eligible"
    automation_mode: str = "automated_with_operator_fallback"
    release_gate_note: str = (
        "Повторная обработка использует тот же автоматический путь, "
        "что и обычная входящая операция."
    )


class AdminTonInboxItem(BaseModel):
    id: ApiLifetimeId
    tx_hash: str
    amount: str
    memo: str | None = None
    from_address: str | None = None
    to_address: str | None = None
    status: str
    resolved_global_id: str | None = None
    parsed_tg_id: int | None = None
    parsed_sku: str | None = None
    retries_count: int = 0
    next_retry_at: datetime | None = None
    processed_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime


class AdminTonInboxOut(BaseModel):
    ok: bool
    items: list[AdminTonInboxItem] = Field(default_factory=list)
    next_cursor_id: ApiLifetimeId | None = None


class AdminUnmatchedIncomingItem(BaseModel):
    id: ApiLifetimeId
    tx_hash: str
    asset: str
    amount: str
    from_address: str | None = None
    to_address: str | None = None
    memo: str | None = None
    reason: str | None = None
    resolved_global_id: str | None = None
    created_at: datetime


class AdminUnmatchedIncomingOut(BaseModel):
    ok: bool
    items: list[AdminUnmatchedIncomingItem] = Field(default_factory=list)
    next_cursor_id: ApiLifetimeId | None = None


@router.post(
    "/transfer",
    response_model=AdminTransferOut,
    summary=(
        "Корректировка «банк↔пользователь» "
        "(только через банк, read-through идемпотентность)"
    ),
)
async def admin_transfer(
    payload: AdminTransferIn,
    db: AsyncSession = Depends(get_db),
    _auth: AuthContext = Depends(require_admin_write),
    idempotency_key: str = Depends(require_idempotency_key_header_only),
) -> AdminTransferOut:
    if payload.amount is None or Decimal(payload.amount) <= Decimal("0"):
        raise HTTPException(
            status_code=400,
            detail="Сумма должна быть больше нуля.",
        )

    global_id = int(payload.global_id.value)
    amount_q8 = d8(payload.amount)

    try:
        admin = RBAC.admin_from_auth_context(_auth)
        req = BankUserTransferRequest(
            global_id=f"{global_id:010d}",
            amount=amount_q8,
            direction=payload.direction,
            balance_type=(
                "REGULAR" if payload.balance == "main" else "BONUS"
            ),
            reason=payload.reason or "Ручная корректировка администратора",
            idempotency_key=idempotency_key,
        )
        transfer_result = await BankService.manual_bank_user_transfer(
            db,
            req=req,
            admin=admin,
        )
    except IdempotencyPayloadConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail="IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD",
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("admin_transfer failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Не удалось выполнить корректировку.",
        ) from exc

    try:
        row = await db.execute(
            select(
                User.global_id,
                User.main_balance,
                User.bonus_balance,
            ).where(User.global_id == global_id)
        )
        owner_row = row.fetchone()
        if owner_row:
            resolved_global_id = int(owner_row[0])
            mb, bb = owner_row[1], owner_row[2]
        else:
            resolved_global_id = global_id
            mb, bb = Decimal("0"), Decimal("0")
    except Exception:
        resolved_global_id = global_id
        mb, bb = Decimal("0"), Decimal("0")

    bank_balance = await BankService.get_bank_balance(db)

    return AdminTransferOut(
        ok=True,
        global_id=f"{int(resolved_global_id):010d}",
        balance=payload.balance,
        direction=payload.direction,
        amount=str(d8(payload.amount)),
        bank_balance_after=str(bank_balance.balance),
        user__main__after=str(d8(mb)),
        user_bonus_after=str(d8(bb)),
        idempotency_key=idempotency_key,
        reused=bool(transfer_result.get("reused", False)),
    )


@router.post(
    "/bank/transfers/{transfer_log_id}/rollback",
    summary=(
        "Компенсирующий rollback исходной Admin Bank operation "
        "(Idempotency-Key обязателен)"
    ),
)
async def admin_bank_rollback(
    transfer_log_id: ApiLifetimeId,
    db: AsyncSession = Depends(get_db),
    _auth: AuthContext = Depends(require_admin_write),
    idempotency_key: str = Depends(require_idempotency_key_header_only),
) -> dict[str, Any]:
    """Выполнить не более одного reversal по исходному ledger id."""
    admin = RBAC.admin_from_auth_context(_auth)
    try:
        result = await BankService.rollback_bank_user_tx(
            db,
            transfer_log_id=int(transfer_log_id),
            idempotency_key=idempotency_key,
            admin=admin,
        )
        return cast(dict[str, Any], result)
    except IdempotencyPayloadConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail="IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD",
        ) from exc
    except ValueError as exc:
        marker = str(exc)
        if marker == "ROLLBACK_ORIGINAL_NOT_FOUND":
            raise HTTPException(status_code=404, detail=marker) from exc
        known_conflicts = {
            "ROLLBACK_SOURCE_MUST_BE_USER_SIDE_ADMIN_TRANSFER",
            "ROLLBACK_SOURCE_MUST_BE_ORIGINAL_ADMIN_TRANSFER",
            "ROLLBACK_SOURCE_DIRECTION_INVALID",
            "ROLLBACK_SOURCE_BALANCE_TYPE_INVALID",
            "ROLLBACK_BALANCE_TYPE_CONFLICT",
            "IDEMPOTENCY_REQUIRED",
        }
        detail = marker if marker in known_conflicts else "BANK_ROLLBACK_REJECTED"
        raise HTTPException(status_code=409, detail=detail) from exc


@router.get(
    "/bank/balance",
    summary="Баланс банка BANK_EFHC (efhc_core.bank_balance)",
)
async def admin_bank_balance(
    db: AsyncSession = Depends(get_db),
    _auth: AuthContext = Depends(require_admin),
) -> dict[str, Any]:
    bal = await BankService.get_bank_balance(db)
    return {
        "bank_name": "BANK_EFHC",
        "efhc_main": str(bal.balance),
    }


@router.post(
    "/bank/mint",
    summary="Эмиссия EFHC в банк (Idempotency-Key обязателен)",
)
async def admin_bank_mint(
    payload: MintBurnRequest,
    db: AsyncSession = Depends(get_db),
    _auth: AuthContext = Depends(require_admin_write),
    idempotency_key: str = Depends(require_idempotency_key_header_only),
) -> dict[str, Any]:
    payload.idempotency_key = idempotency_key
    admin = RBAC.admin_from_auth_context(_auth)
    try:
        res = await BankService.mint_efhc(
            db,
            req=payload,
            admin=admin,
        )
    except IdempotencyPayloadConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail="IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD",
        ) from exc
    return {
        "ok": True,
        "bank_balance_after": str(res.get("current_balance")),
        "idempotency_key": idempotency_key,
        "reused": bool(res.get("reused", False)),
    }


@router.post(
    "/bank/burn",
    summary="Сжигание EFHC в банке (Idempotency-Key обязателен)",
)
async def admin_bank_burn(
    payload: MintBurnRequest,
    db: AsyncSession = Depends(get_db),
    _auth: AuthContext = Depends(require_admin_write),
    idempotency_key: str = Depends(require_idempotency_key_header_only),
) -> dict[str, Any]:
    payload.idempotency_key = idempotency_key
    admin = RBAC.admin_from_auth_context(_auth)
    try:
        res = await BankService.burn_efhc(
            db,
            req=payload,
            admin=admin,
        )
    except IdempotencyPayloadConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail="IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD",
        ) from exc
    return {
        "ok": True,
        "bank_balance_after": str(res.get("current_balance")),
        "idempotency_key": idempotency_key,
        "reused": bool(res.get("reused", False)),
    }


@router.post(
    "/ton/reconcile",
    response_model=TonReconcileOut,
    summary=(
        "Повторная проверка входящих TON за выбранный период"
    ),
)
async def ton_reconcile(
    payload: TonReconcileIn,
    db: AsyncSession = Depends(get_db),
    _auth: AuthContext = Depends(require_admin_write),
) -> TonReconcileOut:
    if payload.since_utime is None and payload.last_hours is None:
        raise HTTPException(
            status_code=400,
            detail="Укажите since_utime или last_hours.",
        )

    try:
        if payload.since_utime is not None:
            stats = await process_incoming_payments(
                db=db,
                limit=int(payload.limit),
                since_utime=int(payload.since_utime),
            )
        else:
            if payload.last_hours is None:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "last_hours is required when "
                        "since_utime is null."
                    ),
                )
            stats = await reconcile_last_hours(
                db=db,
                hours=int(payload.last_hours),
                limit=int(payload.limit),
            )
    except Exception as exc:
        logger.exception("ton_reconcile failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Не удалось повторно проверить входящие TON за выбранный период.",
        ) from exc

    diagnostics = await summarize_reconcile_diagnostics(
        db,
        hours=int(payload.last_hours or 6),
    )
    processed = sum(int(value or 0) for value in stats.values())
    credited = int(stats.get("credited", 0) or 0) + int(
        stats.get("paid_auto", 0) or 0
    )
    errors = sum(
        int(value or 0)
        for key, value in stats.items()
        if str(key).startswith("error")
    )
    parsed = sum(
        int(stats.get(key, 0) or 0)
        for key in (
            "parsed",
            "parsed_pending_mapping",
            "pending_manual",
            "paid_pending_manual",
        )
    )
    note = (
        f"Проверено не более {int(payload.limit)} входящих операций "
        "за выбранный период. Повторная проверка безопасна: одна и та же "
        "операция не должна начисляться повторно."
    )
    return TonReconcileOut(
        ok=True,
        processed=processed,
        parsed=parsed,
        credited=credited,
        duplicates=0,
        errors=errors,
        diagnostics=diagnostics,
        note=note,
    )


@router.post(
    "/efhc-deposits/process",
    response_model=AdminEfhcDepositOut,
    summary="Аварийная обработка уже подтверждённой входящей операции EFHC",
)
async def admin_process_efhc_deposit(
    payload: AdminEfhcDepositIn,
    db: AsyncSession = Depends(get_db),
    _auth: AuthContext = Depends(require_admin_write),
) -> AdminEfhcDepositOut:
    admin = RBAC.admin_from_auth_context(_auth)
    try:
        result = await process_efhc_deposit(
            db=db,
            tx_hash=payload.tx_hash,
        )
        result_global_id = result.get("global_id")
        await AdminLogger.write(
            db,
            actor_global_id=admin.global_id,
            admin_id=admin.id,
            action="EFHC_DEPOSIT_EMERGENCY_PROCESS",
            entity="ton_inbox",
            entity_id=None,
            details=(
                f"tx_hash = {payload.tx_hash}; "
                f"ok = {bool(result.get('ok', False))}; "
                f"result = {result.get('error') or 'processed'}"
            ),
            required=True,
        )
        await db.commit()

        error = result.get("error")
        if error == "materialized_tx_not_found":
            raise HTTPException(status_code=404, detail=error)
        if error == "settlement_already_claimed":
            raise HTTPException(status_code=409, detail=error)

        return AdminEfhcDepositOut(
            ok=bool(result.get("ok", False)),
            detail=result.get("detail"),
            error=error,
            tx_hash=str(result.get("tx_hash", payload.tx_hash)),
            amount=str(result.get("amount", "0")),
            global_id=(
                str(result_global_id)
                if result_global_id is not None
                else None
            ),
            main_balance_after=result.get("new__main__balance"),
            bonus_balance_after=result.get("new_bonus_balance"),
        )
    except HTTPException:
        raise
    except DepositError as exc:
        await db.rollback()
        try:
            await AdminLogger.write(
                db,
                actor_global_id=admin.global_id,
                admin_id=admin.id,
                action="EFHC_DEPOSIT_EMERGENCY_REJECTED",
                entity="ton_inbox",
                entity_id=None,
                details=(
                    f"tx_hash = {payload.tx_hash}; "
                    f"error = {type(exc).__name__}"
                ),
                required=True,
            )
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        raise HTTPException(
            status_code=400,
            detail="Подтверждённую входящую операцию обработать нельзя.",
        ) from exc
    except Exception as exc:
        await db.rollback()
        logger.exception("admin_process_efhc_deposit failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Не удалось обработать внешний депозит EFHC.",
        ) from exc


@router.get(
    "/efhc-deposits/runtime-summary",
    response_model=AdminEfhcDepositsRuntimeOut,
    summary="Общее состояние автоматической обработки входящих платежей",
)
async def admin_efhc_deposits_runtime_summary(
    db: AsyncSession = Depends(get_db),
    _auth: AuthContext = Depends(require_admin),
) -> AdminEfhcDepositsRuntimeOut:
    q_logs = text(
        """
        SELECT
          COALESCE(COUNT(*), 0) AS total_count,
          COALESCE(SUM(CASE WHEN status = 'pending_manual'
            THEN 1 ELSE 0 END), 0) AS pending_manual_count,
          COALESCE(SUM(CASE WHEN status = 'error_retry'
            THEN 1 ELSE 0 END), 0) AS error_retry_count,
          COALESCE(SUM(CASE WHEN status = 'error_user_not_found'
            THEN 1 ELSE 0 END), 0) AS error_user_count,
          COALESCE(SUM(CASE WHEN status = 'credited'
            THEN 1 ELSE 0 END), 0) AS auto_credited_count,
          COALESCE(SUM(CASE WHEN status LIKE 'error_%'
            THEN 1 ELSE 0 END), 0) AS error_total,
          COALESCE(SUM(CASE WHEN status NOT IN (
              'credited', 'paid_auto', 'paid_pending_manual', 'pending_manual'
            ) AND (next_retry_at IS NULL OR next_retry_at <= NOW())
            THEN 1 ELSE 0 END), 0) AS retry_waiting_count
        FROM efhc_core.ton_inbox_logs
        """
    )
    q_statuses = text(
        """
        SELECT status, COUNT(*) AS cnt
        FROM efhc_core.ton_inbox_logs
        GROUP BY status
        ORDER BY status
        """
    )
    q_intents = text(
        """
        SELECT COALESCE(COUNT(*), 0) AS pending_intents_count
        FROM efhc_core.payment_intents
        WHERE purpose = 'deposit_efhc'
          AND status = 'PENDING'
        """
    )
    q_unmatched = text(
        "SELECT COALESCE(COUNT(*), 0) AS cnt "
        "FROM efhc_core.unmatched_incoming"
    )
    q_reconcile = text(
        "SELECT value FROM efhc_core.app_settings "
        "WHERE key = 'scheduler.ton_reconcile_last_success_at' LIMIT 1"
    )
    q_watcher = text(
        "SELECT status, executed_at FROM efhc_core.scheduler_task_log "
        "WHERE task_name = 'check_ton_inbox' "
        "ORDER BY executed_at DESC LIMIT 1"
    )

    log_row: Mapping[str, Any] = dict(
        (await db.execute(q_logs)).mappings().first() or {}
    )
    intent_row: Mapping[str, Any] = dict(
        (await db.execute(q_intents)).mappings().first() or {}
    )
    status_rows = (await db.execute(q_statuses)).mappings().all()
    status_counters = {
        str(row.get("status") or "unknown"): int(row.get("cnt", 0) or 0)
        for row in status_rows
    }
    unmatched_count = int(
        (await db.execute(q_unmatched)).scalar_one_or_none() or 0
    )
    reconcile_value = (await db.execute(q_reconcile)).scalar_one_or_none()
    watcher_row = (await db.execute(q_watcher)).mappings().first()

    return AdminEfhcDepositsRuntimeOut(
        ok=True,
        pending_manual_count=int(log_row.get("pending_manual_count", 0) or 0),
        error_retry_count=int(log_row.get("error_retry_count", 0) or 0),
        error_user_count=int(log_row.get("error_user_count", 0) or 0),
        auto_credited_count=int(log_row.get("auto_credited_count", 0) or 0),
        pending_intents_count=int(
            intent_row.get("pending_intents_count", 0) or 0
        ),
        total_count=int(log_row.get("total_count", 0) or 0),
        status_counters=status_counters,
        error_total=int(log_row.get("error_total", 0) or 0),
        retry_waiting_count=int(log_row.get("retry_waiting_count", 0) or 0),
        unmatched_count=unmatched_count,
        last_reconcile_success_at=(
            str(reconcile_value) if reconcile_value is not None else None
        ),
        last_watcher_at=(
            str(watcher_row.get("executed_at")) if watcher_row else None
        ),
        last_watcher_status=(
            str(watcher_row.get("status")) if watcher_row else None
        ),
    )


def _admin_global_id_filter(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
    normalized = value.strip()
    if (
        len(normalized) != 10
        or not normalized.isascii()
        or not normalized.isdigit()
        or normalized == "0000000000"
    ):
        raise HTTPException(
            status_code=422,
            detail="ID пользователя должен состоять ровно из 10 цифр.",
        )
    return int(normalized)


@router.get(
    "/efhc-deposits/inbox",
    response_model=AdminTonInboxOut,
    summary="Список входящих TON-операций для контроля и восстановления",
)
async def admin_efhc_deposits_inbox(
    status: str | None = None,
    q: str | None = None,
    global_id: str | None = None,
    cursor_id: ApiLifetimeId | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _auth: AuthContext = Depends(require_admin),
) -> AdminTonInboxOut:
    safe_limit = max(1, min(int(limit), 100))
    gid = _admin_global_id_filter(global_id)
    rows = (await db.execute(
        text(
            """
            SELECT id, tx_hash, amount, memo, from_address, to_address,
                   status, resolved_global_id, parsed_tg_id, parsed_sku,
                   retries_count, next_retry_at, processed_at, last_error,
                   created_at, updated_at
              FROM efhc_core.ton_inbox_logs
             WHERE (CAST(:status AS TEXT) IS NULL OR status = :status)
               AND (CAST(:gid AS BIGINT) IS NULL OR resolved_global_id = :gid)
               AND (CAST(:cursor_id AS BIGINT) IS NULL OR id < :cursor_id)
               AND (
                 CAST(:q AS TEXT) IS NULL OR tx_hash ILIKE ('%' || :q || '%')
                 OR COALESCE(memo, '') ILIKE ('%' || :q || '%')
                 OR COALESCE(from_address, '') ILIKE ('%' || :q || '%')
                 OR COALESCE(to_address, '') ILIKE ('%' || :q || '%')
               )
             ORDER BY id DESC
             LIMIT :lim
            """
        ),
        {
            "status": status.strip() if status and status.strip() else None,
            "gid": gid,
            "cursor_id": cursor_id,
            "q": q.strip() if q and q.strip() else None,
            "lim": safe_limit + 1,
        },
    )).mappings().all()
    has_more = len(rows) > safe_limit
    rows = rows[:safe_limit]
    items = [
        AdminTonInboxItem(
            id=int(row["id"]),
            tx_hash=str(row["tx_hash"]),
            amount=str(row["amount"]),
            memo=row.get("memo"),
            from_address=row.get("from_address"),
            to_address=row.get("to_address"),
            status=str(row.get("status") or "received"),
            resolved_global_id=(
                f"{int(row['resolved_global_id']):010d}"
                if row.get("resolved_global_id") is not None
                else None
            ),
            parsed_tg_id=(
                int(row["parsed_tg_id"])
                if row.get("parsed_tg_id") is not None
                else None
            ),
            parsed_sku=row.get("parsed_sku"),
            retries_count=int(row.get("retries_count", 0) or 0),
            next_retry_at=row.get("next_retry_at"),
            processed_at=row.get("processed_at"),
            last_error=row.get("last_error"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]
    return AdminTonInboxOut(
        ok=True,
        items=items,
        next_cursor_id=(items[-1].id if has_more and items else None),
    )


@router.get(
    "/efhc-deposits/unmatched",
    response_model=AdminUnmatchedIncomingOut,
    summary="Входящие операции, которые не удалось автоматически сопоставить",
)
async def admin_efhc_deposits_unmatched(
    q: str | None = None,
    global_id: str | None = None,
    cursor_id: ApiLifetimeId | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _auth: AuthContext = Depends(require_admin),
) -> AdminUnmatchedIncomingOut:
    safe_limit = max(1, min(int(limit), 100))
    gid = _admin_global_id_filter(global_id)
    rows = (await db.execute(
        text(
            """
            SELECT id, tx_hash, asset, amount_asset_d8, from_address,
                   to_address, memo, reason, resolved_global_id, created_at
              FROM efhc_core.unmatched_incoming
             WHERE (CAST(:gid AS BIGINT) IS NULL OR resolved_global_id = :gid)
               AND (CAST(:cursor_id AS BIGINT) IS NULL OR id < :cursor_id)
               AND (
                 CAST(:q AS TEXT) IS NULL OR tx_hash ILIKE ('%' || :q || '%')
                 OR COALESCE(memo, '') ILIKE ('%' || :q || '%')
                 OR COALESCE(reason, '') ILIKE ('%' || :q || '%')
               )
             ORDER BY id DESC
             LIMIT :lim
            """
        ),
        {
            "gid": gid,
            "cursor_id": cursor_id,
            "q": q.strip() if q and q.strip() else None,
            "lim": safe_limit + 1,
        },
    )).mappings().all()
    has_more = len(rows) > safe_limit
    rows = rows[:safe_limit]
    items = [
        AdminUnmatchedIncomingItem(
            id=int(row["id"]),
            tx_hash=str(row["tx_hash"]),
            asset=str(row.get("asset") or "TON"),
            amount=str(row.get("amount_asset_d8") or "0"),
            from_address=row.get("from_address"),
            to_address=row.get("to_address"),
            memo=row.get("memo"),
            reason=row.get("reason"),
            resolved_global_id=(
                f"{int(row['resolved_global_id']):010d}"
                if row.get("resolved_global_id") is not None
                else None
            ),
            created_at=row["created_at"],
        )
        for row in rows
    ]
    return AdminUnmatchedIncomingOut(
        ok=True,
        items=items,
        next_cursor_id=(items[-1].id if has_more and items else None),
    )


@router.post(
    "/efhc-deposits/reprocess/{tx_hash}",
    response_model=AdminEfhcDepositReplayOut,
    summary="Повторная безопасная обработка выбранной входящей операции",
)
async def admin_reprocess_efhc_deposit_tx(
    tx_hash: str,
    db: AsyncSession = Depends(get_db),
    _auth: AuthContext = Depends(require_admin_write),
) -> AdminEfhcDepositReplayOut:
    if not str(tx_hash).strip():
        raise HTTPException(
            status_code=422,
            detail="Укажите хэш входящей транзакции.",
        )
    try:
        replay_status = await reprocess_single_tx(
            db,
            str(tx_hash).strip(),
        )
        if replay_status == "not_found":
            raise HTTPException(
                status_code=404,
                detail="Такая входящая транзакция не найдена в журнале.",
            )
        return AdminEfhcDepositReplayOut(
            ok=True,
            tx_hash=str(tx_hash).strip(),
            replay_status=str(replay_status),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "admin_reprocess_efhc_deposit_tx failed: %s",
            exc,
        )
        raise HTTPException(
            status_code=500,
            detail="Не удалось повторно обработать выбранную операцию.",
        ) from exc


@router.get(
    "/reports/overview",
    response_model=ReportsOverviewOut,
    summary="Быстрый обзор ключевых счётчиков",
)
async def reports_overview(
    db: AsyncSession = Depends(get_db),
    _auth: AuthContext = Depends(require_admin),
) -> ReportsOverviewOut:
    counters: dict[str, int] = {
        "ton_inbox_total": 0,
        "ton_inbox_errors": 0,
        "efhc_transfers_total": 0,
        "efhc_transfers_deficit": 0,
        "users_total": 0,
        "users_active": 0,
        "users_inactive": 0,
    }
    facts: dict[str, str] = {
        "panels_total_bought": "0",
        "panels_total_active": "0",
        "panels_total_archived": "0",
        "panels_total_paid_efhc": "0.00000000",
        "panels_total_paid__main__efhc": "0.00000000",
        "panels_total_paid_bonus_efhc": "0.00000000",
        "users_total_generated_kwh": "0.00000000",
        "users_total_exchanged_kwh": "0.00000000",
        "users_total__main__efhc": "0.00000000",
        "users_total_bonus_efhc": "0.00000000",
        "users_total_efhc": "0.00000000",
        "referrals_total_bonus_paid_efhc": "0.00000000",
        "withdraw_bonus_total_efhc": "0.00000000",
        "bank_total_efhc": "0.00000000",
        "bank_users_balance_diff_efhc": "0.00000000",
        "bank_users_balance_match": "OK",
        "bank_metrics_ready": "0",
    }
    notes: str | None = None

    try:
        # work pass audit repair: keep this admin report as a
        # bounded read-only snapshot. One SQL round-trip is easier
        # to reason about than 15+ sequential raw queries.
        await db.execute(text("SET LOCAL statement_timeout = '500ms'"))
        overview_q = text(
            """
            with
            ton as (
              select
                count(*)::bigint as total,
                count(*) filter (
                  where status like 'error_%'
                )::bigint as errors
              from efhc_core.ton_inbox_logs
            ),
            transfers as (
              select
                count(*)::bigint as total,
                count(*) filter (
                  where meta like '%processed_with_deficit%'
                )::bigint as deficit
              from efhc_core.efhc_transfers_log
            ),
            users_count as (
              select
                count(*)::bigint as total_users,
                coalesce(
                  sum(case when is_active then 1 else 0 end),
                  0
                )::bigint as active_users,
                coalesce(
                  sum(case when is_active then 0 else 1 end),
                  0
                )::bigint as inactive_users
              from efhc_core.users
            ),
            panels as (
              select
                count(*)::bigint as total_cnt,
                coalesce(
                  sum(case when is_active then 1 else 0 end),
                  0
                )::bigint as active_cnt,
                coalesce(
                  sum(case when is_active then 0 else 1 end),
                  0
                )::bigint as archived_cnt
              from efhc_core.panels
             where coalesce(meta ->> 'protectively_voided', 'false') <> 'true'
            ),
            purchase_debits as (
              select
                coalesce(sum(amount), 0)::numeric as total_paid,
                coalesce(
                  sum(amount) filter (where balance_type = 'main'),
                  0
                )::numeric as total_paid_main,
                coalesce(
                  sum(amount) filter (where balance_type = 'bonus'),
                  0
                )::numeric as total_paid_bonus
              from efhc_core.efhc_transfers_log
              where reason in (
                'panel_purchase',
                'panel_activation',
                'panel_reactivation'
              )
                and direction = 'debit'
            ),
            protective_voids as (
              select
                coalesce(
                  sum(
                    coalesce((event ->> 'original_payment_bonus')::numeric, 0)
                    + coalesce((event ->> 'original_payment_main')::numeric, 0)
                  ),
                  0
                )::numeric as voided_total,
                coalesce(
                  sum(coalesce((event ->> 'original_payment_main')::numeric, 0)),
                  0
                )::numeric as voided_main,
                coalesce(
                  sum(coalesce((event ->> 'original_payment_bonus')::numeric, 0)),
                  0
                )::numeric as voided_bonus
              from efhc_core.panels p
              cross join lateral jsonb_array_elements(
                case
                  when jsonb_typeof(p.meta -> 'protective_events') = 'array'
                    then p.meta -> 'protective_events'
                  else '[]'::jsonb
                end
              ) as event
              where event ->> 'op' = 'protective_deactivate'
            ),
            purchase as (
              select
                (purchase_debits.total_paid - protective_voids.voided_total)::numeric as total_paid,
                (purchase_debits.total_paid_main - protective_voids.voided_main)::numeric as total_paid_main,
                (purchase_debits.total_paid_bonus - protective_voids.voided_bonus)::numeric as total_paid_bonus
              from purchase_debits
              cross join protective_voids
            ),
            users_totals as (
              select
                coalesce(sum(main_balance), 0)::numeric as total_main,
                coalesce(sum(bonus_balance), 0)::numeric as total_bonus,
                coalesce(
                  sum(total_generated_kwh),
                  0
                )::numeric as total_generated,
                coalesce(
                  sum(exchanged_kwh_total),
                  0
                )::numeric as total_exchanged
              from efhc_core.users
            ),
            bank as (
              select coalesce(balance, 0)::numeric as bank_total
              from efhc_core.bank_balance
              where key = 'EFHC_MAIN'
              limit 1
            ),
            ref_bonus as (
              select
                coalesce(sum(amount), 0)::numeric as total_ref_bonus
              from efhc_core.efhc_transfers_log
              where reason in (
                'referral_active_unit',
                'referral_level_bonus'
              )
            ),
            withdraw_bonus as (
              select
                coalesce(
                  sum(amount),
                  0
                )::numeric as total_withdraw_bonus
              from efhc_core.efhc_transfers_log
              where reason like 'withdraw%'
                and balance_type = 'bonus'
            )
            select
              ton.total as ton_inbox_total,
              ton.errors as ton_inbox_errors,
              transfers.total as efhc_transfers_total,
              transfers.deficit as efhc_transfers_deficit,
              users_count.total_users,
              users_count.active_users,
              users_count.inactive_users,
              panels.total_cnt as panels_total_bought,
              panels.active_cnt as panels_total_active,
              panels.archived_cnt as panels_total_archived,
              purchase.total_paid,
              purchase.total_paid_main,
              purchase.total_paid_bonus,
              users_totals.total_generated,
              users_totals.total_exchanged,
              users_totals.total_main,
              users_totals.total_bonus,
              coalesce(bank.bank_total, 0)::numeric as bank_total,
              ref_bonus.total_ref_bonus,
              withdraw_bonus.total_withdraw_bonus
            from ton
            cross join transfers
            cross join users_count
            cross join panels
            cross join purchase
            cross join users_totals
            cross join ref_bonus
            cross join withdraw_bonus
            left join bank on true
            """
        )
        row = (await db.execute(overview_q)).mappings().first()
        if row:
            counters["ton_inbox_total"] = int(
                row["ton_inbox_total"] or 0
            )
            counters["ton_inbox_errors"] = int(
                row["ton_inbox_errors"] or 0
            )
            counters["efhc_transfers_total"] = int(
                row["efhc_transfers_total"] or 0
            )
            counters["efhc_transfers_deficit"] = int(
                row["efhc_transfers_deficit"] or 0
            )
            counters["users_total"] = int(row["total_users"] or 0)
            counters["users_active"] = int(row["active_users"] or 0)
            counters["users_inactive"] = int(row["inactive_users"] or 0)

            facts["panels_total_bought"] = str(
                int(row["panels_total_bought"] or 0)
            )
            facts["panels_total_active"] = str(
                int(row["panels_total_active"] or 0)
            )
            facts["panels_total_archived"] = str(
                int(row["panels_total_archived"] or 0)
            )
            facts["panels_total_paid_efhc"] = str(
                d8(row["total_paid"] or 0)
            )
            facts["panels_total_paid__main__efhc"] = str(
                d8(row["total_paid_main"] or 0)
            )
            facts["panels_total_paid_bonus_efhc"] = str(
                d8(row["total_paid_bonus"] or 0)
            )
            facts["users_total_generated_kwh"] = str(
                d8(row["total_generated"] or 0)
            )
            facts["users_total_exchanged_kwh"] = str(
                d8(row["total_exchanged"] or 0)
            )
            facts["users_total__main__efhc"] = str(
                d8(row["total_main"] or 0)
            )
            facts["users_total_bonus_efhc"] = str(
                d8(row["total_bonus"] or 0)
            )
            users_total = d8(
                (row["total_main"] or 0) + (row["total_bonus"] or 0)
            )
            facts["users_total_efhc"] = str(users_total)
            bank_total = d8(row["bank_total"] or 0)
            facts["bank_total_efhc"] = str(bank_total)
            facts["referrals_total_bonus_paid_efhc"] = str(
                d8(row["total_ref_bonus"] or 0)
            )
            facts["withdraw_bonus_total_efhc"] = str(
                d8(row["total_withdraw_bonus"] or 0)
            )
            diff_val = d8(bank_total - users_total)
            facts["bank_users_balance_diff_efhc"] = str(diff_val)
            facts["bank_users_balance_match"] = (
                "OK" if diff_val == d8(0) else "BUG"
            )

    except Exception as exc:
        await db.rollback()
        logger.warning("reports_overview partial: %s", exc)
        notes = (
            "Таблицы ещё не инициализированы или "
            "миграции не применены. "
            "Проверьте alembic."
        )

    try:
        bank_metrics_snapshot = await refresh_bank_metrics_snapshot(db)
        facts.update(snapshot_to_facts(bank_metrics_snapshot))
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.warning("reports_overview bank metrics snapshot partial: %s", exc)
        suffix = (
            "bank_metrics_snapshot не обновлён; примените "
            "URGENT_BANK_METRICS_SNAPSHOT.sql для существующей базы."
        )
        notes = f"{notes} {suffix}".strip() if notes else suffix

    return ReportsOverviewOut(
        ok=True,
        ts=datetime.now(UTC),
        counters=counters,
        facts=facts,
        notes=notes,
    )
