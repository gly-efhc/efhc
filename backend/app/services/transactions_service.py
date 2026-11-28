# backend/app/services/transactions_service.py
# =====================================================================
# EFHC Bot — Банковский сервис
# (READ-THROUGH идемпотентность)
# ---------------------------------------------------------------------
# ЕДИНСТВЕННАЯ точка входа
# для денежных движений EFHC.
# Канон (функции):
# • credit_user_from_bank(...)        — кредит на MAIN
# • credit_user_bonus_from_bank(...)  — кредит на BONUS
# • debit_user_to_bank(...)           — дебет с MAIN
# • debit_user_bonus_to_bank(...)     — дебет с BONUS
# • exchange_kwh_to_efhc(...) — кредит EFHC
#   1:1 за энергию
# ---------------------------------------------------------------------
# Правила:
# • Пользователь не может уйти в минус
#   (main/bonus).
# • Банк может уйти в минус
#   операции не блокируются.
# • Операция идемпотентна по idempotency_key
#   (UNIQUE в логе).
# • Decimal(30,8), округление вниз — deps.d8().
# • Зеркальный лог Банка: mirror:<idempotency_key>.
# • Никаких P2P
#   только «пользователь ↔ банк».
# =====================================================================

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, cast

from app.core.config_core import get_settings
from app.core.logging_core import get_logger
from app.deps import d8
from app.identity.financial_write_owner import (
    FinancialWriteOwner,
    resolve_and_lock_financial_write_owner,
)
from app.standards.finance_rules import split_bonus_then_main
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# IDEMPOTENCY_KEY_REUSED_FOR_DIFFERENT_BANK_OPERATION

logger = get_logger(__name__)


# ---------------------------------------------------------------------
# Транзакционная граница принадлежит сервису
# ---------------------------------------------------------------------
# HEAL-0018: у денежного перехода одна явная граница транзакции.
# Старый скрытый begin_nested() маскировал уже открытую Session
# и мог оставить денежные записи внутри внешнего autobegin.
# Этот helper выполняет commit или rollback одной корневой
# транзакции вызова денежного сервиса.
#
# Правило вызывающего слоя:
# - routes и wrappers не оборачивают эти сервисы своей записью;
# - read-only preflight может открыть autobegin, но окончательная
#   граница commit/rollback всё равно принадлежит сервису.
@contextlib.asynccontextmanager
async def _tx_context(db: AsyncSession):
    if getattr(db, "in_transaction", None) and db.in_transaction():
        try:
            yield
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        return

    async with db.begin():
        yield


settings = get_settings()
SCHEMA = getattr(settings, "DB_SCHEMA_CORE", "efhc_core")


async def _safe_rollback(db: AsyncSession, ctx: str) -> None:
    try:
        await db.rollback()
    except Exception as exc:
        logger.warning("DB rollback failed (%s): %s", ctx, exc)


async def _rollback_started_exchange_transaction(
    db: AsyncSession,
    *,
    ctx: str,
) -> None:
    """Close read-only autobegin before exchange owns money writes.

    FIND-005 repair: exchange helpers may be called directly
    after a preflight SELECT opened an implicit session transaction.
    They must not commit a caller/preflight transaction and must acquire
    their idempotency proof after the user row lock.
    """
    if getattr(db, "in_transaction", None) and db.in_transaction():
        await _safe_rollback(db, ctx)


# Каноническая системная сущность центрального банка.
# Банк не является пользователем и не имеет global_id/tg_id.
BANK_SYSTEM_ENTITY = "BANK_EFHC"

# ---------------------------------------------------------------------
# Системный объект bank_balance (вариант A).
# Истина баланса банка хранится в efhc_core.bank_balance.
# В банке есть ТОЛЬКО EFHC main.
# BANK_EFHC хранится как system_entity банковской стороны проводки.
# У банковской строки global_id=NULL и tg_id=NULL.
KEY_BANK_MAIN = "EFHC_MAIN"

_BANK_GET_SQL = text(
    "SELECT key, balance FROM "
    "efhc_core.bank_balance "
    "WHERE key = :k "
    "FOR UPDATE"
)

_BANK_UPD_SQL = text(
    "UPDATE "
    "efhc_core.bank_balance "
    "SET balance = :bal, "
    "updated_at = timezone('utc', now()) "
    "WHERE key = :key"
)

_BANK_INS_SQL = text(
    "INSERT INTO "
    "efhc_core.bank_balance (key, balance) "
    "VALUES (:key, :bal) "
    "ON CONFLICT (key) DO NOTHING"
)


async def _ensure_bank_locked(
    db: AsyncSession,
    *,
    initial_balance: Decimal | str = Decimal("0"),
) -> tuple[Decimal, Decimal]:
    """Блокирует и возвращает баланс банка (main, bonus=0)."""
    await db.execute(
        _BANK_INS_SQL,
        {"key": KEY_BANK_MAIN, "bal": str(d8(initial_balance))},
    )
    res = await db.execute(
        _BANK_GET_SQL,
        {"k": KEY_BANK_MAIN},
    )
    row = res.first()
    main = Decimal(str(row[1])) if row else Decimal("0")
    return (main, Decimal("0"))


async def get_bank_balance(
    db: AsyncSession,
    *,
    initial_balance: Decimal | str = Decimal("0"),
) -> Decimal:
    """Return BANK_EFHC main balance through transactions SSOT."""

    bank_main, _bank_bonus = await _ensure_bank_locked(
        db,
        initial_balance=initial_balance,
    )
    return cast(Decimal, d8(bank_main))


async def _update_bank_balances(
    db: AsyncSession,
    *,
    new_main: Decimal,
    new_bonus: Decimal,
) -> None:
    """Обновляет баланс банка (истина = bank_balance)."""
    await db.execute(
        _BANK_UPD_SQL,
        {"key": KEY_BANK_MAIN, "bal": str(d8(new_main))},
    )


# ---------------------------------------------------------------------
# Канон direction в efhc_transfers_log: только credit/debit.
# Контрагентность (банк<->пользователь) фиксируется в reason/meta.
# Для зеркальной записи банка используем инверсию:
#   credit пользователя => debit банка
#   debit пользователя  => credit банка
# ---------------------------------------------------------------------


def _invert_direction(direction: str) -> str:
    if direction == "credit":
        return "debit"
    return "credit"


# ---------------------------------------------------------------------
# DTO результата операции
# ---------------------------------------------------------------------


@dataclass
class TxResult:
    ok: bool
    tg_id: int | None
    amount: Decimal
    balance_type: str  # "main" | "bonus"
    reason: str
    idempotency_key: str
    user__main__balance: Decimal
    user_bonus_balance: Decimal
    bank__main__balance: Decimal | None = None
    created_log_id: int | None = None
    detail: str = "ok"
    processed_with_deficit: bool = False
    meta: dict[str, object] | None = None
    bank_deficit_after: Decimal | None = None
    global_id: int | None = None


class IdempotencyPayloadConflictError(RuntimeError):
    """Тот же Idempotency-Key повторно использован с другим payload."""


@dataclass
class BankSupplyResult:
    """Result for admin-only bank supply changes.

    F-001 linkage repair: mint/burn must use existing official
    tables only. The canonical bank balance stays in
    efhc_core.bank_balance and the canonical audit/idempotency ledger is
    efhc_core.efhc_transfers_log.
    """

    ok: bool
    amount: Decimal
    direction: str
    reason: str
    idempotency_key: str
    bank__main__balance: Decimal
    created_log_id: int | None = None
    detail: str = "ok"


def _idempotent_detail(detail: str) -> bool:
    return str(detail or "").startswith("idempotent")


# ---------------------------------------------------------------------
# Низкоуровневые SQL
# (осознанно без ORM, ради прозрачности)
# ---------------------------------------------------------------------

_GET_USER_FOR_UPDATE_SQL = text("""
    SELECT
        global_id,
        COALESCE(main_balance, 0)  AS main_balance,
        COALESCE(bonus_balance, 0) AS bonus_balance
    FROM efhc_core.users
    WHERE global_id = :global_id
    FOR UPDATE
    """)


_GET_USER_SQL = text("""
    SELECT
        global_id,
        COALESCE(main_balance, 0)  AS main_balance,
        COALESCE(bonus_balance, 0) AS bonus_balance
    FROM efhc_core.users
    WHERE global_id = :global_id
    """)

_UPDATE_USER_BALANCES_SQL = text("""
    UPDATE efhc_core.users
    SET
        main_balance  = :mb,
        bonus_balance = :bb,
        updated_at    = NOW()
    WHERE global_id = :global_id
    """)


_INSERT_LOG_SQL = text("""
    INSERT INTO efhc_core.efhc_transfers_log (
        tg_id,
        global_id,
        system_entity,
        amount,
        direction,
        balance_type,
        reason,
        idempotency_key,
        created_at,
        meta
    )
    VALUES (
        :tg_id,
        :global_id,
        :system_entity,
        :amount,
        :direction,
        :balance_type,
        :reason,
        :idk,
        NOW(),
        COALESCE(CAST(:meta AS text), '{}')
    )
    ON CONFLICT (idempotency_key)
    DO NOTHING
    RETURNING id
    """)

_SELECT_LOG_BY_IDK_SQL = text("""
    SELECT
        id,
        tg_id,
        global_id,
        system_entity,
        amount,
        direction,
        balance_type,
        reason,
        idempotency_key,
        created_at
    FROM efhc_core.efhc_transfers_log
    WHERE idempotency_key = :idk
    LIMIT 1
    """)

_MARK_IDK_CONFLICT_SQL = text("""
    UPDATE efhc_core.efhc_transfers_log
    SET meta = (
        COALESCE(CAST(meta AS jsonb), '{}'::jsonb)
        || '{{"idk_conflict":"true"}}'::jsonb
    )::text
    WHERE idempotency_key = :idk
    """)


_APPEND_LOG_EXTRA_PG_SQL = text("""
    UPDATE efhc_core.efhc_transfers_log
    SET meta = (
        COALESCE(CAST(meta AS jsonb), '{}'::jsonb)
        || CAST(:extra AS jsonb)
    )::text
    WHERE id = :log_id
    """)


_APPEND_LOG_EXTRA_BY_IDK_PG_SQL = text("""
    UPDATE efhc_core.efhc_transfers_log
    SET meta = (
        COALESCE(CAST(meta AS jsonb), '{}'::jsonb)
        || CAST(:extra AS jsonb)
    )::text
    WHERE idempotency_key = :idk
    """)


async def append_transfer_meta(
    db: AsyncSession,
    *,
    log_id: int,
    meta: dict[str, Any],
) -> None:
    """Каноничный путь модификации efhc_transfers_log.meta.

    Правило проекта: любые записи/правки efhc_transfers_log должны
    происходить только через transactions_service.

    Реализация:
    - Postgres: jsonb merge (||)
    """

    if not log_id or int(log_id) <= 0:
        return

    payload = dict(meta or {})

    await db.execute(
        _APPEND_LOG_EXTRA_PG_SQL,
        {"log_id": int(log_id), "extra": json.dumps(payload)},
    )


async def append_transfer_meta_by_idempotency_key(
    db: AsyncSession,
    *,
    idempotency_key: str,
    meta: dict[str, Any],
) -> None:
    """Каноничный путь модификации efhc_transfers_log.meta по
    idempotency_key."""

    if not idempotency_key or not str(idempotency_key).strip():
        return
    payload = dict(meta or {})

    await db.execute(
        _APPEND_LOG_EXTRA_BY_IDK_PG_SQL,
        {"idk": str(idempotency_key), "extra": json.dumps(payload)},
    )


def _available_from_total_exchanged(
    total_generated_kwh: Decimal,
    exchanged_kwh_total: Decimal,
) -> Decimal:
    """SSOT mirror: available_kwh = max(total - exchanged, 0).

    All values are scale=8 (DOWN) via d8().
    """
    total_v = d8(total_generated_kwh)
    exch_v = d8(exchanged_kwh_total)
    avail = d8(total_v - exch_v)
    return avail if avail > Decimal("0") else Decimal("0")


# ---------------------------------------------------------------------
# Утилиты блокировки пользователя
# и фиксации балансов
# ---------------------------------------------------------------------


async def _ensure_user_locked(
    db: AsyncSession,
    *,
    global_id: int,
) -> tuple[Decimal, Decimal]:
    """Return locked balances for the canonical account owner."""
    res = await db.execute(
        _GET_USER_FOR_UPDATE_SQL,
        {"global_id": int(global_id)},
    )
    row = res.fetchone()
    if row:
        return d8(row[1] or 0), d8(row[2] or 0)
    raise RuntimeError(
        "user_not_onboarded: "
        f"global_id={global_id}; user creation is allowed only in "
        "onboard_user_at_first_creation"
    )


async def _update_user_balances(
    db: AsyncSession,
    main_balance: Decimal,
    bonus_balance: Decimal,
    *,
    global_id: int,
) -> None:
    """Update balances for the canonical account owner."""
    await db.execute(
        _UPDATE_USER_BALANCES_SQL,
        {
            "mb": str(d8(main_balance)),
            "bb": str(d8(bonus_balance)),
            "global_id": int(global_id),
        },
    )


async def _insert_log(
    db: AsyncSession,
    *,
    provider_tg_id: int | None,
    global_id: int | None = None,
    system_entity: str | None = None,
    amount: Decimal,
    direction: str,
    balance_type: str,
    reason: str,
    idk: str,
    meta: dict[str, Any] | None = None,
) -> int:
    """Write one canonical user or system-entity transfer row."""
    normalized_entity = str(system_entity or "").strip() or None
    if (
        provider_tg_id is None
        and global_id is None
        and normalized_entity is None
    ):
        raise RuntimeError("transfer_owner_required")
    if normalized_entity is not None and (
        provider_tg_id is not None or global_id is not None
    ):
        raise RuntimeError("system_entity_must_not_have_user_identity")
    extra_payload = json.dumps(dict(meta or {}))
    res = await db.execute(
        _INSERT_LOG_SQL,
        {
            "tg_id": (
                int(provider_tg_id)
                if provider_tg_id is not None
                else None
            ),
            "global_id": (
                int(global_id) if global_id is not None else None
            ),
            "system_entity": normalized_entity,
            "amount": str(d8(amount)),
            "direction": str(direction),
            "balance_type": str(balance_type),
            "reason": str(reason),
            "idk": str(idk),
            "meta": extra_payload,
        },
    )
    row = res.fetchone()
    if not row:
        existing = await _find_log_by_idk(db, idk)
        if existing:
            raise RuntimeError(f"IDEMPOTENCY_CONFLICT:{idk}")
        raise RuntimeError("LOG_INSERT_FAILED")
    return int(row[0])



async def _find_log_by_idk(
    db: AsyncSession,
    idk: str,
) -> dict[str, Any] | None:
    """Find one transfer by stable domain idempotency key."""
    res = await db.execute(_SELECT_LOG_BY_IDK_SQL, {"idk": idk})
    row = res.fetchone()
    if not row:
        return None
    return {
        "id": int(row[0]),
        "tg_id": (int(row[1]) if row[1] is not None else None),
        "global_id": (int(row[2]) if row[2] is not None else None),
        "system_entity": (str(row[3]) if row[3] is not None else None),
        "amount": Decimal(str(row[4])),
        "direction": str(row[5]),
        "balance_type": str(row[6]),
        "reason": str(row[7]),
        "idempotency_key": str(row[8]),
        "created_at": row[9],
    }



# ---------------------------------------------------------------------
# READ-THROUGH обвязка
# идемпотентной операции
# ---------------------------------------------------------------------

RunCore = Callable[
    ...,
    Awaitable[tuple[Decimal, Decimal, Decimal, bool]],
]


def _error_text(exc: Exception) -> str:
    return str(exc).lower()


def _is_idempotency_conflict(exc: Exception) -> bool:
    msg = _error_text(exc)
    return (
        msg.startswith("idempotency_conflict:")
        or "idempotency_conflict:" in msg
        or ("unique" in msg and "idempotency_key" in msg)
    )


def _is_transient_tx_error(exc: Exception) -> bool:
    msg = _error_text(exc)
    return any(
        marker in msg
        for marker in (
            "deadlock",
            "could not serialize",
            "serialization",
            "conflict",
        )
    )


async def _read_through_existing_tx(
    db: AsyncSession,
    *,
    global_id: int,
    provider_tg_id: int | None,
    idempotency_key: str,
    prev: dict[str, Any],
    with_bank_balance: bool,
    expected_amount: Decimal | None = None,
    expected_direction: str | None = None,
    expected_balance_type: str | None = None,
    expected_reason: str | None = None,
) -> TxResult:
    """Return an existing operation for either identity selector."""
    prev_global_id = prev.get("global_id")
    prev_tg_id = prev.get("tg_id")
    if (
        global_id is not None
        and prev_global_id is not None
        and int(prev_global_id) != int(global_id)
    ):
        raise RuntimeError(
            f"IDEMPOTENCY_OWNER_CONFLICT:{idempotency_key}"
        )
    payload_mismatch = (
        (
            expected_amount is not None
            and d8(prev.get("amount", "0")) != d8(expected_amount)
        )
        or (
            expected_direction is not None
            and str(prev.get("direction")) != str(expected_direction)
        )
        or (
            expected_balance_type is not None
            and str(prev.get("balance_type"))
            != str(expected_balance_type)
        )
        or (
            expected_reason is not None
            and str(prev.get("reason")) != str(expected_reason)
        )
    )
    if payload_mismatch:
        raise IdempotencyPayloadConflictError(
            "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD:"
            f"{idempotency_key}"
        )
    if (
        prev_global_id is None
        and provider_tg_id is not None
        and prev_tg_id is not None
        and int(prev_tg_id) != int(provider_tg_id)
    ):
        raise RuntimeError(
            f"IDEMPOTENCY_OWNER_CONFLICT:{idempotency_key}"
        )
    user_main, user_bonus = await _ensure_user_locked(
        db, global_id=global_id
    )
    bank_main: Decimal | None = None
    if with_bank_balance:
        bank_main, _ = await _ensure_bank_locked(db)
    return TxResult(
        ok=True,
        tg_id=(
            int(provider_tg_id)
            if provider_tg_id is not None
            else None
        ),
        amount=d8(prev["amount"]),
        balance_type=str(prev["balance_type"]),
        reason=str(prev["reason"]),
        idempotency_key=idempotency_key,
        user__main__balance=d8(user_main),
        user_bonus_balance=d8(user_bonus),
        bank__main__balance=(
            None if bank_main is None else d8(bank_main)
        ),
        created_log_id=int(prev["id"]),
        detail="idempotent",
        processed_with_deficit=False,
        global_id=int(global_id),
    )



async def _mark_idempotency_conflict(
    db: AsyncSession,
    *,
    idempotency_key: str,
) -> None:
    try:
        async with _tx_context(db):
            await db.execute(
                _MARK_IDK_CONFLICT_SQL,
                {"idk": idempotency_key},
            )
    except Exception:
        await _safe_rollback(db, "idk_conflict_mark")


async def _run_idempotent(
    db: AsyncSession,
    *,
    idempotency_key: str,
    global_id: int,
    balance_type: str,
    amount: Decimal,
    reason: str,
    direction: str,
    exec_core: RunCore,
    meta: dict[str, Any] | None = None,
) -> TxResult:
    """Execute one atomic idempotent canonical-owner operation."""
    max_tries = 3
    backoff = 0.15
    last_exc: Exception | None = None

    for attempt in range(1, max_tries + 1):
        try:
            async with _tx_context(db):
                owner = await resolve_and_lock_financial_write_owner(
                    db, global_id=global_id
                )
                prev = await _find_log_by_idk(db, idempotency_key)
                if prev:
                    return await _read_through_existing_tx(
                        db,
                        global_id=owner.global_id,
                        provider_tg_id=owner.provider_tg_id,
                        idempotency_key=idempotency_key,
                        prev=prev,
                        with_bank_balance=True,
                        expected_amount=amount,
                        expected_direction=direction,
                        expected_balance_type=balance_type,
                        expected_reason=reason,
                    )

                user_main, user_bonus = await _ensure_user_locked(
                    db, global_id=owner.global_id
                    )
                bank_main, bank_bonus = await _ensure_bank_locked(db)

                (
                    new_user_main,
                    new_user_bonus,
                    new_bank_main,
                    deficit,
                ) = await exec_core(
                    db=db,
                    provider_tg_id=owner.provider_tg_id,
                    global_id=owner.global_id,
                    user_main=user_main,
                    user_bonus=user_bonus,
                    bank_main=bank_main,
                    bank_bonus=bank_bonus,
                    amount=d8(amount),
                    balance_type=balance_type,
                    reason=reason,
                    idempotency_key=idempotency_key,
                )

                if (
                    new_user_main < Decimal("0")
                    or new_user_bonus < Decimal("0")
                ):
                    raise ValueError(
                        "User balance negative is forbidden"
                    )

                await _update_user_balances(
                    db,
                    new_user_main,
                    new_user_bonus,
                    global_id=owner.global_id,
                )
                await _update_bank_balances(
                    db,
                    new_main=new_bank_main,
                    new_bonus=bank_bonus,
                )

                meta_user: dict[str, Any] = dict(meta or {})
                meta_user["owner_global_id"] = str(owner.global_id)
                if deficit:
                    meta_user["bank_deficit_mode"] = "true"

                log_id = await _insert_log(
                    db,
                    provider_tg_id=owner.provider_tg_id,
                    global_id=owner.global_id,
                    amount=d8(amount),
                    direction=direction,
                    balance_type=balance_type,
                    reason=reason,
                    idk=idempotency_key,
                    meta=meta_user,
                )

                if BANK_SYSTEM_ENTITY:
                    mirror_key = f"mirror:{idempotency_key}"
                    meta_bank = {
                        "mirror_for_global_id": owner.global_id,
                        "mirror_of_idk": idempotency_key,
                    }
                    try:
                        await _insert_log(
                            db,
                            provider_tg_id=None,
                            system_entity=BANK_SYSTEM_ENTITY,
                            global_id=None,
                            amount=d8(amount),
                            direction=_invert_direction(direction),
                            balance_type="main",
                            reason=f"mirror:{reason}",
                            idk=mirror_key,
                            meta=meta_bank,
                        )
                    except Exception as mirror_exc:
                        if "unique" not in str(mirror_exc).lower():
                            logger.warning(
                                "Mirror log insert error: %s",
                                mirror_exc,
                            )

                return TxResult(
                    ok=True,
                    tg_id=owner.provider_tg_id,
                    amount=d8(amount),
                    balance_type=balance_type,
                    reason=reason,
                    idempotency_key=idempotency_key,
                    user__main__balance=d8(new_user_main),
                    user_bonus_balance=d8(new_user_bonus),
                    bank__main__balance=d8(new_bank_main),
                    created_log_id=int(log_id),
                    processed_with_deficit=bool(deficit),
                    detail="ok",
                    global_id=owner.global_id,
                )
        except ValueError:
            raise
        except Exception as exc:
            if _is_idempotency_conflict(exc):
                await _mark_idempotency_conflict(
                    db, idempotency_key=idempotency_key
                )
                prev = await _find_log_by_idk(db, idempotency_key)
                if prev:
                    await _safe_rollback(db, "idk_read_through")
                    async with _tx_context(db):
                        resolver = (
                            resolve_and_lock_financial_write_owner
                        )
                        owner = await resolver(
                            db, global_id=global_id
                        )
                        return await _read_through_existing_tx(
                            db,
                            provider_tg_id=owner.provider_tg_id,
                            global_id=owner.global_id,
                            idempotency_key=idempotency_key,
                            prev=prev,
                            with_bank_balance=False,
                            expected_amount=amount,
                            expected_direction=direction,
                            expected_balance_type=balance_type,
                            expected_reason=reason,
                        )
                await asyncio.sleep(backoff * attempt)
                last_exc = exc
                continue
            if _is_transient_tx_error(exc):
                await asyncio.sleep(backoff * attempt)
                last_exc = exc
                continue
            last_exc = exc
            logger.error(
                "Bank tx fatal error (attempt %s/%s): %s",
                attempt,
                max_tries,
                exc,
            )
            break

    raise RuntimeError(
        f"Bank transaction failed after {max_tries} attempts: "
        f"{last_exc}"
    )



# ---------------------------------------------------------------------
# Бизнес-операции (канон)
# ---------------------------------------------------------------------


async def credit_user_from_bank(
    db: AsyncSession,
    *,
    global_id: int,
    amount_efhc: Decimal | None = None,
    amount: Decimal | None = None,
    reason: str,
    idempotency_key: str,
    meta: dict[str, Any] | None = None,
) -> TxResult:
    """Canonical owner credit for MAIN."""
    if amount is None and amount_efhc is None:
        raise ValueError("Необходимо указать amount или amount_efhc")
    if amount is None:
        amount = amount_efhc
    amt = cast(Decimal, d8(amount))
    if amt <= Decimal("0"):
        raise ValueError("Сумма должна быть > 0")

    async def _core(
        **kwargs: Any,
    ) -> tuple[Decimal, Decimal, Decimal, bool]:
        user_main: Decimal = kwargs["user_main"]
        user_bonus: Decimal = kwargs["user_bonus"]
        bank_main: Decimal = kwargs["bank_main"]
        amount_local: Decimal = kwargs["amount"]
        new_user_main = d8(user_main + amount_local)
        new_bank_main = d8(bank_main - amount_local)
        return (
            new_user_main,
            user_bonus,
            new_bank_main,
            new_bank_main < Decimal("0"),
        )

    return await _run_idempotent(
        db,
        idempotency_key=str(idempotency_key),
        global_id=global_id,
        balance_type="main",
        amount=amt,
        reason=reason,
        direction="credit",
        exec_core=_core,
        meta=meta,
    )



async def credit_user_from_bank_nocommit(
    db: AsyncSession,
    *,
    global_id: int,
    amount_efhc: Decimal | None = None,
    amount: Decimal | None = None,
    reason: str,
    idempotency_key: str,
    meta: dict[str, Any] | None = None,
) -> TxResult:
    """HEAL-0024 canonical path; caller owns transaction boundary."""
    if amount is None and amount_efhc is None:
        raise ValueError("Необходимо указать amount или amount_efhc")
    if amount is None:
        amount = amount_efhc
    amt = cast(Decimal, d8(amount))
    if amt <= Decimal("0"):
        raise ValueError("Сумма должна быть > 0")

    owner = await resolve_and_lock_financial_write_owner(
        db, global_id=global_id
    )
    prev = await _find_log_by_idk(db, str(idempotency_key))
    if prev:
        return await _read_through_existing_tx(
            db,
            provider_tg_id=owner.provider_tg_id,
            global_id=owner.global_id,
            idempotency_key=str(idempotency_key),
            prev=prev,
            with_bank_balance=True,
            expected_amount=amt,
            expected_direction="credit",
            expected_balance_type="main",
            expected_reason=reason,
        )
    user_main, user_bonus = await _ensure_user_locked(
        db, global_id=owner.global_id
    )
    bank_main, bank_bonus = await _ensure_bank_locked(db)
    locked_prev = await _find_log_by_idk(db, str(idempotency_key))
    if locked_prev:
        return await _read_through_existing_tx(
            db,
            provider_tg_id=owner.provider_tg_id,
            global_id=owner.global_id,
            idempotency_key=str(idempotency_key),
            prev=locked_prev,
            with_bank_balance=True,
            expected_amount=amt,
            expected_direction="credit",
            expected_balance_type="main",
            expected_reason=reason,
        )
    new_user_main = d8(user_main + amt)
    new_user_bonus = user_bonus
    new_bank_main = d8(bank_main - amt)
    deficit = new_bank_main < Decimal("0")

    await _update_user_balances(
        db,
        new_user_main,
        new_user_bonus,
        global_id=owner.global_id,
    )
    await _update_bank_balances(
        db, new_main=new_bank_main, new_bonus=bank_bonus
    )
    meta_user = dict(meta or {})
    meta_user["owner_global_id"] = str(owner.global_id)
    if deficit:
        meta_user["bank_deficit_mode"] = "true"
    log_id = await _insert_log(
        db,
        provider_tg_id=owner.provider_tg_id,
        global_id=owner.global_id,
        amount=amt,
        direction="credit",
        balance_type="main",
        reason=reason,
        idk=str(idempotency_key),
        meta=meta_user,
    )
    if BANK_SYSTEM_ENTITY:
        await _insert_log(
            db,
            provider_tg_id=None,
            system_entity=BANK_SYSTEM_ENTITY,
            global_id=None,
            amount=amt,
            direction=_invert_direction("credit"),
            balance_type="main",
            reason=f"mirror:{reason}",
            idk=f"mirror:{idempotency_key}",
            meta={
                "mirror_for_global_id": owner.global_id,
                "mirror_of_idk": str(idempotency_key),
            },
        )
    return TxResult(
        ok=True,
        tg_id=owner.provider_tg_id,
        amount=amt,
        balance_type="main",
        reason=reason,
        idempotency_key=str(idempotency_key),
        user__main__balance=d8(new_user_main),
        user_bonus_balance=d8(new_user_bonus),
        bank__main__balance=d8(new_bank_main),
        created_log_id=int(log_id),
        processed_with_deficit=bool(deficit),
        detail="ok",
        global_id=owner.global_id,
    )



async def credit_user_bonus_from_bank(
    db: AsyncSession,
    *,
    global_id: int,
    amount_efhc: Decimal | None = None,
    amount: Decimal | None = None,
    reason: str,
    idempotency_key: str,
    meta: dict[str, Any] | None = None,
) -> TxResult:
    """Canonical owner credit for BONUS."""
    if amount is None and amount_efhc is None:
        raise ValueError("Необходимо указать amount или amount_efhc")
    if amount is None:
        amount = amount_efhc
    amt = cast(Decimal, d8(amount))
    if amt <= Decimal("0"):
        raise ValueError("Сумма должна быть > 0")

    async def _core(
        **kwargs: Any,
    ) -> tuple[Decimal, Decimal, Decimal, bool]:
        user_main: Decimal = kwargs["user_main"]
        user_bonus: Decimal = kwargs["user_bonus"]
        bank_main: Decimal = kwargs["bank_main"]
        amount_local: Decimal = kwargs["amount"]
        new_user_bonus = d8(user_bonus + amount_local)
        new_bank_main = d8(bank_main - amount_local)
        return (
            user_main,
            new_user_bonus,
            new_bank_main,
            new_bank_main < Decimal("0"),
        )

    return await _run_idempotent(
        db,
        idempotency_key=str(idempotency_key),
        global_id=global_id,
        balance_type="bonus",
        amount=amt,
        reason=reason,
        direction="credit",
        exec_core=_core,
        meta=meta,
    )



async def credit_user_bonus_from_bank_nocommit(
    db: AsyncSession,
    *,
    global_id: int,
    amount_efhc: Decimal | None = None,
    amount: Decimal | None = None,
    reason: str,
    idempotency_key: str,
    meta: dict[str, Any] | None = None,
) -> TxResult:
    """Canonical nocommit path; caller owns transaction boundary."""
    if amount is None and amount_efhc is None:
        raise ValueError("Необходимо указать amount или amount_efhc")
    if amount is None:
        amount = amount_efhc
    amt = cast(Decimal, d8(amount))
    if amt <= Decimal("0"):
        raise ValueError("Сумма должна быть > 0")

    owner = await resolve_and_lock_financial_write_owner(
        db, global_id=global_id
    )
    prev = await _find_log_by_idk(db, str(idempotency_key))
    if prev:
        return await _read_through_existing_tx(
            db,
            provider_tg_id=owner.provider_tg_id,
            global_id=owner.global_id,
            idempotency_key=str(idempotency_key),
            prev=prev,
            with_bank_balance=True,
            expected_amount=amt,
            expected_direction="credit",
            expected_balance_type="bonus",
            expected_reason=reason,
        )
    user_main, user_bonus = await _ensure_user_locked(
        db, global_id=owner.global_id
    )
    bank_main, bank_bonus = await _ensure_bank_locked(db)
    locked_prev = await _find_log_by_idk(db, str(idempotency_key))
    if locked_prev:
        return await _read_through_existing_tx(
            db,
            provider_tg_id=owner.provider_tg_id,
            global_id=owner.global_id,
            idempotency_key=str(idempotency_key),
            prev=locked_prev,
            with_bank_balance=True,
            expected_amount=amt,
            expected_direction="credit",
            expected_balance_type="bonus",
            expected_reason=reason,
        )
    new_user_main = user_main
    new_user_bonus = d8(user_bonus + amt)
    new_bank_main = d8(bank_main - amt)
    deficit = new_bank_main < Decimal("0")

    await _update_user_balances(
        db,
        new_user_main,
        new_user_bonus,
        global_id=owner.global_id,
    )
    await _update_bank_balances(
        db, new_main=new_bank_main, new_bonus=bank_bonus
    )
    meta_user = dict(meta or {})
    meta_user["owner_global_id"] = str(owner.global_id)
    if deficit:
        meta_user["bank_deficit_mode"] = "true"
    log_id = await _insert_log(
        db,
        provider_tg_id=owner.provider_tg_id,
        global_id=owner.global_id,
        amount=amt,
        direction="credit",
        balance_type="bonus",
        reason=reason,
        idk=str(idempotency_key),
        meta=meta_user,
    )
    if BANK_SYSTEM_ENTITY:
        await _insert_log(
            db,
            provider_tg_id=None,
            system_entity=BANK_SYSTEM_ENTITY,
            global_id=None,
            amount=amt,
            direction=_invert_direction("credit"),
            balance_type="main",
            reason=f"mirror:{reason}",
            idk=f"mirror:{idempotency_key}",
            meta={
                "mirror_for_global_id": owner.global_id,
                "mirror_of_idk": str(idempotency_key),
            },
        )
    return TxResult(
        ok=True,
        tg_id=owner.provider_tg_id,
        amount=amt,
        balance_type="bonus",
        reason=reason,
        idempotency_key=str(idempotency_key),
        user__main__balance=d8(new_user_main),
        user_bonus_balance=d8(new_user_bonus),
        bank__main__balance=d8(new_bank_main),
        created_log_id=int(log_id),
        processed_with_deficit=bool(deficit),
        detail="ok",
        global_id=owner.global_id,
    )



async def debit_user_to_bank(
    db: AsyncSession,
    *,
    global_id: int,
    amount_efhc: Decimal | None = None,
    amount: Decimal | None = None,
    reason: str,
    idempotency_key: str,
    meta: dict[str, Any] | None = None,
) -> TxResult:
    """Canonical owner debit for MAIN."""
    if amount is None and amount_efhc is None:
        raise ValueError("Необходимо указать amount или amount_efhc")
    if amount is None:
        amount = amount_efhc
    amt = cast(Decimal, d8(amount))
    if amt <= Decimal("0"):
        raise ValueError("Сумма должна быть > 0")

    async def _core(
        **kwargs: Any,
    ) -> tuple[Decimal, Decimal, Decimal, bool]:
        user_main: Decimal = kwargs["user_main"]
        user_bonus: Decimal = kwargs["user_bonus"]
        bank_main: Decimal = kwargs["bank_main"]
        amount_local: Decimal = kwargs["amount"]
        if user_main - amount_local < Decimal("0"):
            raise ValueError("Недостаточно средств на основном балансе")
        new_user_main = d8(user_main - amount_local)
        new_bank_main = d8(bank_main + amount_local)
        return (
            new_user_main,
            user_bonus,
            new_bank_main,
            new_bank_main < Decimal("0"),
        )

    return await _run_idempotent(
        db,
        idempotency_key=str(idempotency_key),
        global_id=global_id,
        balance_type="main",
        amount=amt,
        reason=reason,
        direction="debit",
        exec_core=_core,
        meta=meta,
    )



async def debit_user_to_bank_nocommit(
    db: AsyncSession,
    *,
    global_id: int,
    amount_efhc: Decimal | None = None,
    amount: Decimal | None = None,
    reason: str,
    idempotency_key: str,
    meta: dict[str, Any] | None = None,
) -> TxResult:
    """HEAL-0024 canonical path; caller owns transaction boundary."""
    if amount is None and amount_efhc is None:
        raise ValueError("Необходимо указать amount или amount_efhc")
    if amount is None:
        amount = amount_efhc
    amt = cast(Decimal, d8(amount))
    if amt <= Decimal("0"):
        raise ValueError("Сумма должна быть > 0")

    owner = await resolve_and_lock_financial_write_owner(
        db, global_id=global_id
    )
    prev = await _find_log_by_idk(db, str(idempotency_key))
    if prev:
        return await _read_through_existing_tx(
            db,
            provider_tg_id=owner.provider_tg_id,
            global_id=owner.global_id,
            idempotency_key=str(idempotency_key),
            prev=prev,
            with_bank_balance=True,
            expected_amount=amt,
            expected_direction="debit",
            expected_balance_type="main",
            expected_reason=reason,
        )
    user_main, user_bonus = await _ensure_user_locked(
        db, global_id=owner.global_id
    )
    bank_main, bank_bonus = await _ensure_bank_locked(db)
    if user_main - amt < Decimal("0"):
        raise ValueError("Недостаточно средств на основном балансе")
    new_user_main = d8(user_main - amt)
    new_user_bonus = user_bonus
    new_bank_main = d8(bank_main + amt)
    deficit = new_bank_main < Decimal("0")

    await _update_user_balances(
        db,
        new_user_main,
        new_user_bonus,
        global_id=owner.global_id,
    )
    await _update_bank_balances(
        db, new_main=new_bank_main, new_bonus=bank_bonus
    )
    meta_user = dict(meta or {})
    meta_user["owner_global_id"] = str(owner.global_id)
    if deficit:
        meta_user["bank_deficit_mode"] = "true"
    log_id = await _insert_log(
        db,
        provider_tg_id=owner.provider_tg_id,
        global_id=owner.global_id,
        amount=amt,
        direction="debit",
        balance_type="main",
        reason=reason,
        idk=str(idempotency_key),
        meta=meta_user,
    )
    if BANK_SYSTEM_ENTITY:
        await _insert_log(
            db,
            provider_tg_id=None,
            system_entity=BANK_SYSTEM_ENTITY,
            global_id=None,
            amount=amt,
            direction=_invert_direction("debit"),
            balance_type="main",
            reason=f"mirror:{reason}",
            idk=f"mirror:{idempotency_key}",
            meta={
                "mirror_for_global_id": owner.global_id,
                "mirror_of_idk": str(idempotency_key),
            },
        )
    return TxResult(
        ok=True,
        tg_id=owner.provider_tg_id,
        amount=amt,
        balance_type="main",
        reason=reason,
        idempotency_key=str(idempotency_key),
        user__main__balance=d8(new_user_main),
        user_bonus_balance=d8(new_user_bonus),
        bank__main__balance=d8(new_bank_main),
        created_log_id=int(log_id),
        processed_with_deficit=bool(deficit),
        detail="ok",
        global_id=owner.global_id,
    )



async def debit_user_bonus_to_bank(
    db: AsyncSession,
    *,
    global_id: int,
    amount_efhc: Decimal | None = None,
    amount: Decimal | None = None,
    reason: str,
    idempotency_key: str,
    meta: dict[str, Any] | None = None,
) -> TxResult:
    """Canonical owner debit for BONUS."""
    if amount is None and amount_efhc is None:
        raise ValueError("Необходимо указать amount или amount_efhc")
    if amount is None:
        amount = amount_efhc
    amt = cast(Decimal, d8(amount))
    if amt <= Decimal("0"):
        raise ValueError("Сумма должна быть > 0")

    async def _core(
        **kwargs: Any,
    ) -> tuple[Decimal, Decimal, Decimal, bool]:
        user_main: Decimal = kwargs["user_main"]
        user_bonus: Decimal = kwargs["user_bonus"]
        bank_main: Decimal = kwargs["bank_main"]
        amount_local: Decimal = kwargs["amount"]
        if user_bonus - amount_local < Decimal("0"):
            raise ValueError("Недостаточно средств на бонусном балансе")
        new_user_bonus = d8(user_bonus - amount_local)
        new_bank_main = d8(bank_main + amount_local)
        return (
            user_main,
            new_user_bonus,
            new_bank_main,
            new_bank_main < Decimal("0"),
        )

    return await _run_idempotent(
        db,
        idempotency_key=str(idempotency_key),
        global_id=global_id,
        balance_type="bonus",
        amount=amt,
        reason=reason,
        direction="debit",
        exec_core=_core,
        meta=meta,
    )


async def debit_user_bonus_to_bank_nocommit(
    db: AsyncSession,
    *,
    global_id: int,
    amount_efhc: Decimal | None = None,
    amount: Decimal | None = None,
    reason: str,
    idempotency_key: str,
    meta: dict[str, Any] | None = None,
) -> TxResult:
    """Списать BONUS в банк без commit; DB transaction принадлежит caller."""
    if amount is None and amount_efhc is None:
        raise ValueError("Необходимо указать amount или amount_efhc")
    if amount is None:
        amount = amount_efhc
    amt = cast(Decimal, d8(amount))
    if amt <= Decimal("0"):
        raise ValueError("Сумма должна быть > 0")

    owner = await resolve_and_lock_financial_write_owner(
        db, global_id=global_id
    )
    prev = await _find_log_by_idk(db, str(idempotency_key))
    if prev:
        return await _read_through_existing_tx(
            db,
            provider_tg_id=owner.provider_tg_id,
            global_id=owner.global_id,
            idempotency_key=str(idempotency_key),
            prev=prev,
            with_bank_balance=True,
            expected_amount=amt,
            expected_direction="debit",
            expected_balance_type="bonus",
            expected_reason=reason,
        )
    user_main, user_bonus = await _ensure_user_locked(
        db, global_id=owner.global_id
    )
    bank_main, bank_bonus = await _ensure_bank_locked(db)
    locked_prev = await _find_log_by_idk(db, str(idempotency_key))
    if locked_prev:
        return await _read_through_existing_tx(
            db,
            provider_tg_id=owner.provider_tg_id,
            global_id=owner.global_id,
            idempotency_key=str(idempotency_key),
            prev=locked_prev,
            with_bank_balance=True,
            expected_amount=amt,
            expected_direction="debit",
            expected_balance_type="bonus",
            expected_reason=reason,
        )
    if user_bonus - amt < Decimal("0"):
        raise ValueError("Недостаточно средств на бонусном балансе")
    new_user_main = user_main
    new_user_bonus = d8(user_bonus - amt)
    new_bank_main = d8(bank_main + amt)
    deficit = new_bank_main < Decimal("0")

    await _update_user_balances(
        db,
        new_user_main,
        new_user_bonus,
        global_id=owner.global_id,
    )
    await _update_bank_balances(
        db, new_main=new_bank_main, new_bonus=bank_bonus
    )
    meta_user = dict(meta or {})
    meta_user["owner_global_id"] = str(owner.global_id)
    log_id = await _insert_log(
        db,
        provider_tg_id=owner.provider_tg_id,
        global_id=owner.global_id,
        amount=amt,
        direction="debit",
        balance_type="bonus",
        reason=reason,
        idk=str(idempotency_key),
        meta=meta_user,
    )
    if BANK_SYSTEM_ENTITY:
        await _insert_log(
            db,
            provider_tg_id=None,
            system_entity=BANK_SYSTEM_ENTITY,
            global_id=None,
            amount=amt,
            direction=_invert_direction("debit"),
            balance_type="main",
            reason=f"mirror:{reason}",
            idk=f"mirror:{idempotency_key}",
            meta={
                "mirror_for_global_id": owner.global_id,
                "mirror_of_idk": str(idempotency_key),
            },
        )
    return TxResult(
        ok=True,
        tg_id=owner.provider_tg_id,
        amount=amt,
        balance_type="bonus",
        reason=reason,
        idempotency_key=str(idempotency_key),
        user__main__balance=d8(new_user_main),
        user_bonus_balance=d8(new_user_bonus),
        bank__main__balance=d8(new_bank_main),
        created_log_id=int(log_id),
        processed_with_deficit=bool(deficit),
        detail="ok",
        global_id=owner.global_id,
    )



def _bank_supply_idempotency_matches(
    prev: dict[str, Any],
    *,
    amount: Decimal,
    direction: str,
    reason: str,
) -> bool:
    return (
        d8(prev.get("amount", "0")) == d8(amount)
        and str(prev.get("direction")) == str(direction)
        and str(prev.get("balance_type")) == "main"
        and str(prev.get("reason")) == str(reason)
    )


async def _run_bank_supply_change(
    db: AsyncSession,
    *,
    amount: Decimal,
    direction: str,
    reason: str,
    idempotency_key: str,
    meta: dict[str, Any] | None = None,
) -> BankSupplyResult:
    """Change BANK_EFHC supply through canonical tables only.

    F-001 linkage repair repair:
    - no runtime dependency on the former separate mint/burn ledger;
    - no runtime dependency on the former rollback journal;
    - idempotency/audit surface is efhc_core.efhc_transfers_log;
    - bank balance SSOT is efhc_core.bank_balance.
    """

    amt = d8(amount)
    if amt <= Decimal("0"):
        raise ValueError("Сумма должна быть > 0")
    if not idempotency_key or not str(idempotency_key).strip():
        raise ValueError("Idempotency-Key обязателен")
    if direction not in {"credit", "debit"}:
        raise ValueError("direction must be credit or debit")

    async with _tx_context(db):
        prev = await _find_log_by_idk(db, str(idempotency_key))
        if prev:
            if not _bank_supply_idempotency_matches(
                prev,
                amount=amt,
                direction=direction,
                reason=reason,
            ):
                raise ValueError(
                    "IDEMPOTENCY_KEY_REUSED_FOR_DIFFERENT_"
                    "BANK_OPERATION"
                )
            bank_main, _bank_bonus = await _ensure_bank_locked(db)
            return BankSupplyResult(
                ok=True,
                amount=amt,
                direction=direction,
                reason=reason,
                idempotency_key=str(idempotency_key),
                bank__main__balance=d8(bank_main),
                created_log_id=int(prev["id"]),
                detail="idempotent",
            )

        bank_main, bank_bonus = await _ensure_bank_locked(db)
        if direction == "credit":
            new_bank_main = d8(bank_main + amt)
        else:
            new_bank_main = d8(bank_main - amt)

        await _update_bank_balances(
            db,
            new_main=new_bank_main,
            new_bonus=bank_bonus,
        )

        payload = dict(meta or {})
        payload.setdefault("source", "admin_bank_supply")
        payload.setdefault(
            "canonical_balance_table",
            "efhc_core.bank_balance",
        )
        payload.setdefault(
            "canonical_ledger",
            "efhc_core.efhc_transfers_log",
        )

        log_id = await _insert_log(
            db,
            provider_tg_id=None,
            system_entity=BANK_SYSTEM_ENTITY,
            amount=amt,
            direction=direction,
            balance_type="main",
            reason=reason,
            idk=str(idempotency_key),
            meta=payload,
        )

        return BankSupplyResult(
            ok=True,
            amount=amt,
            direction=direction,
            reason=reason,
            idempotency_key=str(idempotency_key),
            bank__main__balance=d8(new_bank_main),
            created_log_id=int(log_id),
            detail="ok",
        )


async def _run_bank_supply_change_nocommit(
    db: AsyncSession,
    *,
    amount: Decimal,
    direction: str,
    reason: str,
    idempotency_key: str,
    meta: dict[str, Any] | None = None,
) -> BankSupplyResult:
    """Изменить supply BANK_EFHC без самостоятельного commit.

    Этот вариант нужен только для операций, где денежная проводка и
    обязательный Admin audit должны фиксироваться одной корневой DB
    транзакцией. Вызывающий слой полностью владеет commit/rollback.
    """
    amt = d8(amount)
    if amt <= Decimal("0"):
        raise ValueError("Сумма должна быть > 0")
    if not idempotency_key or not str(idempotency_key).strip():
        raise ValueError("Idempotency-Key обязателен")
    if direction not in {"credit", "debit"}:
        raise ValueError("direction must be credit or debit")

    prev = await _find_log_by_idk(db, str(idempotency_key))
    if prev:
        if not _bank_supply_idempotency_matches(
            prev,
            amount=amt,
            direction=direction,
            reason=reason,
        ):
            raise IdempotencyPayloadConflictError(
                "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD"
            )
        bank_main, _bank_bonus = await _ensure_bank_locked(db)
        return BankSupplyResult(
            ok=True,
            amount=amt,
            direction=direction,
            reason=reason,
            idempotency_key=str(idempotency_key),
            bank__main__balance=d8(bank_main),
            created_log_id=int(prev["id"]),
            detail="idempotent",
        )

    bank_main, bank_bonus = await _ensure_bank_locked(db)
    locked_prev = await _find_log_by_idk(db, str(idempotency_key))
    if locked_prev:
        if not _bank_supply_idempotency_matches(
            locked_prev,
            amount=amt,
            direction=direction,
            reason=reason,
        ):
            raise IdempotencyPayloadConflictError(
                "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD"
            )
        return BankSupplyResult(
            ok=True,
            amount=amt,
            direction=direction,
            reason=reason,
            idempotency_key=str(idempotency_key),
            bank__main__balance=d8(bank_main),
            created_log_id=int(locked_prev["id"]),
            detail="idempotent",
        )

    new_bank_main = (
        d8(bank_main + amt)
        if direction == "credit"
        else d8(bank_main - amt)
    )
    await _update_bank_balances(
        db,
        new_main=new_bank_main,
        new_bonus=bank_bonus,
    )

    payload = dict(meta or {})
    payload.setdefault("source", "admin_bank_supply")
    payload.setdefault(
        "canonical_balance_table",
        "efhc_core.bank_balance",
    )
    payload.setdefault(
        "canonical_ledger",
        "efhc_core.efhc_transfers_log",
    )
    log_id = await _insert_log(
        db,
        provider_tg_id=None,
        system_entity=BANK_SYSTEM_ENTITY,
        amount=amt,
        direction=direction,
        balance_type="main",
        reason=reason,
        idk=str(idempotency_key),
        meta=payload,
    )
    return BankSupplyResult(
        ok=True,
        amount=amt,
        direction=direction,
        reason=reason,
        idempotency_key=str(idempotency_key),
        bank__main__balance=d8(new_bank_main),
        created_log_id=int(log_id),
        detail="ok",
    )


async def mint_bank_efhc(
    db: AsyncSession,
    *,
    amount: Decimal,
    reason: str,
    idempotency_key: str,
    meta: dict[str, Any] | None = None,
) -> BankSupplyResult:
    """Mint EFHC into BANK_EFHC via canonical SSOT tables."""

    return await _run_bank_supply_change(
        db,
        amount=amount,
        direction="credit",
        reason="admin_bank_mint",
        idempotency_key=idempotency_key,
        meta={**dict(meta or {}), "admin_reason": str(reason or "")},
    )


async def mint_bank_efhc_nocommit(
    db: AsyncSession,
    *,
    amount: Decimal,
    reason: str,
    idempotency_key: str,
    meta: dict[str, Any] | None = None,
) -> BankSupplyResult:
    """Начислить supply BANK_EFHC без commit; граница у Admin service."""
    return await _run_bank_supply_change_nocommit(
        db,
        amount=amount,
        direction="credit",
        reason="admin_bank_mint",
        idempotency_key=idempotency_key,
        meta={**dict(meta or {}), "admin_reason": str(reason or "")},
    )


async def burn_bank_efhc(
    db: AsyncSession,
    *,
    amount: Decimal,
    reason: str,
    idempotency_key: str,
    meta: dict[str, Any] | None = None,
) -> BankSupplyResult:
    """Burn EFHC from BANK_EFHC via canonical SSOT tables."""

    return await _run_bank_supply_change(
        db,
        amount=amount,
        direction="debit",
        reason="admin_bank_burn",
        idempotency_key=idempotency_key,
        meta={**dict(meta or {}), "admin_reason": str(reason or "")},
    )


async def burn_bank_efhc_nocommit(
    db: AsyncSession,
    *,
    amount: Decimal,
    reason: str,
    idempotency_key: str,
    meta: dict[str, Any] | None = None,
) -> BankSupplyResult:
    """Уменьшить supply BANK_EFHC без commit; граница у Admin service."""
    return await _run_bank_supply_change_nocommit(
        db,
        amount=amount,
        direction="debit",
        reason="admin_bank_burn",
        idempotency_key=idempotency_key,
        meta={**dict(meta or {}), "admin_reason": str(reason or "")},
    )


async def exchange_kwh_to_efhc(
    db: AsyncSession,
    *,
    global_id: int,
    amount_kwh: Decimal | None = None,
    amount: Decimal | None = None,
    reason: str,
    idempotency_key: str,
    strict_kwh_check: bool = False,
) -> TxResult:
    """Обмен kWh → EFHC (1:1)."""
    if amount is None and amount_kwh is None:
        raise ValueError(
            (
                "Необходимо указать amount ",
                "или amount_kwh",
            )
        )
    if amount is None:
        amount = amount_kwh

    amt = d8(amount)
    if amt <= Decimal("0"):
        raise ValueError("Сумма должна быть > 0")

    async def _core(
        **kwargs: Any,
    ) -> tuple[Decimal, Decimal, Decimal, bool]:
        user_main: Decimal = kwargs["user_main"]
        user_bonus: Decimal = kwargs["user_bonus"]
        bank_main: Decimal = kwargs["bank_main"]
        amount_local: Decimal = kwargs["amount"]

        if strict_kwh_check:
            q = (
                "SELECT "
                "COALESCE(total_generated_kwh, 0), "
                "COALESCE(exchanged_kwh_total, 0) "
                "FROM efhc_core.users WHERE global_id = :global_id"
            )
            row = await db.execute(
                text(q),
                {"global_id": int(global_id)},
            )
            rec = row.fetchone()
            total_kwh = d8(rec[0] if rec else 0)
            exchanged_total = d8(rec[1] if rec else 0)
            ak = _available_from_total_exchanged(
                total_kwh,
                exchanged_total,
            )
            if ak < amount_local:
                raise ValueError("Недостаточно доступной энергии")

        new_user_main = d8(user_main + amount_local)
        new_user_bonus = user_bonus
        new_bank_main = d8(bank_main - amount_local)
        deficit = new_bank_main < Decimal("0")
        return (new_user_main, new_user_bonus, new_bank_main, deficit)

    return await _run_idempotent(
        db,
        idempotency_key=idempotency_key,
        global_id=global_id,
        balance_type="main",
        amount=amt,
        reason=reason,
        direction="credit",
        exec_core=_core,
    )


async def exchange_partial_available_kwh_to_main(
    db: AsyncSession,
    *,
    global_id: int,
    amount_kwh: Decimal,
    idempotency_key: str,
    reason: str = "exchange_partial",
) -> TxResult:
    """Частичный обмен available_kwh → MAIN по канону 1:1."""

    amt = d8(amount_kwh)
    if amt <= Decimal("0"):
        raise ValueError("Сумма должна быть > 0")
    if not idempotency_key or not str(idempotency_key).strip():
        raise ValueError("Idempotency-Key обязателен")

    await _rollback_started_exchange_transaction(
        db,
        ctx="exchange_partial_preflight",
    )

    max_tries = 3
    last_exc: Exception | None = None

    for _attempt in range(1, max_tries + 1):
        try:
            owner = await resolve_and_lock_financial_write_owner(
                db,
                global_id=global_id,
            )
            q_user = text(
                "SELECT "
                "COALESCE(main_balance, 0), "
                "COALESCE(bonus_balance, 0), "
                "COALESCE(total_generated_kwh, 0), "
                "COALESCE(exchanged_kwh_total, 0) "
                "FROM efhc_core.users "
                "WHERE global_id = :global_id FOR UPDATE"
            )
            rec = await db.execute(
                q_user,
                {"global_id": int(owner.global_id)},
            )
            row = rec.fetchone()
            if not row:
                raise ValueError("User not found")

            existing = await _find_log_by_idk(db, str(idempotency_key))
            if existing:
                return await _read_through_existing_tx(
                    db,
                    provider_tg_id=owner.provider_tg_id,
                    global_id=owner.global_id,
                    idempotency_key=str(idempotency_key),
                    prev=existing,
                    with_bank_balance=True,
                    expected_amount=amt,
                    expected_direction="credit",
                    expected_balance_type="main",
                    expected_reason=reason,
                )

            user_main = d8(row[0] or 0)
            user_bonus = d8(row[1] or 0)
            total_kwh = d8(row[2] or 0)
            exchanged_total = d8(row[3] or 0)

            if exchanged_total > total_kwh:
                raise ValueError("SSOT violated: exchanged > total")

            available = _available_from_total_exchanged(
                total_kwh,
                exchanged_total,
            )
            if available < amt:
                raise ValueError("Недостаточно available_kwh")

            bank_main, bank_bonus = await _ensure_bank_locked(db)

            new_user_main = d8(user_main + amt)
            new_user_bonus = user_bonus
            new_bank_main = d8(bank_main - amt)
            deficit = new_bank_main < Decimal("0")
            new_exchanged_total = d8(exchanged_total + amt)
            new_available = _available_from_total_exchanged(
                total_kwh,
                new_exchanged_total,
            )

            await _update_user_balances(
                db,
                new_user_main,
                new_user_bonus,
                global_id=owner.global_id,
            )
            await _update_bank_balances(
                db,
                new_main=new_bank_main,
                new_bonus=bank_bonus,
            )

            q_energy = (
                "UPDATE efhc_core.users "
                "SET exchanged_kwh_total = :ex, "
                "    updated_at = now() "
                "WHERE global_id = :global_id"
            )
            await db.execute(
                text(q_energy),
                {
                    "ex": str(d8(new_exchanged_total)),
                    "global_id": int(owner.global_id),
                },
            )

            total_equiv_before = d8(user_main + available)
            total_equiv_after = d8(new_user_main + new_available)
            audit_ok = bool(total_equiv_before == total_equiv_after)
            audit = {
                "audit__schema__version": "v1",
                "exchange_partial_audit": True,
                "op_type": "EXCHANGE_PARTIAL",
                "status": "success",
                "rate": "1.00000000",
                "before": {
                    "total_generated_kwh": str(total_kwh),
                    "exchanged_kwh_total": str(exchanged_total),
                    "available_kwh": str(available),
                    "main_balance": str(user_main),
                    "total_equivalent": str(total_equiv_before),
                },
                "params": {
                    "requested_amount_kwh": str(amt),
                    "actual_amount_kwh": str(amt),
                },
                "after": {
                    "total_generated_kwh": str(total_kwh),
                    "exchanged_kwh_total": str(new_exchanged_total),
                    "available_kwh": str(new_available),
                    "main_balance": str(new_user_main),
                    "total_equivalent": str(total_equiv_after),
                    "invariant_ok": audit_ok,
                },
            }
            log_id = await _insert_log(
                db,
                provider_tg_id=owner.provider_tg_id,
                global_id=owner.global_id,
                amount=amt,
                direction="credit",
                balance_type="main",
                reason=reason,
                idk=str(idempotency_key),
                meta=audit,
            )

            if BANK_SYSTEM_ENTITY:
                mirror_key = f"mirror:{idempotency_key}"
                mirror_direction = _invert_direction("credit")
                extra_bank = {
                    "mirror_for_global_id": int(owner.global_id),
                    "mirror_of_idk": str(idempotency_key),
                }
                await _insert_log(
                    db,
                    provider_tg_id=None,
                    system_entity=BANK_SYSTEM_ENTITY,
                    amount=d8(amt),
                    direction=mirror_direction,
                    balance_type="main",
                    reason=f"mirror:{reason}",
                    idk=mirror_key,
                    meta=extra_bank,
                )

            await db.commit()
            return TxResult(
                ok=True,
                tg_id=owner.provider_tg_id,
                global_id=owner.global_id,
                amount=amt,
                balance_type="main",
                reason=str(reason),
                idempotency_key=str(idempotency_key),
                created_log_id=int(log_id),
                user__main__balance=new_user_main,
                user_bonus_balance=new_user_bonus,
                bank__main__balance=d8(new_bank_main),
                detail="partial_exchange_success",
                meta=audit,
                bank_deficit_after=deficit,
            )
        except Exception as exc:
            last_exc = exc
            with contextlib.suppress(Exception):
                await db.rollback()
            if _is_idempotency_conflict(exc):
                prev = await _find_log_by_idk(db, str(idempotency_key))
                if prev:
                    conflict_owner = (
                        await resolve_and_lock_financial_write_owner(
                            db,
                            global_id=global_id,
                        )
                    )
                    main, _bonus = await get_user_balances_snapshot(
                        db,
                        global_id=conflict_owner.global_id,
                    )
                    bank_main, _bank_bonus = await _ensure_bank_locked(
                        db
                    )
                    return TxResult(
                        ok=True,
                        tg_id=conflict_owner.provider_tg_id,
                        global_id=conflict_owner.global_id,
                        amount=d8(prev.get("amount", 0)),
                        balance_type="main",
                        reason=reason,
                        idempotency_key=str(idempotency_key),
                        user__main__balance=d8(main),
                        user_bonus_balance=d8(_bonus),
                        bank__main__balance=d8(bank_main),
                        created_log_id=int(prev["id"]),
                        detail="idempotent",
                    )
        await asyncio.sleep(0)

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("partial exchange failed")


async def exchange__all__available_kwh_to_main(
    db: AsyncSession,
    *,
    global_id: int,
    idempotency_key: str,
    reason: str = "exchange_all",
) -> TxResult:
    """EXCHANGE_ALL по SSOT:

    - total_generated_kwh (lifetime) НЕ уменьшается (append-only).
    - exchanged_kwh_total растёт (append-only).
    - available_kwh = total_generated_kwh - exchanged_kwh_total.
    - начисление строго в EFHC MAIN 1:1.
    - операция идемпотентна по idempotency_key.

    Важно: атомарность обеспечивается блокировкой строки пользователя.
    """

    if not idempotency_key or not str(idempotency_key).strip():
        raise ValueError("Idempotency-Key обязателен")

    await _rollback_started_exchange_transaction(
        db,
        ctx="exchange_all_preflight",
    )

    max_tries = 3
    last_exc: Exception | None = None

    for _attempt in range(1, max_tries + 1):
        try:
            owner = await resolve_and_lock_financial_write_owner(
                db,
                global_id=global_id,
            )
            q_user = text(
                "SELECT "
                "COALESCE(main_balance, 0), "
                "COALESCE(bonus_balance, 0), "
                "COALESCE(total_generated_kwh, 0), "
                "COALESCE(exchanged_kwh_total, 0) "
                "FROM efhc_core.users "
                "WHERE global_id = :global_id FOR UPDATE"
            )
            rec = await db.execute(
                q_user,
                {"global_id": int(owner.global_id)},
            )
            row = rec.fetchone()
            if not row:
                raise ValueError("User not found")

            existing = await _find_log_by_idk(db, str(idempotency_key))
            if existing:
                return await _read_through_existing_tx(
                    db,
                    provider_tg_id=owner.provider_tg_id,
                    global_id=owner.global_id,
                    idempotency_key=str(idempotency_key),
                    prev=existing,
                    with_bank_balance=True,
                    expected_direction="credit",
                    expected_balance_type="main",
                    expected_reason=reason,
                )

            user_main = d8(row[0] or 0)
            user_bonus = d8(row[1] or 0)
            total_kwh = d8(row[2] or 0)
            exchanged_total = d8(row[3] or 0)

            if exchanged_total > total_kwh:
                raise ValueError("SSOT violated: exchanged > total")

            available = _available_from_total_exchanged(
                total_kwh,
                exchanged_total,
            )

            bank_main, bank_bonus = await _ensure_bank_locked(db)

            if available <= Decimal("0"):
                total_equiv_before = d8(user_main + available)
                audit = {
                    "audit__schema__version": "v1",
                    "exchange__all__audit": True,
                    "op_type": "EXCHANGE_ALL",
                    "status": "rejected",
                    "reason": "no_available_kwh",
                    "before": {
                        "total_generated_kwh": str(total_kwh),
                        "exchanged_kwh_total": str(exchanged_total),
                        "available_kwh": str(available),
                        "main_balance": str(user_main),
                        "total_equivalent": str(total_equiv_before),
                    },
                    "after": {
                        "total_generated_kwh": str(total_kwh),
                        "exchanged_kwh_total": str(exchanged_total),
                        "available_kwh": str(available),
                        "main_balance": str(user_main),
                        "total_equivalent": str(total_equiv_before),
                        "invariant_ok": True,
                    },
                }
                # FIND-006: отклонённый обмен с нулевой суммой
                # не является финансовым переводом. Журнал разрешает
                # Допустимы только credit/debit. Запись amount=0
                # загрязняет финансовую сверку.
                # Audit payload остаётся в результате, а read-only
                # транзакция закрывается.
                await db.rollback()
                return TxResult(
                    ok=False,
                    tg_id=owner.provider_tg_id,
                    global_id=owner.global_id,
                    amount=Decimal("0"),
                    balance_type="main",
                    reason="exchange_rejected_no_kwh",
                    idempotency_key=str(idempotency_key),
                    created_log_id=None,
                    user__main__balance=user_main,
                    user_bonus_balance=user_bonus,
                    bank__main__balance=d8(bank_main),
                    detail="no_available_kwh",
                    meta=audit,
                )

            new_user_main = d8(user_main + available)
            new_user_bonus = user_bonus

            new_bank_main = d8(bank_main - available)
            deficit = new_bank_main < Decimal("0")

            new_exchanged_total = d8(exchanged_total + available)
            # После обмена всей доступной энергии остаток равен нулю.
            new_available = _available_from_total_exchanged(
                total_kwh,
                new_exchanged_total,
            )

            await _update_user_balances(
                db,
                new_user_main,
                new_user_bonus,
                global_id=owner.global_id,
            )
            await _update_bank_balances(
                db,
                new_main=new_bank_main,
                new_bonus=bank_bonus,
            )

            q_energy = (
                "UPDATE efhc_core.users "
                "SET exchanged_kwh_total = :ex, "
                "    updated_at = now() "
                "WHERE global_id = :global_id"
            )
            await db.execute(
                text(q_energy),
                {
                    "ex": str(d8(new_exchanged_total)),
                    "global_id": int(owner.global_id),
                },
            )

            total_equiv_before = d8(user_main + available)
            total_equiv_after = d8(new_user_main + new_available)

            audit_ok = bool(total_equiv_before == total_equiv_after)
            audit = {
                "audit__schema__version": "v1",
                "exchange__all__audit": True,
                "op_type": "EXCHANGE_ALL",
                "status": "success",
                "rate": "1.00000000",
                "before": {
                    "total_generated_kwh": str(total_kwh),
                    "exchanged_kwh_total": str(exchanged_total),
                    "available_kwh": str(available),
                    "main_balance": str(user_main),
                    "total_equivalent": str(total_equiv_before),
                },
                "params": {
                    "amount_kwh": str(d8(available)),
                    "amount_efhc": str(d8(available)),
                },
                "after": {
                    "total_generated_kwh": str(total_kwh),
                    "exchanged_kwh_total": str(new_exchanged_total),
                    "available_kwh": str(new_available),
                    "main_balance": str(new_user_main),
                    "total_equivalent": str(total_equiv_after),
                    "invariant_ok": bool(audit_ok),
                },
            }
            extra_user: dict[str, Any] = {}
            if deficit:
                extra_user["bank_deficit_mode"] = "true"
            extra_user.update(audit)

            log_id = await _insert_log(
                db,
                provider_tg_id=owner.provider_tg_id,
                global_id=owner.global_id,
                amount=d8(available),
                direction="credit",
                balance_type="main",
                reason=reason,
                idk=str(idempotency_key),
                meta=extra_user,
            )

            if BANK_SYSTEM_ENTITY:
                mirror_key = f"mirror:{idempotency_key}"
                mirror_direction = _invert_direction("credit")
                extra_bank = {
                    "mirror_for_global_id": int(owner.global_id),
                    "mirror_of_idk": str(idempotency_key),
                }
                await _insert_log(
                    db,
                    provider_tg_id=None,
                    system_entity=BANK_SYSTEM_ENTITY,
                    amount=d8(available),
                    direction=mirror_direction,
                    balance_type="main",
                    reason=f"mirror:{reason}",
                    idk=mirror_key,
                    meta=extra_bank,
                )

            await db.commit()
            return TxResult(
                ok=True,
                tg_id=owner.provider_tg_id,
                global_id=owner.global_id,
                amount=d8(available),
                balance_type="main",
                reason=reason,
                idempotency_key=str(idempotency_key),
                user__main__balance=new_user_main,
                user_bonus_balance=new_user_bonus,
                bank__main__balance=None,
                created_log_id=int(log_id),
            )
        except Exception as e:
            last_exc = e
            with contextlib.suppress(Exception):
                await db.rollback()
            if _is_idempotency_conflict(e):
                prev = await _find_log_by_idk(db, str(idempotency_key))
                if prev:
                    conflict_owner = (
                        await resolve_and_lock_financial_write_owner(
                            db,
                            global_id=global_id,
                        )
                    )
                    main, _bonus = await get_user_balances_snapshot(
                        db,
                        global_id=conflict_owner.global_id,
                    )
                    bank_main, _bank_bonus = await _ensure_bank_locked(
                        db
                    )
                    return TxResult(
                        ok=True,
                        tg_id=conflict_owner.provider_tg_id,
                        global_id=conflict_owner.global_id,
                        amount=d8(prev.get("amount", 0)),
                        balance_type="main",
                        reason=reason,
                        idempotency_key=str(idempotency_key),
                        user__main__balance=d8(main),
                        user_bonus_balance=d8(_bonus),
                        bank__main__balance=d8(bank_main),
                        created_log_id=int(prev["id"]),
                        detail="idempotent",
                    )
    raise last_exc or RuntimeError("exchange_all failed")


# ---------------------------------------------------------------------
# Доп. утилита (для роутов/админки)
# ---------------------------------------------------------------------


async def get_user_balances_snapshot(
    db: AsyncSession,
    *,
    global_id: int,
) -> tuple[Decimal, Decimal]:
    """Вернуть balances canonical owner без блокировки."""

    q = (
        "SELECT COALESCE(main_balance, 0), "
        "COALESCE(bonus_balance, 0) "
        "FROM efhc_core.users WHERE global_id = :owner"
    )
    params = {"owner": int(global_id)}
    row = await db.execute(text(q), params)
    rec = row.fetchone()
    if not rec:
        return (Decimal("0"), Decimal("0"))
    return d8(rec[0] or 0), d8(rec[1] or 0)


# =====================================================================
# Пояснения:
# • READ-THROUGH:
#   нет предварительного SELECT по idempotency_key.
# • При UNIQUE(idempotency_key) → rollback
#   и возврат существующей записи.
# • Пользователь никогда не уходит
#   в минус; Банк может.
# • direction (строго):
#   - credit: увеличение баланса global_id
#   - debit:  уменьшение баланса global_id
# • bank<->user фиксируется в reason/meta, например:
#   reason: контекст операции (bank↔user)
# • зеркальная запись банка использует system_entity=BANK_EFHC,
#   global_id/tg_id=NULL, инверсию direction + reason=mirror:...
# =====================================================================


# =====================================================================
# Канонические операции трат/вывода (SSOT денег)
# =====================================================================


async def _find_existing_bonus_then__main__spend_log(
    db: AsyncSession,
    *,
    main_key: str,
    bonus_key: str,
) -> dict[str, Any] | None:
    """Find an existing purchase spend log by either derived key.

    The all-bonus retry guard closed the hole: a purchase may create
    only the ``:bonus`` log when ``main_part == 0``. Both keys are valid
    completion proofs for the same user-facing idempotency key.
    """
    prev_main = await _find_log_by_idk(db, main_key)
    if prev_main:
        return prev_main
    prev_bonus = await _find_log_by_idk(db, bonus_key)
    if prev_bonus:
        return prev_bonus
    return None


async def _read_through_bonus_then__main__spend(
    db: AsyncSession,
    *,
    owner: FinancialWriteOwner,
    amount: Decimal,
    reason: str,
    idempotency_key: str,
    prev: dict[str, Any],
) -> TxResult:
    user_main, user_bonus = await _ensure_user_locked(
        db, global_id=owner.global_id
    )
    bank_main, _bank_bonus = await _ensure_bank_locked(db)
    return TxResult(
        ok=True,
        tg_id=owner.provider_tg_id,
        amount=d8(amount),
        balance_type="mixed",
        reason=reason,
        idempotency_key=str(idempotency_key),
        user__main__balance=d8(user_main),
        user_bonus_balance=d8(user_bonus),
        bank__main__balance=d8(bank_main),
        created_log_id=int(prev["id"]),
        processed_with_deficit=False,
        detail="idempotent",
        global_id=owner.global_id,
    )



async def spend_user_to_bank_bonus_then__main__nocommit(
    db: AsyncSession,
    *,
    global_id: int,
    amount: Decimal,
    reason: str,
    idempotency_key: str,
    meta: dict[str, Any] | None = None,
    before_new_spend: Callable[[], Awaitable[None]] | None = None,
) -> TxResult:
    """Spend BONUS then MAIN by canonical owner without commit."""
    owner = await resolve_and_lock_financial_write_owner(
        db, global_id=global_id
    )
    bonus_key = f"{idempotency_key}:bonus"
    main_key = f"{idempotency_key}:main"
    prev_spend = await _find_existing_bonus_then__main__spend_log(
        db, main_key=main_key, bonus_key=bonus_key
    )
    if prev_spend:
        return await _read_through_bonus_then__main__spend(
            db,
            owner=owner,
            amount=d8(amount),
            reason=reason,
            idempotency_key=str(idempotency_key),
            prev=prev_spend,
        )
    if before_new_spend is not None:
        await before_new_spend()
    user_main, user_bonus = await _ensure_user_locked(
        db, global_id=owner.global_id
    )
    bank_main, bank_bonus = await _ensure_bank_locked(db)
    breakdown = split_bonus_then_main(
        bonus_balance=user_bonus,
        main_balance=user_main,
        amount=d8(amount),
    )
    new_user_bonus = d8(user_bonus - breakdown.bonus_part)
    new_user_main = d8(user_main - breakdown.main_part)
    new_bank_main = d8(bank_main + d8(amount))
    await _update_user_balances(
        db,
        new_user_main,
        new_user_bonus,
        global_id=owner.global_id,
    )
    await _update_bank_balances(
        db, new_main=new_bank_main, new_bonus=bank_bonus
    )
    extra = dict(meta or {})
    extra.update(
        {
            "owner_global_id": str(owner.global_id),
            "spend_bonus_part": str(breakdown.bonus_part),
            "spend__main__part": str(breakdown.main_part),
        }
    )
    created_id: int | None = None
    for part, balance_type, key in (
        (breakdown.bonus_part, "bonus", bonus_key),
        (breakdown.main_part, "main", main_key),
    ):
        if part <= Decimal("0"):
            continue
        created_id = await _insert_log(
            db,
            provider_tg_id=owner.provider_tg_id,
            global_id=owner.global_id,
            amount=part,
            direction="debit",
            balance_type=balance_type,
            reason=reason,
            idk=key,
            meta=extra,
        )
        if BANK_SYSTEM_ENTITY:
            await _insert_log(
                db,
                provider_tg_id=None,
                system_entity=BANK_SYSTEM_ENTITY,
                global_id=None,
                amount=part,
                direction="credit",
                balance_type="main",
                reason=f"mirror:{reason}",
                idk=f"mirror:{key}",
                meta={
                    "mirror_for_global_id": owner.global_id,
                    "mirror_of_idk": key,
                },
            )
    return TxResult(
        ok=True,
        tg_id=owner.provider_tg_id,
        amount=d8(amount),
        balance_type="mixed",
        reason=reason,
        idempotency_key=str(idempotency_key),
        user__main__balance=d8(new_user_main),
        user_bonus_balance=d8(new_user_bonus),
        bank__main__balance=d8(new_bank_main),
        created_log_id=int(created_id or 0),
        processed_with_deficit=bool(new_bank_main < Decimal("0")),
        detail="ok",
        global_id=owner.global_id,
    )



async def spend_user_to_bank_bonus_then_main(
    db: AsyncSession,
    *,
    global_id: int,
    amount: Decimal,
    reason: str,
    idempotency_key: str,
    meta: dict[str, Any] | None = None,
) -> TxResult:
    """Atomic BONUS then MAIN spend by canonical owner."""
    bonus_key = f"{idempotency_key}:bonus"
    main_key = f"{idempotency_key}:main"
    try:
        async with _tx_context(db):
            return await spend_user_to_bank_bonus_then__main__nocommit(
                db,
                global_id=global_id,
                amount=d8(amount),
                reason=reason,
                idempotency_key=str(idempotency_key),
                meta=meta,
            )
    except Exception as exc:
        with contextlib.suppress(Exception):
            await db.rollback()
        if _is_idempotency_conflict(exc):
            async with _tx_context(db):
                owner = await resolve_and_lock_financial_write_owner(
                    db, global_id=global_id
                )
                prev = await _find_existing_bonus_then__main__spend_log(
                    db,
                    main_key=main_key,
                    bonus_key=bonus_key,
                )
                if prev:
                    return await _read_through_bonus_then__main__spend(
                        db,
                        owner=owner,
                        amount=d8(amount),
                        reason=reason,
                        idempotency_key=str(idempotency_key),
                        prev=prev,
                    )
        raise


async def withdraw__main__only_to_bank(
    db: AsyncSession,
    *,
    global_id: int,
    amount: Decimal,
    reason: str,
    idempotency_key: str,
    meta: dict[str, Any] | None = None,
) -> TxResult:
    """Withdraw/hold MAIN by canonical owner."""
    return await debit_user_to_bank(
        db,
        global_id=global_id,
        amount=amount,
        reason=reason,
        idempotency_key=idempotency_key,
        meta=meta,
    )
