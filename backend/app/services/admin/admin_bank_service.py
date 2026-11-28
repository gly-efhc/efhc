# backend/app/services/admin/admin_bank_service.py
# ======================================================================
# EFHC Bot — Банк EFHC: начальная эмиссия, ручные операции
# Банк↔Пользователь,
# логирование и безопасные откаты через компенсирующие транзакции.
# ----------------------------------------------------------------------
# Назначение модуля:
# • Централизованный сервис для операций с Банком EFHC в админ-панели.
# • Строгий канон: НЕТ P2P-переводов между пользователями, только:
#   - Банк → Пользователь
#   - Пользователь → Банк
# • Начальная эмиссия Банка: 5 000 000 EFHC (идемпотентная
# инициализация).
# • Ручные корректировки: только main банка.
# • Полная идемпотентность: mint/burn, ручные корректировки, откаты.
# • Логи: bank_balance, efhc_transfers_log, admin_logs.
#
# ВАЖНО (канон):
# 1) Начальный баланс Банка — 5 000 000 EFHC.
#    Физический seed: 0001_init.py → efhc_core.bank_balance;
#    runtime fallback: BANK_INITIAL_TOTAL.
# 2) P2P между пользователями запрещены. Корректировка: userA → Банк →
# userB.
# 3) Ручные операции Банк↔Пользователь только через
# transactions_service.*
#    (credit/debit, включая бонусный баланс). Никаких прямых UPDATE
#    балансов.
# 4) Обычные Admin money operations требуют idempotency_key клиента.
#    Reversal использует отдельный deterministic business key от source id;
#    request Idempotency-Key сохраняется как audit attribute.
# 5) Банк хранит только main (bonus в банке отсутствует).
# ======================================================================

from __future__ import annotations

import json
from decimal import ROUND_DOWN, Decimal
from typing import Any, Literal, cast

from app.core.config_core import get_settings
from app.core.logging_core import get_logger
from app.core.sql_aliases_core import canon_schema
from app.core.utils_core import (
    format_decimal_str,
    quantize_decimal,
)
from app.identity.api_contract import PydanticGlobalId
from app.services.transactions_service import (
    IdempotencyPayloadConflictError,
    burn_bank_efhc_nocommit,
    credit_user_bonus_from_bank_nocommit,
    credit_user_from_bank_nocommit,
    debit_user_bonus_to_bank_nocommit,
    debit_user_to_bank_nocommit,
    get_bank_balance,
    mint_bank_efhc_nocommit,
)
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.engine import Result
from sqlalchemy.ext.asyncio import AsyncSession

from .admin_logging import AdminLogger
from .admin_notifications import AdminNotifier
from .admin_rbac import RBAC, AdminRole, AdminUser

logger = get_logger(__name__)
S = get_settings()

SCHEMA_CORE: str = canon_schema(
    getattr(S, "DB_SCHEMA_CORE", "efhc_core") or "efhc_core",
)

# Логическое имя центрального банка: BANK_EFHC.

BANK_EFHC = "BANK_EFHC"

# Начальная эмиссия Банка (канон: 5 000 000 EFHC).
# Физический seed живёт в 0001_init.py → efhc_core.bank_balance;
# это runtime fallback для service-owned initialization, не второй SSOT.
BANK_INITIAL_TOTAL: Decimal = Decimal(
    str(getattr(S, "BANK_INITIAL_TOTAL_EFHC", "5000000") or "5000000")
)

# Универсальная точность EFHC (по канону 8 знаков)
EFHC_DECIMALS: int = int(getattr(S, "EFHC_DECIMALS", 8) or 8)
_Q = Decimal(1).scaleb(-EFHC_DECIMALS)


def d8(x: Any) -> Decimal:
    """Округляет вниз до EFHC_DECIMALS знаков (канон EFHC)."""
    return Decimal(str(x)).quantize(_Q, rounding=ROUND_DOWN)


# ----------------------------------------------------------------------
# Истина банка: efhc_core.bank_balance.
# Чтение/инициализация идут через transactions_service,
# чтобы admin layer не стал вторым money-write источником.
# ----------------------------------------------------------------------




# ======================================================================
# DTO / запросы / ответы для админки
# ======================================================================


class MintBurnRequest(BaseModel):
    """Запрос на mint/burn EFHC в банке."""

    amount: Decimal = Field(..., gt=Decimal("0"))
    reason: str | None = None
    idempotency_key: str = Field(..., min_length=1, max_length=128)

    @field_validator("amount", mode="before")
    def _v_amount(cls, v: Any) -> Decimal:
        """Валидатор: amount → Decimal(d8)."""
        return cast(Decimal, quantize_decimal(v, EFHC_DECIMALS, "DOWN"))

    @field_validator("idempotency_key")
    def _v_idem(cls, v: str) -> str:
        """Валидатор: idempotency_key (strip, non-empty)."""
        v = (v or "").strip()
        if not v:
            raise ValueError("idempotency_key обязателен")
        return v


class BankUserTransferRequest(BaseModel):
    """Ручная операция Банк↔Пользователь (админ-корректировка)."""

    global_id: PydanticGlobalId
    amount: Decimal = Field(..., gt=Decimal("0"))
    direction: Literal["credit", "debit"]
    balance_type: Literal["REGULAR", "BONUS"]
    reason: str | None = None
    idempotency_key: str = Field(..., min_length=1, max_length=128)

    @field_validator("amount", mode="before")
    def _v_amount(cls, v: Any) -> Decimal:
        """Валидатор: amount → Decimal(d8)."""
        return cast(Decimal, quantize_decimal(v, EFHC_DECIMALS, "DOWN"))

    @field_validator("idempotency_key")
    def _v_idem(cls, v: str) -> str:
        """Валидатор: idempotency_key (strip, non-empty)."""
        v = (v or "").strip()
        if not v:
            raise ValueError("idempotency_key обязателен")
        return v


class BankBalance(BaseModel):
    """Сводный баланс логического банка EFHC."""

    balance: str
    bank_key: str = BANK_EFHC


class BankTransferLogEntry(BaseModel):
    """Каноничный ledger Банк↔аккаунт по ``global_id``."""

    id: int
    from_global_id: str | None
    to_global_id: str | None
    amount: str
    reason: str
    created_at: str


# ======================================================================
# Сервис Банка EFHC
# ======================================================================


class BankService:
    """Банк-сервис админки (без P2P)."""

    # ------------------------------------------------------------------
    # Инициализация Банка (начальный баланс 5 000 000 EFHC)
    # ------------------------------------------------------------------
    @staticmethod
    async def ensure_initial_balance(
        db: AsyncSession,
    ) -> dict[str, Any]:
        """Идемпотентно инициализирует efhc_core.bank_balance."""
        before = await get_bank_balance(
            db,
            initial_balance=BANK_INITIAL_TOTAL,
        )
        after = await get_bank_balance(
            db,
            initial_balance=BANK_INITIAL_TOTAL,
        )
        return {
            "initialized": before == Decimal("0"),
            "balance_before": format_decimal_str(before, EFHC_DECIMALS),
            "balance_after": format_decimal_str(after, EFHC_DECIMALS),
        }

    # ------------------------------------------------------------------
    # Текущий баланс Банка
    # ------------------------------------------------------------------
    @staticmethod
    async def get_bank_balance(db: AsyncSession) -> BankBalance:
        """Возвращает текущий баланс банка из efhc_core.bank_balance."""
        bal = await get_bank_balance(
            db,
            initial_balance=BANK_INITIAL_TOTAL,
        )
        return BankBalance(
            balance=format_decimal_str(d8(bal), EFHC_DECIMALS),
        )

    # ------------------------------------------------------------------
    # Минт/бёрн EFHC (только Банк)
    # ------------------------------------------------------------------
    @staticmethod
    async def mint_efhc(
        db: AsyncSession,
        req: MintBurnRequest,
        admin: AdminUser,
    ) -> dict[str, Any]:
        """
        Минт EFHC в Банк через существующие SSOT-таблицы.

        F-001 linkage repair:
          • баланс банка: efhc_core.bank_balance;
          • canonical ledger/idempotency: efhc_core.efhc_transfers_log;
          • отдельная таблица mint/burn не создаётся и не читается;
          • действие администратора пишется в admin_action_log.

        RBAC:
          • Только SUPERADMIN.
        """
        RBAC.require_role(admin, AdminRole.SUPERADMIN)

        amt = d8(req.amount)
        message = (
            f"Минт {format_decimal_str(amt, EFHC_DECIMALS)} EFHC"
        )
        notification_id: int | None = None
        try:
            result = await mint_bank_efhc_nocommit(
                db,
                amount=amt,
                reason=req.reason or "",
                idempotency_key=req.idempotency_key,
                meta={
                    "admin_id": int(admin.id),
                    "admin_global_id": int(admin.global_id),
                    "operation": "BANK_MINT",
                    "cycle": "bank_ssot",
                },
            )
            await AdminLogger.write(
                db,
                actor_global_id=admin.global_id,
                admin_id=admin.id,
                action="BANK_MINT",
                entity="bank",
                entity_id=None,
                details=(
                    f"amount = {format_decimal_str(amt, EFHC_DECIMALS)}; "
                    f"ik = {req.idempotency_key}; "
                    f"ledger = efhc_transfers_log; "
                    f"reused = {result.detail == 'idempotent'}"
                ),
                required=True,
            )
            if result.detail != "idempotent":
                notification_id = await AdminNotifier.notify_generic(
                    db,
                    event="BANK_MINT",
                    message=message,
                    payload_json=(
                        f'{{"amount":"'
                        f'{format_decimal_str(amt, EFHC_DECIMALS)}",'
                        f'"admin_id":{admin.id}}}'
                    ),
                    send_telegram=False,
                )
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        if notification_id is not None:
            await AdminNotifier.send_telegram_after_commit(
                notification_id=notification_id,
                event="BANK_MINT",
                message=message,
            )

        return {
            "ok": True,
            "minted": format_decimal_str(amt, EFHC_DECIMALS),
            "idempotency_key": req.idempotency_key,
            "current_balance": format_decimal_str(
                result.bank__main__balance,
                EFHC_DECIMALS,
            ),
            "reused": result.detail == "idempotent",
            "ledger": "efhc_transfers_log",
        }

    @staticmethod
    async def burn_efhc(
        db: AsyncSession,
        req: MintBurnRequest,
        admin: AdminUser,
    ) -> dict[str, Any]:
        """
        Бёрн EFHC из Банка через существующие SSOT-таблицы.

        F-001 linkage repair:
          • баланс банка: efhc_core.bank_balance;
          • canonical ledger/idempotency: efhc_core.efhc_transfers_log;
          • отдельная таблица mint/burn не создаётся и не читается;
          • действие администратора пишется в admin_action_log.

        RBAC:
          • Только SUPERADMIN.
        """
        RBAC.require_role(admin, AdminRole.SUPERADMIN)

        amt = d8(req.amount)
        message = (
            f"Сжигание {format_decimal_str(amt, EFHC_DECIMALS)} EFHC"
        )
        notification_id: int | None = None
        try:
            result = await burn_bank_efhc_nocommit(
                db,
                amount=amt,
                reason=req.reason or "",
                idempotency_key=req.idempotency_key,
                meta={
                    "admin_id": int(admin.id),
                    "admin_global_id": int(admin.global_id),
                    "operation": "BANK_BURN",
                    "cycle": "bank_ssot",
                },
            )
            await AdminLogger.write(
                db,
                actor_global_id=admin.global_id,
                admin_id=admin.id,
                action="BANK_BURN",
                entity="bank",
                entity_id=None,
                details=(
                    f"amount = {format_decimal_str(amt, EFHC_DECIMALS)}; "
                    f"ik = {req.idempotency_key}; "
                    f"ledger = efhc_transfers_log; "
                    f"reused = {result.detail == 'idempotent'}"
                ),
                required=True,
            )
            if result.detail != "idempotent":
                notification_id = await AdminNotifier.notify_generic(
                    db,
                    event="BANK_BURN",
                    message=message,
                    payload_json=(
                        f'{{"amount":"'
                        f'{format_decimal_str(amt, EFHC_DECIMALS)}",'
                        f'"admin_id":{admin.id}}}'
                    ),
                    send_telegram=False,
                )
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        if notification_id is not None:
            await AdminNotifier.send_telegram_after_commit(
                notification_id=notification_id,
                event="BANK_BURN",
                message=message,
            )

        return {
            "ok": True,
            "burned": format_decimal_str(amt, EFHC_DECIMALS),
            "idempotency_key": req.idempotency_key,
            "current_balance": format_decimal_str(
                result.bank__main__balance,
                EFHC_DECIMALS,
            ),
            "reused": result.detail == "idempotent",
            "ledger": "efhc_transfers_log",
        }

    # ------------------------------------------------------------------
    # Ручные операции Банк↔Пользователь (только через
    # transactions_service)
    # ------------------------------------------------------------------
    @staticmethod
    async def manual_bank_user_transfer(
        db: AsyncSession,
        req: BankUserTransferRequest,
        admin: AdminUser,
        *,
        _audit_action: str | None = None,
        _audit_details_suffix: str | None = None,
        _meta_extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Выполнить ручную корректировку Банк↔Пользователь атомарно.

        Денежная проводка, обязательный ``admin_action_log`` и outbox
        уведомления записываются одной root transaction. Сетевой Telegram
        delivery выполняется только после успешного commit.
        """
        RBAC.require_role(admin, AdminRole.MODERATOR)

        amt = d8(req.amount)
        if amt <= 0:
            raise ValueError("Сумма должна быть больше нуля")

        base_reason = req.reason or "ADMIN_MANUAL"
        meta = {
            "admin_id": admin.id,
            "admin_global_id": int(admin.global_id),
            "admin_role": admin.role,
            "admin_reason": base_reason,
            "source": "admin_manual_bank_transfer",
        }
        if _meta_extra:
            meta.update(dict(_meta_extra))
        global_id = int(req.global_id)
        notification_id: int | None = None
        label = "Кредит" if req.direction == "credit" else "Дебет"
        message = (
            f"{label} {format_decimal_str(amt, EFHC_DECIMALS)} EFHC "
            f"({req.balance_type}) пользователю {req.global_id}"
        )

        try:
            if req.direction == "credit":
                if req.balance_type == "REGULAR":
                    reason = "admin_manual_regular_credit"
                    result = await credit_user_from_bank_nocommit(
                        db,
                        global_id=global_id,
                        amount=amt,
                        reason=reason,
                        idempotency_key=req.idempotency_key,
                        meta=meta,
                    )
                    action = "CREDIT_REGULAR"
                else:
                    reason = "admin_manual_bonus_credit"
                    result = await credit_user_bonus_from_bank_nocommit(
                        db,
                        global_id=global_id,
                        amount=amt,
                        reason=reason,
                        idempotency_key=req.idempotency_key,
                        meta=meta,
                    )
                    action = "CREDIT_BONUS"
            else:
                if req.balance_type == "REGULAR":
                    reason = "admin_manual_regular_debit"
                    result = await debit_user_to_bank_nocommit(
                        db,
                        global_id=global_id,
                        amount=amt,
                        reason=reason,
                        idempotency_key=req.idempotency_key,
                        meta=meta,
                    )
                    action = "DEBIT_REGULAR"
                else:
                    reason = "admin_manual_bonus_debit"
                    result = await debit_user_bonus_to_bank_nocommit(
                        db,
                        global_id=global_id,
                        amount=amt,
                        reason=reason,
                        idempotency_key=req.idempotency_key,
                        meta=meta,
                    )
                    action = "DEBIT_BONUS"

            reused = str(result.detail).startswith("idempotent")
            audit_action = _audit_action or action
            details_suffix = (
                f"; {_audit_details_suffix}"
                if _audit_details_suffix
                else ""
            )
            await AdminLogger.write(
                db,
                actor_global_id=admin.global_id,
                admin_id=admin.id,
                action=audit_action,
                entity="bank_user_tx",
                entity_id=global_id,
                details=(
                    f"amount = {format_decimal_str(amt, EFHC_DECIMALS)}; "
                    f"ik = {req.idempotency_key}; "
                    f"balance_type = {req.balance_type}; "
                    f"reused = {reused}{details_suffix}"
                ),
                required=True,
            )

            if not reused:
                payload_json = (
                    f'{{"global_id":"{req.global_id}",'
                    f'"amount":"{format_decimal_str(amt, EFHC_DECIMALS)}",'
                    f'"direction":"{req.direction}",'
                    f'"balance_type":"{req.balance_type}",'
                    f'"admin_id":{admin.id},'
                    f'"ik":"{req.idempotency_key}"}}'
                )
                notification_id = await AdminNotifier.notify_generic(
                    db,
                    event=audit_action,
                    message=message,
                    payload_json=payload_json,
                    send_telegram=False,
                )

            await db.commit()
        except IdempotencyPayloadConflictError:
            await db.rollback()
            raise
        except Exception as exc:
            await db.rollback()
            logger.warning(
                "BankService.manual_bank_user_transfer failed "
                "(user=%s, dir=%s, bal=%s): %s",
                req.global_id,
                req.direction,
                req.balance_type,
                exc,
            )
            raise ValueError(
                f"Не удалось выполнить операцию: {type(exc).__name__}: {exc}"
            ) from exc

        if notification_id is not None:
            await AdminNotifier.send_telegram_after_commit(
                notification_id=notification_id,
                event=audit_action,
                message=message,
            )

        return {
            "ok": True,
            "global_id": f"{global_id:010d}",
            "amount": format_decimal_str(result.amount, EFHC_DECIMALS),
            "direction": req.direction,
            "balance_type": req.balance_type,
            "idempotency_key": req.idempotency_key,
            "reused": reused,
            "transfer_log_id": (
                int(result.created_log_id)
                if result.created_log_id is not None
                else None
            ),
            "user__main__balance": format_decimal_str(
                result.user__main__balance, EFHC_DECIMALS
            ),
            "user_bonus_balance": format_decimal_str(
                result.user_bonus_balance, EFHC_DECIMALS
            ),
            "bank__main__balance": (
                format_decimal_str(result.bank__main__balance, EFHC_DECIMALS)
                if result.bank__main__balance is not None
                else None
            ),
        }

    # ------------------------------------------------------------------
    # История операций Банк↔Пользователь
    # ------------------------------------------------------------------
    @staticmethod
    async def list_bank_user_transfers(
        db: AsyncSession,
        *,
        global_id: int | None = None,
        limit: int = 100,
        offset: int = 0,
        sort_desc: bool = True,
    ) -> list[BankTransferLogEntry]:
        """Вернуть canonical ledger Банк↔аккаунт.

        Пользовательская сторона определяется по ``global_id``;
        банковская сторона — только по ``system_entity=BANK_EFHC``.
        """

        limit = max(1, min(limit, 500))
        offset = max(0, offset)
        where = [
            "(global_id IS NOT NULL OR system_entity = :bank_entity)"
        ]
        params: dict[str, Any] = {
            "bank_entity": BANK_EFHC,
            "limit": limit,
            "offset": offset,
        }
        if global_id is not None:
            canonical = int(global_id)
            where.append(
                "(global_id = :global_id "
                "OR meta LIKE :global_marker)"
            )
            params["global_id"] = canonical
            params["global_marker"] = (
                f'%"mirror_for_global_id": {canonical}%'
            )

        order = "DESC" if sort_desc else "ASC"
        where_clause = " AND ".join(where)
        sql_tpl = """
            SELECT id, tg_id, global_id, system_entity, amount, direction, reason,
                   created_at, meta
              FROM efhc_core.efhc_transfers_log
             WHERE {where_clause}
             ORDER BY id {order}
             LIMIT :limit OFFSET :offset
            """
        sql = text(
            sql_tpl.replace("efhc_core", SCHEMA_CORE)
            .replace("{where_clause}", where_clause)
            .replace("{order}", order)
        )
        result: Result = await db.execute(sql, params)
        out: list[BankTransferLogEntry] = []
        for row in result.fetchall():
            meta_raw = getattr(row, "meta", None)
            meta: dict[str, Any] = {}
            if meta_raw:
                try:
                    parsed = json.loads(str(meta_raw))
                    if isinstance(parsed, dict):
                        meta = parsed
                except Exception:
                    meta = {}

            row_global = (
                int(row.global_id)
                if getattr(row, "global_id", None) is not None
                else None
            )
            mirror_global = meta.get("mirror_for_global_id")
            mirror_global_id = (
                int(mirror_global)
                if mirror_global is not None
                else None
            )
            account_global_id = row_global or mirror_global_id
            account_external = (
                f"{account_global_id:010d}"
                if account_global_id is not None
                else None
            )
            direction = str(row.direction)
            bank_row = (
                getattr(row, "system_entity", None) == BANK_EFHC
            )
            if bank_row:
                from_owner = (
                    BANK_EFHC
                    if direction == "debit"
                    else account_external
                )
                to_owner = (
                    account_external
                    if direction == "debit"
                    else BANK_EFHC
                )
            else:
                from_owner = (
                    BANK_EFHC
                    if direction == "credit"
                    else account_external
                )
                to_owner = (
                    account_external
                    if direction == "credit"
                    else BANK_EFHC
                )

            out.append(
                BankTransferLogEntry(
                    id=int(row.id),
                    from_global_id=from_owner,
                    to_global_id=to_owner,
                    amount=str(row.amount),
                    reason=str(row.reason),
                    created_at=(
                        row.created_at.isoformat()
                        if hasattr(row.created_at, "isoformat")
                        else str(row.created_at)
                    ),
                )
            )
        return out

    # ------------------------------------------------------------------
    # «Откат» через компенсирующую транзакцию (мягкий rollback)
    # ------------------------------------------------------------------
    @staticmethod
    async def rollback_bank_user_tx(
        db: AsyncSession,
        *,
        transfer_log_id: int,
        balance_type: Literal["REGULAR", "BONUS"] | None = None,
        idempotency_key: str,
        admin: AdminUser,
    ) -> dict[str, Any]:
        """Создать ровно одну compensating operation для Admin transfer.

        Business identity reversal — исходный ``transfer_log_id``. HTTP
        ``Idempotency-Key`` остаётся request-level атрибутом аудита и не
        может разрешить второй reversal той же исходной проводки.
        """
        RBAC.require_role(admin, AdminRole.MODERATOR)
        request_idk = str(idempotency_key or "").strip()
        if not request_idk:
            raise ValueError("IDEMPOTENCY_REQUIRED")

        result: Result = await db.execute(
            text(
                """
                SELECT id, global_id, system_entity, amount, direction,
                       balance_type, reason, idempotency_key, meta
                  FROM efhc_core.efhc_transfers_log
                 WHERE id = :txid
                 FOR UPDATE
                """
            ),
            {"txid": int(transfer_log_id)},
        )
        row = result.fetchone()
        if not row:
            raise ValueError("ROLLBACK_ORIGINAL_NOT_FOUND")

        if (
            getattr(row, "system_entity", None) is not None
            or getattr(row, "global_id", None) is None
        ):
            raise ValueError("ROLLBACK_SOURCE_MUST_BE_USER_SIDE_ADMIN_TRANSFER")

        original_meta: dict[str, Any] = {}
        raw_meta = getattr(row, "meta", None)
        if raw_meta:
            try:
                parsed = json.loads(str(raw_meta))
                if isinstance(parsed, dict):
                    original_meta = parsed
            except Exception:
                original_meta = {}

        allowed_reasons = {
            "admin_manual_regular_credit",
            "admin_manual_bonus_credit",
            "admin_manual_regular_debit",
            "admin_manual_bonus_debit",
        }
        original_reason = str(row.reason or "")
        if (
            original_reason not in allowed_reasons
            or str(original_meta.get("source") or "")
            != "admin_manual_bank_transfer"
            or original_meta.get("rollback_of_transfer_log_id") is not None
            or str(original_meta.get("admin_reason") or "").startswith(
                "ROLLBACK:"
            )
        ):
            raise ValueError("ROLLBACK_SOURCE_MUST_BE_ORIGINAL_ADMIN_TRANSFER")

        owner_global_id = int(row.global_id)
        direction = str(row.direction)
        if direction not in {"credit", "debit"}:
            raise ValueError("ROLLBACK_SOURCE_DIRECTION_INVALID")
        amount = d8(row.amount)
        original_balance_type = str(row.balance_type or "").lower()
        if original_balance_type == "main":
            canonical_balance_type: Literal["REGULAR", "BONUS"] = "REGULAR"
        elif original_balance_type == "bonus":
            canonical_balance_type = "BONUS"
        else:
            raise ValueError("ROLLBACK_SOURCE_BALANCE_TYPE_INVALID")
        if balance_type is not None and balance_type != canonical_balance_type:
            raise ValueError("ROLLBACK_BALANCE_TYPE_CONFLICT")

        reverse_direction: Literal["credit", "debit"] = (
            "debit" if direction == "credit" else "credit"
        )
        compensation_idk = f"admin_bank_rollback:{int(transfer_log_id)}"

        existing_result: Result = await db.execute(
            text(
                """
                SELECT id, amount, direction, balance_type, idempotency_key, meta
                  FROM efhc_core.efhc_transfers_log
                 WHERE global_id = :global_id
                   AND system_entity IS NULL
                   AND (
                       idempotency_key = :compensation_idk
                       OR meta LIKE :rollback_marker
                       OR meta LIKE :legacy_marker
                   )
                 ORDER BY id ASC
                 LIMIT 1
                """
            ),
            {
                "global_id": owner_global_id,
                "compensation_idk": compensation_idk,
                "rollback_marker": (
                    f'%"rollback_of_transfer_log_id": {int(transfer_log_id)}%'
                ),
                "legacy_marker": (
                    f'%"admin_reason": "ROLLBACK:{int(transfer_log_id)}|%'
                ),
            },
        )
        existing = existing_result.fetchone()
        if existing is not None:
            existing_meta: dict[str, Any] = {}
            if getattr(existing, "meta", None):
                try:
                    parsed = json.loads(str(existing.meta))
                    if isinstance(parsed, dict):
                        existing_meta = parsed
                except Exception:
                    existing_meta = {}
            linked = (
                existing_meta.get("rollback_of_transfer_log_id")
                == int(transfer_log_id)
                or str(existing_meta.get("admin_reason") or "").startswith(
                    f"ROLLBACK:{int(transfer_log_id)}|"
                )
            )
            payload_matches = (
                linked
                and d8(existing.amount) == amount
                and str(existing.direction) == reverse_direction
                and str(existing.balance_type).lower() == original_balance_type
            )
            if not payload_matches:
                raise IdempotencyPayloadConflictError(
                    "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD"
                )
            await AdminLogger.write(
                db,
                actor_global_id=admin.global_id,
                admin_id=admin.id,
                action="BANK_ROLLBACK",
                entity="bank_user_tx",
                entity_id=owner_global_id,
                details=(
                    f"rollback_transfer_log_id = {int(transfer_log_id)}; "
                    f"request_ik = {request_idk}; reused = True"
                ),
                required=True,
            )
            await db.commit()
            return {
                "ok": True,
                "rollback_of": int(transfer_log_id),
                "balance_type": canonical_balance_type,
                "request_idempotency_key": request_idk,
                "compensation_idempotency_key": str(
                    existing.idempotency_key
                ),
                "compensation_log_id": int(existing.id),
                "reused": True,
            }

        rollback_req = BankUserTransferRequest(
            global_id=f"{owner_global_id:010d}",
            amount=amount,
            direction=reverse_direction,
            balance_type=canonical_balance_type,
            reason=f"ROLLBACK:{int(transfer_log_id)}",
            idempotency_key=compensation_idk,
        )
        compensation = await BankService.manual_bank_user_transfer(
            db,
            req=rollback_req,
            admin=admin,
            _audit_action="BANK_ROLLBACK",
            _audit_details_suffix=(
                f"rollback_transfer_log_id = {int(transfer_log_id)}; "
                f"request_ik = {request_idk}; "
                f"original_balance_type = {canonical_balance_type}"
            ),
            _meta_extra={
                "source": "admin_bank_rollback",
                "rollback_of_transfer_log_id": int(transfer_log_id),
                "rollback_request_idempotency_key": request_idk,
                "original_idempotency_key": str(row.idempotency_key),
            },
        )
        compensation_log_id = compensation.get("transfer_log_id")
        return {
            "ok": True,
            "rollback_of": int(transfer_log_id),
            "balance_type": canonical_balance_type,
            "request_idempotency_key": request_idk,
            "compensation_idempotency_key": compensation_idk,
            "compensation_log_id": (
                int(compensation_log_id)
                if compensation_log_id is not None
                else None
            ),
            "reused": bool(compensation.get("reused", False)),
            "compensation": compensation,
        }



__all__ = [
    "MintBurnRequest",
    "BankUserTransferRequest",
    "BankBalance",
    "BankTransferLogEntry",
    "BankService",
]

