"""EFHC Bot: вывод EFHCm.

Заявки на вывод EFHCm (только EFHC, не TON).
Создание заявки: атомарный холд через debit_user_to_bank_nocommit().
Админ: approve/reject.
При отказе/отмене — рефанд.
Идемпотентность по idempotency_key.
Движение средств: transactions_service.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

from app.core.config_core import get_settings
from app.core.logging_core import get_logger
from app.core.sql_aliases_core import canon_schema
from app.deps import d8
from app.identity.financial_write_owner import (
    resolve_and_lock_financial_write_owner,
)
from app.lib.time import utcnow
from app.models.admin_models import AdminWhitelist, IdempotencyKey
from app.services.admin.admin_logging import AdminLogger
from app.services.common_errors import EfhcConflictError
from app.services.financial_retention_foundation_service import (
    FINANCIAL_EXECUTION_DAYS,
    financial_execution_record_eligible,
)
from app.services.transactions_service import (
    _tx_context,
    append_transfer_meta,
    credit_user_from_bank_nocommit,
    debit_user_to_bank_nocommit,
)
from app.standards.finance_rules import quantize_external_efhc_d2
from app.utils.cursor_codec import decode_cursor, encode_cursor
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)
settings = get_settings()
SCHEMA_ADMIN = canon_schema(
    getattr(settings, "DB_SCHEMA_ADMIN", "efhc_admin") or "efhc_admin",
)

# Минимальная сумма вывода (канон): 10 EFHCm
MIN_WITHDRAW_EFHC = Decimal("10")


# -------------------------------------------------------------------
# Статусы заявок
# -------------------------------------------------------------------
WITHDRAW_REQ_PENDING = "PENDING"
# Создана; сумма в холде.
# Или будет в холде.

WITHDRAW_REQ_APPROVED = "APPROVED"
# Legacy статус. Канон SSOT: финализация = PAID.

WITHDRAW_REQ_REJECTED = "REJECTED"
# Админ отклонил; рефанд выполнен.

WITHDRAW_REQ_CANCELED = "CANCELED"
# Пользователь отменил.
# Рефанд выполнен.

WITHDRAW_REQ_PAID = "PAID"
# Выплата завершена админом (внешне).
# Холд остаётся в Банке.


# -------------------------------------------------------------------
# DTO
# -------------------------------------------------------------------
@dataclass(frozen=True)
class WithdrawRequestDTO:
    id: int
    tg_id: int | None
    amount: Decimal
    status: str
    idempotency_key: str
    hold_done: bool
    refund_done: bool
    payout_ref: str | None
    created_at: str
    updated_at: str
    global_id: int | None = None

    def __getitem__(self, key: str):
        return getattr(self, key)


@dataclass
class WithdrawPageDTO:
    items: list[WithdrawRequestDTO]
    next_cursor: str | None


# -------------------------------------------------------------------
# Помощники
# -------------------------------------------------------------------


def _now_utc() -> datetime:
    """Возвращает текущее время UTC."""
    return cast(datetime, utcnow())


def _require_withdraw_execution_window(created_at: datetime) -> None:
    """Запретить payout старой заявки на границе >=180 суток."""

    if not financial_execution_record_eligible(
        created_at,
        now=utcnow(),
    ):
        raise ValueError("WITHDRAW_EXECUTION_WINDOW_EXPIRED")


def _row_to_dto(row) -> WithdrawRequestDTO:
    """Convert a SQL row; global_id is optional for legacy queries."""
    return WithdrawRequestDTO(
        id=int(row[0]),
        tg_id=(int(row[1]) if row[1] is not None else None),
        amount=d8(row[2]),
        status=str(row[3]),
        idempotency_key=str(row[4]),
        hold_done=bool(row[5]),
        refund_done=bool(row[6]),
        payout_ref=(str(row[7]) if row[7] else None),
        created_at=row[8].astimezone(UTC).isoformat(),
        updated_at=row[9].astimezone(UTC).isoformat(),
        global_id=(
            int(row[10])
            if len(row) > 10 and row[10] is not None
            else None
        ),
    )



async def _fetch_withdraw_request(
    db: AsyncSession,
    *,
    request_id: int,
    global_id: int | None = None,
) -> WithdrawRequestDTO:
    """Fetch request, optionally enforcing canonical owner."""
    if global_id is None:
        query = text(
            """
            SELECT id, tg_id, amount, status, idempotency_key,
                   hold_done, refund_done, payout_ref,
                   created_at, updated_at, global_id
              FROM efhc_core.withdraw_requests
             WHERE id = :request_id
            """
        )
        params: dict[str, Any] = {"request_id": int(request_id)}
    else:
        query = text(
            """
            SELECT id, tg_id, amount, status, idempotency_key,
                   hold_done, refund_done, payout_ref,
                   created_at, updated_at, global_id
              FROM efhc_core.withdraw_requests
             WHERE id = :request_id
               AND global_id = :global_id
            """
        )
        params = {
            "request_id": int(request_id),
            "global_id": int(global_id),
        }
    row = (await db.execute(query, params)).fetchone()
    if not row:
        raise ValueError("withdraw request not found")
    return _row_to_dto(row)


async def _ensure_admin_whitelisted(
    db: AsyncSession,
    *,
    actor_global_id: int,
) -> int:
    """Дубль-страховка по canonical actor owner.

    Возвращает локальный PK whitelist для audit/idempotency metadata.
    """
    gid = int(actor_global_id)
    q = select(AdminWhitelist.id).where(
        AdminWhitelist.global_id == gid,
        AdminWhitelist.is_active.is_(True),
    )
    r = await db.execute(q)
    admin_id = r.scalar_one_or_none()
    if admin_id is None:
        raise ValueError("admin global_id not whitelisted")
    return int(admin_id)


def _make_withdraw_cursor(ts: datetime, rid: int) -> str:
    """Формирует next_cursor."""
    payload = {
        "ts": ts.astimezone(UTC).isoformat(),
        "id": int(rid),
    }
    return str(encode_cursor(payload))


def _parse_withdraw_cursor(
    cursor: str | None,
) -> tuple[datetime | None, int | None]:
    """Парсит cursor в (created_at, id) для keyset.

    При пустом cursor возвращает None.
    """
    if not cursor:
        return None, None
    try:
        payload = decode_cursor(cursor)
        ts_raw = payload.get("ts")
        rid = payload.get("id")
        ts = None
        if ts_raw:
            raw_ts = str(ts_raw).replace("Z", " + 00:00")
            ts = datetime.fromisoformat(raw_ts)
            ts = ts.astimezone(UTC)
        return ts, (int(rid) if rid is not None else None)
    except Exception:
        return None, None


# ======================================================================
# =======
# Создание заявки с мгновенным холдом
#
# Таблица withdraw_requests.
# Ожидается миграцией.
# id BIGSERIAL PK,
# tg_id BIGINT NULL, — внешний идентификатор Telegram
# global_id BIGINT NOT NULL, — канонический владелец
# amount NUMERIC(30,8) NOT NULL,
# status TEXT NOT NULL,
# idempotency_key TEXT NOT NULL UNIQUE,
# hold_done BOOLEAN NOT NULL DEFAULT FALSE, — холд выполнен
# refund_done BOOLEAN NOT NULL DEFAULT FALSE, — возврат
# payout_ref TEXT NULL, — ссылка выплаты
# created_at timestamptz NOT NULL DEFAULT now(), — создание
# updated_at timestamptz NOT NULL DEFAULT now() — изменение
# Поля выше перечислены как техническая схема таблицы.
# ======================================================================
# =======


async def request_withdraw(
    db: AsyncSession,
    *,
    global_id: int,
    amount: Decimal,
    idempotency_key: str,
    external_address: str,
) -> WithdrawRequestDTO:
    """HEAL-0024 canonical withdraw boundary.

    Request creation and MAIN hold are one atomic operation.
    """
    if not idempotency_key or not str(idempotency_key).strip():
        raise ValueError(
            "Idempotency-Key обязателен (idempotency_key пуст)."
        )
    idem = str(idempotency_key).strip()
    destination = str(external_address or "").strip()
    if not destination:
        raise ValueError("external_address обязателен")
    raw_external_amount = Decimal(str(amount))
    normalized_external_d2 = quantize_external_efhc_d2(raw_external_amount)
    amt = d8(normalized_external_d2)
    rounding_dust = raw_external_amount - normalized_external_d2
    if amt <= 0:
        raise ValueError("amount must be positive after D2 ROUND_DOWN")
    if amt < MIN_WITHDRAW_EFHC:
        raise ValueError(
            f"Минимальная сумма вывода: {MIN_WITHDRAW_EFHC} EFHCm"
        )

    try:
        async with _tx_context(db):
            owner = await resolve_and_lock_financial_write_owner(
                db, global_id=int(global_id)
            )
            row = (
                await db.execute(
                    text(
                        """
                        SELECT id, tg_id, amount, status,
                               idempotency_key, hold_done,
                               refund_done, payout_ref,
                               created_at, updated_at, global_id,
                               external_address
                          FROM efhc_core.withdraw_requests
                         WHERE idempotency_key = :idempotency_key
                         FOR UPDATE
                        """
                    ),
                    {"idempotency_key": idem},
                )
            ).fetchone()
            if row is not None:
                existing = _row_to_dto(row)
                if (
                    existing.global_id is not None
                    and existing.global_id != owner.global_id
                ):
                    raise RuntimeError(
                        "Idempotency-Key belongs to another owner"
                    )
                existing_address = (
                    str(row[11]).strip()
                    if len(row) > 11 and row[11] is not None
                    else ""
                )
                if d8(existing.amount) != amt:
                    raise EfhcConflictError(
                        "Idempotency-Key относится к другой сумме вывода"
                    )
                if existing_address and existing_address != destination:
                    raise EfhcConflictError(
                        "Idempotency-Key относится к другому адресу вывода"
                    )
            else:
                pending = await db.execute(
                    text(
                        """
                        SELECT EXISTS(
                          SELECT 1 FROM efhc_core.withdraw_requests
                           WHERE global_id = :global_id
                             AND status = :status
                        )
                        """
                    ),
                    {
                        "global_id": owner.global_id,
                        "status": WITHDRAW_REQ_PENDING,
                    },
                )
                if bool(pending.scalar()):
                    raise RuntimeError(
                        "Active PENDING withdraw already exists. "
                        "Complete or cancel it first."
                    )
                row = (
                    await db.execute(
                        text(
                            """
                            INSERT INTO efhc_core.withdraw_requests
                              (tg_id, global_id, amount, status,
                               idempotency_key, external_address)
                            VALUES
                              (:tg_id, :global_id, :amount, :status,
                               :idempotency_key, :external_address)
                            RETURNING
                              id, tg_id, amount, status,
                              idempotency_key, hold_done,
                              refund_done, payout_ref,
                              created_at, updated_at, global_id
                            """
                        ),
                        {
                            "tg_id": owner.provider_tg_id,
                            "global_id": owner.global_id,
                            "amount": amt,
                            "status": WITHDRAW_REQ_PENDING,
                            "idempotency_key": idem,
                            "external_address": destination,
                        },
                    )
                ).fetchone()
            dto = _row_to_dto(row)
            if dto.hold_done:
                return dto

            main_before = d8(
                (
                    await db.execute(
                        text(
                            """
                            SELECT COALESCE(main_balance, 0)
                              FROM efhc_core.users
                             WHERE global_id = :global_id
                             FOR UPDATE
                            """
                        ),
                        {"global_id": owner.global_id},
                    )
                ).scalar()
                or 0
            )
            tx = await debit_user_to_bank_nocommit(
                db,
                global_id=owner.global_id,
                amount_efhc=dto.amount,
                reason="withdraw_hold",
                idempotency_key=f"{idem}:hold",
                meta={
                    "withdraw_request_id": dto.id,
                    "raw_external_efhc": str(raw_external_amount),
                    "debited_external_efhc": str(normalized_external_d2),
                    "rounding_dust_efhc": str(rounding_dust),
                    "external_rounding": "D2_ROUND_DOWN",
                },
            )
            log_id = int(getattr(tx, "created_log_id", 0) or 0)
            if log_id:
                main_after = d8(tx.user__main__balance)
                await append_transfer_meta(
                    db,
                    log_id=log_id,
                    meta={
                        "audit__schema__version": "v2-global-owner",
                        "withdraw_audit": True,
                        "atomic_request_hold": True,
                        "op_type": "WITHDRAW",
                        "global_id": owner.global_id,
                        "raw_external_efhc": str(raw_external_amount),
                        "debited_external_efhc": str(normalized_external_d2),
                        "rounding_dust_efhc": str(rounding_dust),
                        "external_rounding": "D2_ROUND_DOWN",
                        "network_fee_payer": "project",
                        "before": {
                            "main_balance_before": str(main_before),
                            "withdrawable__main__before": str(
                                main_before
                            ),
                            "amount": str(d8(dto.amount)),
                            "min_amount": str(d8(MIN_WITHDRAW_EFHC)),
                        },
                        "after": {
                            "main_balance_after": str(main_after),
                            "withdrawable__main__after": str(
                                main_after
                            ),
                            "invariant_ok": bool(
                                main_after
                                == d8(main_before - d8(dto.amount))
                            ),
                        },
                    },
                )
            row2 = (
                await db.execute(
                    text(
                        """
                        UPDATE efhc_core.withdraw_requests
                           SET hold_done = TRUE, updated_at = now()
                         WHERE id = :request_id
                           AND global_id = :global_id
                           AND status = :status
                        RETURNING
                          id, tg_id, amount, status, idempotency_key,
                          hold_done, refund_done, payout_ref,
                          created_at, updated_at, global_id
                        """
                    ),
                    {
                        "request_id": dto.id,
                        "global_id": owner.global_id,
                        "status": WITHDRAW_REQ_PENDING,
                    },
                )
            ).fetchone()
            return _row_to_dto(row2) if row2 else dto
    except Exception as exc:
        logger.error(
            "request_withdraw atomic hold failed "
            "(global_id=%s idempotency_key=%s): %s",
            global_id,
            idem,
            exc,
        )
        raise RuntimeError(
            "Недостаточно средств или временная ошибка холда."
        ) from exc



async def cancel_withdraw(
    db: AsyncSession,
    *,
    global_id: int,
    request_id: int,
    idempotency_key: str | None = None,
) -> WithdrawRequestDTO:
    """Cancel and refund one request by canonical owner."""
    _ = (idempotency_key or "").strip()
    async with _tx_context(db):
        owner = await resolve_and_lock_financial_write_owner(
            db, global_id=int(global_id)
        )
        row = (
            await db.execute(
                text(
                    """
                    SELECT id, tg_id, amount, status, idempotency_key,
                           hold_done, refund_done, payout_ref,
                           created_at, updated_at, global_id
                      FROM efhc_core.withdraw_requests
                     WHERE id = :request_id
                       AND global_id = :global_id
                     FOR UPDATE
                    """
                ),
                {
                    "request_id": int(request_id),
                    "global_id": owner.global_id,
                },
            )
        ).fetchone()
        if not row:
            raise ValueError("withdraw request not found")
        dto = _row_to_dto(row)
        if dto.status != WITHDRAW_REQ_CANCELED:
            if dto.status != WITHDRAW_REQ_PENDING:
                raise RuntimeError("transition forbidden")
            row = (
                await db.execute(
                    text(
                        """
                        UPDATE efhc_core.withdraw_requests
                           SET status = :status,
                               processed_at = NOW() AT TIME ZONE 'UTC',
                               updated_at = now()
                         WHERE id = :request_id
                           AND global_id = :global_id
                           AND status = :pending
                        RETURNING
                          id, tg_id, amount, status, idempotency_key,
                          hold_done, refund_done, payout_ref,
                          created_at, updated_at, global_id
                        """
                    ),
                    {
                        "request_id": dto.id,
                        "global_id": owner.global_id,
                        "status": WITHDRAW_REQ_CANCELED,
                        "pending": WITHDRAW_REQ_PENDING,
                    },
                )
            ).fetchone()
            if not row:
                raise RuntimeError("transition forbidden")
            dto = _row_to_dto(row)
        if not dto.hold_done or dto.refund_done:
            return dto
        await credit_user_from_bank_nocommit(
            db,
            global_id=owner.global_id,
            amount_efhc=dto.amount,
            reason="withdraw_refund",
            idempotency_key=f"{dto.idempotency_key}:refund",
            meta={
                "withdraw_request_id": dto.id,
                "withdraw_refund_atomic": "true",
                "withdraw_refund_status": WITHDRAW_REQ_CANCELED,
            },
        )
        row2 = (
            await db.execute(
                text(
                    """
                    UPDATE efhc_core.withdraw_requests
                       SET refund_done = TRUE, updated_at = now()
                     WHERE id = :request_id
                       AND global_id = :global_id
                       AND status = :status
                    RETURNING
                      id, tg_id, amount, status, idempotency_key,
                      hold_done, refund_done, payout_ref,
                      created_at, updated_at, global_id
                    """
                ),
                {
                    "request_id": dto.id,
                    "global_id": owner.global_id,
                    "status": WITHDRAW_REQ_CANCELED,
                },
            )
        ).fetchone()
        if not row2:
            raise RuntimeError("withdraw refund finalization failed")
        return _row_to_dto(row2)



# ======================================================================
# =======
# Действия админа: approve / reject / mark_paid
# ======================================================================
# =======


async def approve_withdraw_request(
    db: AsyncSession,
    *,
    request_id: int,
    actor_global_id: int,
    idempotency_key: str,
) -> WithdrawRequestDTO:
    """Единый вход: approve.

    Канон:
    - статус меняется только атомарно из PENDING;
    - actor_global_id обязателен (аудит);
    - idempotency_key обязателен (идемпотентность);
    - идемпотентность хранится в efhc_admin.idempotency_key.
    """
    actor_id = int(actor_global_id)
    rid = int(request_id)
    idem = (idempotency_key or "").strip()
    if actor_id <= 0:
        raise ValueError("actor_global_id required")
    if rid <= 0:
        raise ValueError("request_id required")
    if not idem:
        raise ValueError("idempotency_key required")

    async with _tx_context(db):
        admin_id = await _ensure_admin_whitelisted(
            db,
            actor_global_id=actor_id,
        )
        await _idem_ensure_row(
            db,
            key=idem,
            scope="withdraw_approve",
            request_fingerprint=str(rid),
            actor_global_id=actor_id,
            admin_id=admin_id,
        )

        idem_row = await _idem_lock_row(db, key=idem)
        if idem_row is None:
            raise RuntimeError("idempotency lock failed")

        if bool(getattr(idem_row, "used", False)):
            dto_hit = await _fetch_withdraw_request(db, request_id=rid)
            await AdminLogger.write(
                db,
                actor_global_id=actor_id,
                admin_id=admin_id,
                action="WITHDRAW_APPROVE_IDEM",
                entity="withdraw_request",
                entity_id=rid,
                details=f"idk={idem}; hit",
            )
            return dto_hit

        try:
            dto = await _admin_approve_withdraw_nocommit(
                db,
                request_id=rid,
            )
        except Exception as exc:
            await AdminLogger.write(
                db,
                actor_global_id=actor_id,
                admin_id=admin_id,
                action="WITHDRAW_APPROVE_FAIL",
                entity="withdraw_request",
                entity_id=rid,
                details=f"idk={idem}; {exc}",
            )
            raise

        await _idem_mark_used(
            db,
            key=idem,
            response_code=200,
            response_payload={
                "withdraw_request_id": int(dto.id),
                "status": str(dto.status),
            },
        )

        await AdminLogger.write(
            db,
            actor_global_id=actor_id,
            admin_id=admin_id,
            action="WITHDRAW_APPROVE",
            entity="withdraw_request",
            entity_id=rid,
            details=f"idk={idem}; PENDING->{dto.status}",
        )
        return dto


async def _idem_ensure_row(
    db: AsyncSession,
    *,
    key: str,
    scope: str,
    request_fingerprint: str,
    actor_global_id: int,
    admin_id: int | None = None,
) -> None:
    """Создать строку ключа идемпотентности, если её нет.

    Таблица: efhc_admin.idempotency_key (UNIQUE key).
    """
    k = (key or "").strip()
    if not k:
        raise ValueError("idempotency_key required")
    sc = (scope or "").strip()[:64] or None
    fp = (request_fingerprint or "").strip()[:128] or None

    sql = text(
        "\n".join(
            [
                "INSERT INTO " + SCHEMA_ADMIN + ".idempotency_key",
                "(key, scope, request_fingerprint, "
                "global_id, admin_id, expires_at)",
                "VALUES (:k, :sc, :fp, :global_id, :admin_id, "
                "timezone('utc', now()) + interval '180 days')",
                "ON CONFLICT (key) DO NOTHING",
            ]
        )
    )
    await db.execute(
        sql,
        {
            "k": k,
            "sc": sc,
            "fp": fp,
            "global_id": int(actor_global_id),
            "admin_id": (
                None if admin_id is None else int(admin_id)
            ),
        },
    )


async def _idem_lock_row(
    db: AsyncSession,
    *,
    key: str,
) -> IdempotencyKey | None:
    """Залочить ключ (SELECT ... FOR UPDATE) и вернуть ORM-объект."""
    k = (key or "").strip()
    if not k:
        return None

    stmt = (
        select(IdempotencyKey)
        .where(IdempotencyKey.key == k)
        .with_for_update()
    )
    res = await db.execute(stmt)
    return res.scalars().first()


async def _idem_mark_used(
    db: AsyncSession,
    *,
    key: str,
    response_code: int,
    response_payload: dict[str, Any],
) -> None:
    """Пометить ключ использованным и сохранить часть ответа."""
    k = (key or "").strip()
    if not k:
        raise ValueError("idempotency_key required")
    payload = dict(response_payload or {})
    sql = text(
        "\n".join(
            [
                "UPDATE " + SCHEMA_ADMIN + ".idempotency_key",
                "   SET used = true,",
                "       response_code = :rc,",
                "       response_payload_json = CAST(:pj AS jsonb)",
                " WHERE key = :k",
            ]
        )
    )
    await db.execute(
        sql,
        {"k": k, "rc": int(response_code), "pj": json.dumps(payload)},
    )


async def _admin_approve_withdraw_nocommit(
    db: AsyncSession,
    *,
    request_id: int,
) -> WithdrawRequestDTO:
    """Атомарный переход PENDING→PAID без commit().

    Commit выполняет внешний слой (approve_withdraw_request).
    """
    rid = int(request_id)

    lock_q = text(
        "\n".join(
            [
                "SELECT id,status,created_at FROM",
                " efhc_core.withdraw_requests",
                "WHERE id = :rid",
                "FOR UPDATE",
            ]
        )
    )
    locked = await db.execute(lock_q, {"rid": rid})
    lock_row = locked.fetchone()
    if not lock_row:
        raise ValueError("withdraw request not found")
    if str(lock_row[1]) != WITHDRAW_REQ_PENDING:
        logger.warning("withdraw transition forbidden")
        raise ValueError("transition forbidden")
    _require_withdraw_execution_window(lock_row[2])

    u = text(
        """
        UPDATE efhc_core.withdraw_requests
           SET status       = :st,
               processed_at = NOW() AT TIME ZONE 'UTC',
               updated_at   = now()
         WHERE id = :rid
           AND status = :pending
           AND created_at > :execution_cutoff
        RETURNING
          id,
          tg_id,
          amount,
          status,
          idempotency_key AS idempotency_key,
          hold_done,
          refund_done,
          payout_ref,
          created_at,
          updated_at
        """
    )
    params = {
        "pending": WITHDRAW_REQ_PENDING,
        "rid": rid,
        "st": WITHDRAW_REQ_PAID,
        "execution_cutoff": utcnow() - timedelta(
            days=FINANCIAL_EXECUTION_DAYS
        ),
    }
    r = await db.execute(u, params)
    row = r.fetchone()
    if not row:
        logger.warning("withdraw transition forbidden")
        raise ValueError("transition forbidden")
    return _row_to_dto(row)


async def reject_withdraw_request(
    db: AsyncSession,
    *,
    request_id: int,
    actor_global_id: int,
    reason: str,
) -> WithdrawRequestDTO:
    """Единый вход: reject.

    Канон SSOT: статус меняется только атомарно из PENDING.
    actor_global_id и reason зарезервированы под аудит.
    """
    actor_id = int(actor_global_id)
    reason_s = str(reason)
    admin_id = await _ensure_admin_whitelisted(
        db,
        actor_global_id=actor_id,
    )
    try:
        dto = await admin_reject_withdraw(db, request_id=request_id)
    except Exception as exc:
        await AdminLogger.write(
            db,
            actor_global_id=actor_id,
            admin_id=admin_id,
            action="WITHDRAW_REJECT_FAIL",
            entity="withdraw_request",
            entity_id=int(request_id),
            details=f"PENDING->REJECTED; {reason_s}; {exc}",
        )
        raise
    await AdminLogger.write(
        db,
        actor_global_id=actor_id,
        admin_id=admin_id,
        action="WITHDRAW_REJECT",
        entity="withdraw_request",
        entity_id=int(request_id),
        details=f"PENDING->{dto.status}; {reason_s}",
    )
    return dto


async def admin_approve_withdraw(
    db: AsyncSession,
    *,
    request_id: int,
) -> WithdrawRequestDTO:
    """Админ утверждает заявку.

    Legacy-обёртка: сохраняет старое поведение commit().
    Новый каноничный путь: approve_withdraw_request().
    """
    try:
        dto = await _admin_approve_withdraw_nocommit(
            db,
            request_id=int(request_id),
        )
        await db.commit()
        return dto
    except Exception:
        await db.rollback()
        raise


async def admin_reject_withdraw(
    db: AsyncSession,
    *,
    request_id: int,
) -> WithdrawRequestDTO:
    """Админ отклоняет заявку.

    FIND-003 repair:
    status=REJECTED, refund transfer and refund_done are committed as
    one atomic transaction. Legacy REJECTED + refund_done=FALSE rows can
    be repaired by retry through the same nocommit refund path.
    """

    async with _tx_context(db):
        lock_q = text(
            """
            SELECT
              id,
              tg_id,
              amount,
              status,
              idempotency_key AS idempotency_key,
              hold_done,
              refund_done,
              payout_ref,
              created_at,
              updated_at,
              global_id
            FROM efhc_core.withdraw_requests
            WHERE id = :rid
            FOR UPDATE
            """
        )
        locked = await db.execute(lock_q, {"rid": int(request_id)})
        lock_row = locked.fetchone()
        if not lock_row:
            raise ValueError("withdraw request not found")

        current = _row_to_dto(lock_row)
        if current.status == WITHDRAW_REQ_REJECTED:
            dto = current
        else:
            if current.status != WITHDRAW_REQ_PENDING:
                logger.warning("withdraw transition forbidden")
                raise ValueError("transition forbidden")

            u = text(
                """
                UPDATE efhc_core.withdraw_requests
                   SET status       = :st,
                       processed_at = NOW() AT TIME ZONE 'UTC',
                       updated_at   = now()
                 WHERE id = :rid
                   AND status = :pending
                RETURNING
                  id,
                  tg_id,
                  amount,
                  status,
                  idempotency_key AS idempotency_key,
                  hold_done,
                  refund_done,
                  payout_ref,
                  created_at,
                  updated_at,
                  global_id
                """
            )
            r = await db.execute(
                u,
                {
                    "pending": WITHDRAW_REQ_PENDING,
                    "rid": int(request_id),
                    "st": WITHDRAW_REQ_REJECTED,
                },
            )
            row = r.fetchone()
            if not row:
                logger.warning("withdraw transition forbidden")
                raise ValueError("transition forbidden")
            dto = _row_to_dto(row)

        if not dto.hold_done or dto.refund_done:
            return dto

        try:
            if dto.global_id is None:
                raise RuntimeError("withdraw global owner missing")
            await credit_user_from_bank_nocommit(
                db,
                global_id=dto.global_id,
                amount_efhc=dto.amount,
                reason="withdraw_reject_refund",
                idempotency_key=f"{dto.idempotency_key}:refund",
                meta={
                    "withdraw_request_id": int(dto.id),
                    "withdraw_refund_atomic": "true",
                    "withdraw_refund_status": WITHDRAW_REQ_REJECTED,
                },
            )
        except Exception as e:
            logger.error(
                (
                    "reject withdraw_refund failed "
                    "(user=%s, req_id=%s): %s"
                ),
                dto.tg_id,
                dto.id,
                e,
            )
            msg = "Рефанд временно недоступен, повторите позже."
            raise RuntimeError(msg) from e

        u2 = text(
            """
            UPDATE efhc_core.withdraw_requests
               SET refund_done = TRUE,
                   updated_at  = now()
             WHERE id = :rid
               AND status = :st
            RETURNING
              id,
              tg_id,
              amount,
              status,
              idempotency_key AS idempotency_key,
              hold_done,
              refund_done,
              payout_ref,
              created_at,
              updated_at,
              global_id
            """
        )
        r2 = await db.execute(
            u2,
            {"rid": int(dto.id), "st": WITHDRAW_REQ_REJECTED},
        )
        row2 = r2.fetchone()
        if not row2:
            raise RuntimeError(
                "withdraw reject refund finalization failed"
            )
        return _row_to_dto(row2)


async def admin_mark_paid(
    db: AsyncSession,
    *,
    request_id: int,
    payout_ref: str | None = None,
) -> WithdrawRequestDTO:
    """Админ помечает заявку как PAID."""

    u = text(
        """
        UPDATE efhc_core.withdraw_requests
           SET status       = :st,
               payout_ref   = COALESCE(:pref, payout_ref),
               processed_at = NOW() AT TIME ZONE 'UTC',
               updated_at   = now()
         WHERE id = :rid
           AND status = :pending
           AND created_at > :execution_cutoff
        RETURNING
          id,
          tg_id,
          amount,
          status,
          idempotency_key AS idempotency_key,
          hold_done,
          refund_done,
          payout_ref,
          created_at,
          updated_at
        """
    )
    r = await db.execute(
        u,
        {
            "pending": WITHDRAW_REQ_PENDING,
            "pref": (payout_ref or None),
            "rid": int(request_id),
            "st": WITHDRAW_REQ_PAID,
            "execution_cutoff": utcnow() - timedelta(
                days=FINANCIAL_EXECUTION_DAYS
            ),
        },
    )
    row = r.fetchone()
    if not row:
        await db.rollback()
        logger.warning("withdraw transition forbidden")
        raise ValueError("transition forbidden")
    await db.commit()
    return _row_to_dto(row)


# ======================================================================
# =======
# Витрины/списки (курсорно, без OFFSET).
# Для роутов.
# ======================================================================
# =======


async def list_user_withdraws(
    db: AsyncSession,
    *,
    global_id: int,
    limit: int = 50,
    cursor: str | None = None,
    status_filter: str | None = None,
) -> WithdrawPageDTO:
    """Return canonical owner withdrawal page."""
    limit = max(1, min(int(limit), 200))
    c_ts, c_id = _parse_withdraw_cursor(cursor)
    base = """
        SELECT
          id, tg_id, amount, status, idempotency_key,
          hold_done, refund_done, payout_ref,
          created_at, updated_at, global_id
          FROM efhc_core.withdraw_requests
         WHERE global_id = :global_id
        """
    params: dict[str, Any] = {
        "global_id": int(global_id),
        "lim": int(limit),
    }

    if status_filter:
        base += " AND status = :sf"
        params["sf"] = str(status_filter)

    if c_ts is not None and c_id is not None:
        base += (
            " AND ((created_at > :c_ts) "
            "OR (created_at = :c_ts AND id > :c_id))"
        )
        params["c_ts"] = c_ts.astimezone(UTC)
        params["c_id"] = int(c_id)

    base += " ORDER BY created_at ASC, id ASC LIMIT :lim"

    r = await db.execute(text(base), params)
    rows = r.fetchall()

    items = [_row_to_dto(row) for row in rows]
    next_cursor = None
    if rows:
        # created_at
        last_ts: datetime = rows[-1][8].astimezone(UTC)
        last_id: int = int(rows[-1][0])  # id
        next_cursor = _make_withdraw_cursor(last_ts, last_id)

    return WithdrawPageDTO(items=items, next_cursor=next_cursor)


# ======================================================================
# =======
# Самовосстановление.
#
# Находит висячие заявки и исправляет.
# • REQUESTED без hold_done → выполнить холд.
# • REJECTED/CANCELED: hold_done без refund_done: рефанд.
# пользователя.
#
# Пакетная обработка ограничена.
# ======================================================================
# =======


async def ensure_consistency(
    db: AsyncSession,
    *,
    scan_minutes: int = 240,
    batch_limit: int = 200,
    actor_global_id: int | None = None,
    admin_id: int | None = None,
    operation_idempotency_key: str | None = None,
) -> dict[str, int]:
    """Восстановить withdrawal-маркеры и деньги атомарно с Admin audit.

    Активный Admin path передаёт actor и ``Idempotency-Key``. Все
    денежные repair primitives остаются ``nocommit``; root transaction
    фиксируется один раз после обязательных audit-записей.
    """
    fixed_hold = 0
    fixed_refund = 0
    scope = "withdraw_repair_consistency"
    fingerprint = json.dumps(
        {
            "batch_limit": int(batch_limit),
            "scan_minutes": int(scan_minutes),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    op_key = str(operation_idempotency_key or "").strip()
    has_admin_context = actor_global_id is not None or admin_id is not None
    if has_admin_context and (actor_global_id is None or admin_id is None):
        raise ValueError("Для repair требуется полный Admin actor context")
    if has_admin_context and not op_key:
        raise ValueError("Idempotency-Key обязателен для Admin repair")

    try:
        if op_key:
            if actor_global_id is None:
                raise ValueError("Admin actor_global_id обязателен")
            await _idem_ensure_row(
                db,
                key=op_key,
                scope=scope,
                request_fingerprint=fingerprint,
                actor_global_id=int(actor_global_id),
                admin_id=admin_id,
            )
            idem = await _idem_lock_row(db, key=op_key)
            if idem is None:
                raise RuntimeError("Admin idempotency row не создан")
            if (
                str(idem.scope or "") != scope
                or str(idem.request_fingerprint or "") != fingerprint
                or int(idem.global_id or 0) != int(actor_global_id)
            ):
                raise EfhcConflictError(
                    "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD"
                )
            if bool(idem.used):
                payload = dict(idem.response_payload_json or {})
                result = {
                    "auto_fixed_hold": int(
                        payload.get("auto_fixed_hold", 0) or 0
                    ),
                    "auto_fixed_refund": int(
                        payload.get("auto_fixed_refund", 0) or 0
                    ),
                }
                await db.rollback()
                return result

        r1 = await db.execute(
            text(
                """
                SELECT id
                  FROM efhc_core.withdraw_requests
                 WHERE status = :st
                   AND hold_done = FALSE
                   AND created_at >= (now() - (:mins)::interval)
                 ORDER BY created_at ASC
                 LIMIT :lim
                """
            ),
            {
                "st": WITHDRAW_REQ_PENDING,
                "mins": f"{int(scan_minutes)} minutes",
                "lim": int(batch_limit),
            },
        )
        hold_ids = [int(row[0]) for row in r1.fetchall()]

        for request_id in hold_ids:
            try:
                async with db.begin_nested():
                    locked = await db.execute(
                        text(
                            """
                            SELECT id, tg_id, amount, status,
                                   idempotency_key, hold_done, refund_done,
                                   payout_ref, created_at, updated_at,
                                   global_id
                              FROM efhc_core.withdraw_requests
                             WHERE id = :rid
                             FOR UPDATE
                            """
                        ),
                        {"rid": request_id},
                    )
                    row = locked.fetchone()
                    if row is None:
                        continue
                    dto = _row_to_dto(row)
                    if dto.status != WITHDRAW_REQ_PENDING or dto.hold_done:
                        continue
                    if dto.global_id is None:
                        raise RuntimeError("withdraw global owner missing")
                    await debit_user_to_bank_nocommit(
                        db,
                        global_id=dto.global_id,
                        amount_efhc=dto.amount,
                        reason="withdraw_hold",
                        idempotency_key=f"{dto.idempotency_key}:hold",
                    )
                    updated = await db.execute(
                        text(
                            """
                            UPDATE efhc_core.withdraw_requests
                               SET hold_done = TRUE,
                                   updated_at = now()
                             WHERE id = :rid
                               AND status = :st
                               AND hold_done = FALSE
                            """
                        ),
                        {
                            "rid": request_id,
                            "st": WITHDRAW_REQ_PENDING,
                        },
                    )
                    if int(getattr(updated, "rowcount", 0) or 0) == 0:
                        raise RuntimeError(
                            "withdraw hold repair marker race"
                        )
                    if actor_global_id is not None:
                        await AdminLogger.write(
                            db,
                            actor_global_id=int(actor_global_id),
                            admin_id=admin_id,
                            action="WITHDRAW_HOLD_REPAIR",
                            entity="withdrawal",
                            entity_id=request_id,
                            details=f"operation_idempotency_key={op_key}",
                            required=True,
                        )
                fixed_hold += 1
            except Exception as exc:
                logger.warning(
                    "ensure_consistency hold repair failed "
                    "(req_id=%s): %s",
                    request_id,
                    exc,
                )

        r2 = await db.execute(
            text(
                """
                SELECT id
                  FROM efhc_core.withdraw_requests
                 WHERE (status = :st1 OR status = :st2)
                   AND hold_done = TRUE
                   AND refund_done = FALSE
                   AND updated_at >= (now() - (:mins)::interval)
                 ORDER BY updated_at ASC
                 LIMIT :lim
                """
            ),
            {
                "st1": WITHDRAW_REQ_REJECTED,
                "st2": WITHDRAW_REQ_CANCELED,
                "mins": f"{int(scan_minutes)} minutes",
                "lim": int(batch_limit),
            },
        )
        refund_ids = [int(row[0]) for row in r2.fetchall()]

        for request_id in refund_ids:
            try:
                async with db.begin_nested():
                    locked = await db.execute(
                        text(
                            """
                            SELECT id, tg_id, amount, status,
                                   idempotency_key, hold_done, refund_done,
                                   payout_ref, created_at, updated_at,
                                   global_id
                              FROM efhc_core.withdraw_requests
                             WHERE id = :rid
                             FOR UPDATE
                            """
                        ),
                        {"rid": request_id},
                    )
                    row = locked.fetchone()
                    if row is None:
                        continue
                    dto = _row_to_dto(row)
                    if (
                        dto.status
                        not in {
                            WITHDRAW_REQ_REJECTED,
                            WITHDRAW_REQ_CANCELED,
                        }
                        or not dto.hold_done
                        or dto.refund_done
                    ):
                        continue
                    if dto.global_id is None:
                        raise RuntimeError("withdraw global owner missing")
                    await credit_user_from_bank_nocommit(
                        db,
                        global_id=dto.global_id,
                        amount_efhc=dto.amount,
                        reason="withdraw_refund",
                        idempotency_key=f"{dto.idempotency_key}:refund",
                    )
                    updated = await db.execute(
                        text(
                            """
                            UPDATE efhc_core.withdraw_requests
                               SET refund_done = TRUE,
                                   updated_at = now()
                             WHERE id = :rid
                               AND (status = :st1 OR status = :st2)
                               AND hold_done = TRUE
                               AND refund_done = FALSE
                            """
                        ),
                        {
                            "rid": request_id,
                            "st1": WITHDRAW_REQ_REJECTED,
                            "st2": WITHDRAW_REQ_CANCELED,
                        },
                    )
                    if int(getattr(updated, "rowcount", 0) or 0) == 0:
                        raise RuntimeError(
                            "withdraw refund repair marker race"
                        )
                    if actor_global_id is not None:
                        await AdminLogger.write(
                            db,
                            actor_global_id=int(actor_global_id),
                            admin_id=admin_id,
                            action="WITHDRAW_REFUND_REPAIR",
                            entity="withdrawal",
                            entity_id=request_id,
                            details=f"operation_idempotency_key={op_key}",
                            required=True,
                        )
                fixed_refund += 1
            except Exception as exc:
                logger.warning(
                    "ensure_consistency refund repair failed "
                    "(req_id=%s): %s",
                    request_id,
                    exc,
                )

        result = {
            "auto_fixed_hold": fixed_hold,
            "auto_fixed_refund": fixed_refund,
        }
        if actor_global_id is not None:
            await AdminLogger.write(
                db,
                actor_global_id=int(actor_global_id),
                admin_id=admin_id,
                action="WITHDRAW_REPAIR_CONSISTENCY",
                entity="withdrawal_repair",
                details=(
                    f"idempotency_key={op_key}; "
                    f"scan_minutes={int(scan_minutes)}; "
                    f"batch_limit={int(batch_limit)}; "
                    f"fixed_hold={fixed_hold}; "
                    f"fixed_refund={fixed_refund}"
                ),
                required=True,
            )
        if op_key:
            await _idem_mark_used(
                db,
                key=op_key,
                response_code=200,
                response_payload=result,
            )
        await db.commit()
        return result
    except Exception:
        await db.rollback()
        raise


# ======================================================================
# =======
# Пояснения «для чайника»:
# • Почему холд сразу при создании?
# Чтобы не потратить EFHC параллельно.
# или
# Средства переводятся с баланса в Банк.
#
# • Что если холд упал?
# Заявка остаётся REQUESTED с hold_done = FALSE.
# пополнить
# Пользователь может пополнить
# и повторить.
# вызывает
# ensure_consistency() пытается повторить холд.
# idempotency_key.
#
# • Когда деньги реально уходят?
# В этом модуле — никогда.
# Мы переводим EFHC в Банк (холд).
# При необходимости возвращаем обратно
# (рефанд).
# списание
# Вывод на биржу/DEX и т.д.
# ручной процесс.
# администратора/интеграции.
#
# • Почему бонусы нельзя вывести?
# Канон: EFHCb невыплатные; выводится только EFHCm.
# игры/
# При расходовании номинал
# возвращается в Банк.
# ======================================================================
# =======
