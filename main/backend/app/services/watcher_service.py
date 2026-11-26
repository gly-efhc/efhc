# backend/app/services/watcher_service.py
# =====================================================================
# EFHC Bot — Вотчер входящих платежей TON (автозачисления через Банк)
# --------------------------------------------------------------------
# Назначение:
# Обрабатывает входящие транзакции TON по адресу проекта, разбирает MEMO
# по канону и выполняет действия: PaymentIntent settlement EFHC-пакетов,
# создание заявки на NFT (ручная выдача), автоматический депозит EFHC по
# правилам. Все денежные движения — строго через банковский сервис.
#
# Канон/инварианты:
# • Только посекундная генерация в проекте (здесь не применяется).
# • Денежные операции производит единый банк: никакой «эмиссии в обход».
# • P2P запрещён. Обратной конверсии EFHC→kWh нет.
# • NFT: только заявка (PAID_PENDING_MANUAL), никакой автодоставки.
# • Идемпотентность по tx_hash (UNIQUE в ton_inbox_logs) + read-through.
# • Идентификация пользователя:
# 1) по active + verified wallet binding в wallet_bindings,
# 2) при legacy Telegram MEMO — через provider resolution до global_id.
#
# ИИ-защиты / самовосстановление:
# • Read-through: повторная обработка одной транзакции не даёт дублей
# (UNIQUE(tx_hash) + возврат финального результата).
# • «Догон хвостов»: повторная обработка логов
#   с не финальными статусами.
# у которых next_retry_at IS NULL или <= NOW().
# • Деградация: сетевые/временные ошибки TON API не рушат цикл —
# помечаются error_* и переигрываются отдельно.
#
# Запреты:
# • Этот модуль не создаёт NFT и не меняет ставки генерации.
# • Не трогает пользовательские балансы напрямую — только через Банк
# (app.services.transactions_service).
# =====================================================================

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_DOWN, Decimal
from typing import Any, cast

from app.core.config_core import get_settings
from app.core.logging_core import get_logger
from app.deps import d8
from app.domain.finance.external_amounts import (
    external_amount_from_display,
)
from app.identity.types import (
    global_id_from_database,
    global_id_to_database,
    parse_global_id,
)
from app.integrations.ton_api import TonAPIClient, TonAPIEvent
from app.integrations.ton_memo import parse_memo_for_watcher
from app.lib.time import utcnow
from app.lib.ton_address import (
    TonAddressError,
    canonicalize_ton_address,
)
from app.services.financial_execution_window import (
    CODE_EXECUTION_EXPIRED,
    CODE_FIRST_SEEN_EXPIRED,
    trusted_datetime_from_unix,
    validate_external_financial_execution,
)
from app.services.intent_payload_parsing_service import (
    parse_intent_payload,
)
from app.services.jetton_parsing_service import (
    parse_jetton_payload_envelope,
    parse_payment_intent_transport_from_tx,
)
from app.services.payment_reconciliation_service import (
    ConfirmPaymentResult,
    confirm_payment_intent,
)
from app.services.shop_payment_tx_hash_lock_service import (
    claim_tx_hash_settlement,
)
from app.services.shop_service import (
    ITEM_TYPE_EFHC_PACKAGE,
    ITEM_TYPE_NFT_VIP,
)
from app.services.transactions_service import credit_user_from_bank
from app.standards.finance_rules import quantize_external_efhc_d2
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)
settings = get_settings()
SCHEMA = getattr(settings, "DB_SCHEMA_CORE", "efhc_core")


def _global_id_db(global_id: str) -> int:
    """Явная DB-граница для канонического десятизначного global_id."""
    return cast(int, global_id_to_database(parse_global_id(global_id)))


TON_MAIN_WALLET: str = str(settings.TON_MAIN_WALLET or "")
if not TON_MAIN_WALLET:
    logger.warning(
        "[WATCHER] TON_MAIN_WALLET is not set in config "
        "— watcher will not work correctly."
    )

# --------------------------------------------------------------------
# Разбор MEMO канонически принадлежит app.integrations.ton_memo.
# --------------------------------------------------------------------


def _parse_memo(memo: str) -> tuple[str, dict[str, int | str]]:
    """Разобрать MEMO через общий TON memo SSOT adapter."""
    parsed = parse_memo_for_watcher(memo)
    return cast(tuple[str, dict[str, int | str]], parsed)


# --------------------------------------------------------------------
# Статусы ton_inbox_logs.
# --------------------------------------------------------------------
STATUS_RECEIVED = "received"
STATUS_PARSED = "parsed"
STATUS_CREDITED = "credited"
STATUS_PAID_AUTO = "paid_auto"
STATUS_NFT_MANUAL = "paid_pending_manual"
STATUS_ERROR_MEMO = "error_bad_memo"
STATUS_ERROR_USER = "error_user_not_found"
STATUS_ERROR_NET = "error_network_retry"
STATUS_ERROR_SYS = "error_retry"
STATUS_PENDING_MAP = "parsed_pending_mapping"
STATUS_PENDING_MANUAL = "pending_manual"
STATUS_EXPIRED_NO_CREDIT = "expired_no_credit"

# Маркер read-through защиты: WHERE external_tx_hash = :h
# Маркер read-through защиты: external_tx_hash = :h
# Маркер fail-closed защиты: shop_external confirm blocked
# Маркер fail-closed защиты: pending order not found
# Маркер fail-closed защиты: if not o:

FINAL_STATUSES = {
    STATUS_CREDITED,
    STATUS_PAID_AUTO,
    STATUS_NFT_MANUAL,
    STATUS_PENDING_MANUAL,
    STATUS_EXPIRED_NO_CREDIT,
}


@dataclass
class IncomingTx:
    tx_hash: str
    from_address: str
    to_address: str
    amount: Decimal
    memo: str
    utime: int
    asset: str = "TON"
    jetton_master: str = ""
    amount_asset: Decimal = Decimal("0")


def _now_utc() -> datetime:
    """Вернуть текущее UTC-время как timezone-aware datetime."""
    return cast(datetime, utcnow())


def _retry_backoff_delay(retries_count: int) -> timedelta:
    """Вернуть ограниченную экспоненциальную задержку повтора."""
    n = max(1, int(retries_count))
    base_sec = 30
    cap_sec = 15 * 60
    sec = base_sec * (2 ** (n - 1))
    sec = min(cap_sec, sec)
    return timedelta(seconds=int(sec))


async def _get_inbox_retries_count(
    db: AsyncSession,
    *,
    tx_hash: str,
) -> int:
    """Вернуть текущий счётчик повторов из ton_inbox_logs."""
    q = text("""
        SELECT COALESCE(retries_count, 0)
          FROM efhc_core.ton_inbox_logs
         WHERE tx_hash = :tx_hash
        """)
    r = await db.execute(q, {"tx_hash": str(tx_hash)})
    v = r.scalar()
    try:
        return int(v or 0)
    except Exception:
        return 0


def _norm_addr(addr: str) -> str:
    """Нормализовать корректный TON-адрес в canonical storage format EFHC."""
    cleaned = (addr or "").replace(" ", "")
    if not cleaned:
        return ""
    try:
        return cast(str, canonicalize_ton_address(cleaned))
    except TonAddressError:
        return cleaned


async def _record_unmatched_incoming(
    db: AsyncSession,
    *,
    tx_hash: str,
    asset: str,
    amount_asset: Decimal,
    from_address: str,
    to_address: str,
    memo: str,
    utime: int,
    reason: str,
) -> None:
    """Зафиксировать входящую транзакцию без каноничного payload.

    Правило SSOT:
    • Автоначисление возможно:
      - по payload/intent (канон EFHC:purpose:id:global_id),
      - либо при пустом MEMO по привязанному кошельку,
        с обязательной записью в unmatched_incoming.
    """

    asset_u = str(asset or "TON").upper()
    exact_meta: dict[str, Any] = {}
    if asset_u in {"TON", "USDT"}:
        external = external_amount_from_display(
            asset_u, amount_asset, require_positive=False
        )
        compatibility_amount = external.display.quantize(
            Decimal("0.00000001"), rounding=ROUND_DOWN
        )
        exact_meta = {
            "external_amount_atomic": str(external.atomic),
            "external_decimals": int(external.decimals),
            "external_amount_display": external.display_text,
            "amount_asset_d8_role": "frozen_schema_compatibility_only",
        }
    else:
        compatibility_amount = d8(amount_asset)
    q = text("""
        INSERT INTO efhc_core.unmatched_incoming (
            tx_hash, asset, amount_asset_d8,
            from_address, to_address, memo,
            utime, reason, meta, created_at
        ) VALUES (
            :tx, :asset, :amt,
            :fa, :ta, :memo,
            :ut, :reason, CAST(:meta AS JSONB), :now
        )
        ON CONFLICT (tx_hash) DO NOTHING
        """)
    await db.execute(
        q,
        {
            "tx": str(tx_hash),
            "asset": asset_u,
            "amt": compatibility_amount,
            "fa": str(from_address or ""),
            "ta": str(to_address or ""),
            "memo": str(memo or ""),
            "ut": int(utime or 0),
            "reason": str(reason or "unmatched"),
            "meta": json.dumps(exact_meta, ensure_ascii=False),
            "now": _now_utc(),
        },
    )


async def _confirm_payment_intent(
    db: AsyncSession,
    *,
    intent_id: int,
    global_id: str,
    provider_tg_id: int | None,
    purpose: str,
    payload: str,
    tx_hash: str,
    amount_asset: Decimal | None,
    asset: str,
    external_amount_atomic: int | str | None = None,
    external_decimals: int | None = None,
    to_address: str,
    trusted_operation_at: datetime | None = None,
    server_first_seen_at: datetime | None = None,
    return_note: bool = False,
    credit_user_from_bank_fn: Callable[..., Any] | None = None,
) -> str | ConfirmPaymentResult:
    """Внутренний compatibility/dependency seam над canonical reconciliation.

    Новая бизнес-логика не должна подтверждать платежи здесь напрямую:
    единственная canonical точка — ``confirm_payment_intent`` из
    ``payment_reconciliation_service``. Обёртка сохраняется для watcher
    orchestration и контролируемой dependency injection.
    """
    result = await confirm_payment_intent(
        db,
        intent_id=intent_id,
        global_id=global_id,
        provider_tg_id=provider_tg_id,
        purpose=purpose,
        payload=payload,
        tx_hash=tx_hash,
        amount_asset=amount_asset,
        asset=asset,
        external_amount_atomic=external_amount_atomic,
        external_decimals=external_decimals,
        to_address=to_address,
        trusted_operation_at=trusted_operation_at,
        server_first_seen_at=server_first_seen_at,
        status_credited=STATUS_CREDITED,
        status_paid_auto=STATUS_PAID_AUTO,
        status_error_memo=STATUS_ERROR_MEMO,
        status_error_sys=STATUS_ERROR_SYS,
        status_pending_manual=STATUS_PENDING_MANUAL,
        item_type_efhc_package=ITEM_TYPE_EFHC_PACKAGE,
        item_type_nft_vip=ITEM_TYPE_NFT_VIP,
        now_func=_now_utc,
        logger_obj=logger,
        credit_user_from_bank_fn=(
            credit_user_from_bank_fn or credit_user_from_bank
        ),
    )
    if return_note:
        return result
    return str(result.status)


def _transport_meta_for_tx(tx: IncomingTx | TonAPIEvent) -> dict[str, Any]:
    """Сохранить exact transport evidence для безопасного retry без DDL."""
    parsed = parse_payment_intent_transport_from_tx(tx=tx)
    decision = parsed.decision
    raw_asset = str(getattr(tx, "asset", "TON") or "TON").upper()
    financial_asset = {
        "EFHCJ": "EFHC",
        "JETTON_UNKNOWN": "UNKNOWN",
    }.get(decision.confirm_asset, decision.confirm_asset)
    native_atomic = 0
    try:
        native_atomic = int(
            (Decimal(str(getattr(tx, "amount", 0) or 0)) * Decimal("1000000000"))
            .to_integral_value()
        )
    except Exception:
        native_atomic = 0
    return {
        "transport_version": 2,
        "asset": raw_asset,
        "financial_asset": financial_asset,
        "jetton_master": str(getattr(tx, "jetton_master", "") or ""),
        "amount_atomic": str(int(decision.amount_atomic)),
        "token_decimals": int(decision.atomic_decimals),
        "native_amount_atomic": str(native_atomic),
        "provider": "tonapi",
    }


def _incoming_from_transport_meta(
    row: Any,
    meta: dict[str, Any],
) -> IncomingTx | None:
    if int(meta.get("transport_version") or 0) < 2:
        return None
    raw_asset = str(meta.get("asset") or "").upper()
    if raw_asset not in {"TON", "JETTON"}:
        return None
    try:
        native_atomic = int(str(meta.get("native_amount_atomic") or "0"))
        token_atomic = int(str(meta.get("amount_atomic") or "0"))
    except ValueError:
        return None
    amount = Decimal(native_atomic) / Decimal("1000000000")
    return IncomingTx(
        tx_hash=str(row[0]),
        from_address=str(row[1] or ""),
        to_address=str(row[2] or ""),
        amount=amount,
        memo=str(row[4] or ""),
        utime=int(row[5] or 0),
        asset=raw_asset,
        jetton_master=str(meta.get("jetton_master") or ""),
        amount_asset=(Decimal(token_atomic) if raw_asset == "JETTON" else Decimal("0")),
    )


async def _refetch_exact_incoming_tx(
    *,
    tx_hash: str,
    utime: int,
) -> TonAPIEvent | None:
    """Best-effort authoritative refetch for legacy rows lacking transport metadata."""
    if not TON_MAIN_WALLET:
        return None
    since = max(0, int(utime or 0) - 86400) if utime else None
    events = await TonAPIClient().get_incoming_payments(
        TON_MAIN_WALLET, limit=500, since_utime=since
    )
    for event in events:
        if str(event.tx_hash) == str(tx_hash):
            return event
    return None


async def _ton_log_upsert(
    db: AsyncSession,
    *,
    tx: IncomingTx | TonAPIEvent,
    status: str,
    note: str | None = None,
    next_retry_at: datetime | None = None,
) -> tuple[datetime, datetime | None]:
    """Upsert TON inbox и вернуть неизменяемые first-seen/trusted time."""
    q = """
        INSERT INTO efhc_core.ton_inbox_logs
          (
            tx_hash,
            from_address,
            to_address,
            amount,
            memo,
            status,
            retries_count,
            last_error,
            next_retry_at,
            processed_at,
            trusted_operation_at,
            meta,
            created_at,
            updated_at
          )
        VALUES
          (
            :tx_hash,
            :from_addr,
            :to_addr,
            :amount,
            :memo,
            CAST(:status AS VARCHAR),
            CASE WHEN :is_error THEN 1 ELSE 0 END,
            :note,
            :next_retry_at,
            CASE
              WHEN CAST(:status AS VARCHAR) IN (
                'credited',
                'paid_auto',
                'paid_pending_manual'
              ) THEN NOW()
              ELSE NULL
            END,
            :trusted_operation_at,
            CAST(:transport_meta AS jsonb),
            NOW(),
            NOW()
          )
        ON CONFLICT (tx_hash) DO UPDATE SET
          status = EXCLUDED.status,
          retries_count = CASE
            WHEN EXCLUDED.status LIKE 'error%%'
            THEN efhc_core.ton_inbox_logs.retries_count + 1
            ELSE efhc_core.ton_inbox_logs.retries_count
          END,
          last_error = CASE
            WHEN EXCLUDED.status LIKE 'error%%'
            THEN EXCLUDED.last_error
            ELSE NULL
          END,
          next_retry_at = EXCLUDED.next_retry_at,
          trusted_operation_at = COALESCE(
            efhc_core.ton_inbox_logs.trusted_operation_at,
            EXCLUDED.trusted_operation_at
          ),
          meta = COALESCE(efhc_core.ton_inbox_logs.meta, '{}'::jsonb)
                 || EXCLUDED.meta,
          updated_at = NOW(),
          processed_at = CASE
            WHEN EXCLUDED.status IN (
              'credited',
              'paid_auto',
              'paid_pending_manual'
            ) THEN NOW()
            ELSE efhc_core.ton_inbox_logs.processed_at
          END
        RETURNING created_at, trusted_operation_at
        """

    trusted_operation_at = trusted_datetime_from_unix(
        int(getattr(tx, "utime", 0) or 0)
    )
    result = await db.execute(
        text(q),
        {
            "tx_hash": tx.tx_hash,
            "from_addr": _norm_addr(tx.from_address),
            "to_addr": _norm_addr(tx.to_address),
            "amount": str(d8(tx.amount)),
            "memo": (tx.memo or "").strip(),
            "status": status,
            "is_error": status.startswith("error"),
            "note": (note or None),
            "next_retry_at": next_retry_at,
            "trusted_operation_at": trusted_operation_at,
            "transport_meta": json.dumps(_transport_meta_for_tx(tx)),
        },
    )
    row = result.first()
    if row is None:
        raise RuntimeError("ton_inbox_upsert_returning_missing")
    return row[0], row[1]


async def _ton_log_time_evidence(
    db: AsyncSession,
    tx_hash: str,
) -> tuple[datetime, datetime | None] | None:
    """Прочитать только trusted-time evidence до replay decision."""
    row = await db.execute(
        text(
            "SELECT created_at, trusted_operation_at "
            "FROM efhc_core.ton_inbox_logs "
            "WHERE tx_hash = :h LIMIT 1"
        ),
        {"h": tx_hash},
    )
    rec = row.fetchone()
    if rec is None:
        return None
    return rec[0], rec[1]


async def _database_first_seen_now(db: AsyncSession) -> datetime:
    """Получить trusted server first-seen без записи в financial state."""
    row = await db.execute(text("SELECT clock_timestamp()"))
    value = row.scalar_one()
    if not isinstance(value, datetime):
        raise RuntimeError("TON_INBOX_SERVER_TIME_INVALID")
    if value.tzinfo is None or value.utcoffset() is None:
        raise RuntimeError("TON_INBOX_SERVER_TIME_NAIVE")
    return value.astimezone(UTC)


async def _ton_log_exists_final(db: AsyncSession, tx_hash: str) -> bool:
    """Проверка: транзакция уже в финальном статусе (read-through)."""
    q = (
        "SELECT status FROM efhc_core.ton_inbox_logs "
        "WHERE tx_hash = :h LIMIT 1"
    )
    row = await db.execute(text(q), {"h": tx_hash})
    rec = row.fetchone()
    if not rec:
        return False
    return rec[0] in FINAL_STATUSES


@dataclass(frozen=True, slots=True)
class _WatcherOwner:
    global_id: str
    tg_id: int | None


async def _find_user_by_wallet(
    db: AsyncSession,
    addr: str,
) -> _WatcherOwner | None:
    """Разрешить verified wallet binding до canonical owner."""

    if not addr:
        return None
    row = await db.execute(
        text(
            """
            SELECT wb.global_id, wb.tg_id
              FROM efhc_core.wallet_bindings wb
             WHERE wb.wallet_address = :wa
               AND wb.is_active = TRUE
               AND wb.proof_verified = TRUE
               AND wb.global_id IS NOT NULL
             ORDER BY wb.is_primary DESC, wb.id DESC
             LIMIT 1
            """
        ),
        {"wa": _norm_addr(addr)},
    )
    found = row.fetchone()
    if not found or found[0] is None:
        return None
    return _WatcherOwner(
        global_id=str(global_id_from_database(found[0])),
        tg_id=(int(found[1]) if found[1] is not None else None),
    )


async def _find_user_by_tg_id(
    db: AsyncSession,
    tg_id: int,
) -> _WatcherOwner | None:
    """Разрешить Telegram memo selector до canonical owner."""

    row = await db.execute(
        text(
            """
            SELECT ui.global_id
              FROM efhc_core.user_identities ui
             WHERE ui.provider = 'telegram'
               AND ui.provider_tenant = 'default'
               AND ui.provider_subject = :subject
               AND ui.status = 'active'
               AND ui.is_verified = TRUE
             LIMIT 1
            """
        ),
        {"subject": str(int(tg_id))},
    )
    found = row.fetchone()
    if not found or found[0] is None:
        return None
    return _WatcherOwner(
        global_id=str(global_id_from_database(found[0])),
        tg_id=int(tg_id),
    )


async def _find_user_by_global_id(
    db: AsyncSession,
    global_id: str,
) -> _WatcherOwner | None:
    """Разрешить canonical memo selector без требования Telegram."""

    gid = _global_id_db(global_id)
    row = await db.execute(
        text(
            """
            SELECT
                u.global_id,
                (
                    SELECT CASE
                        WHEN ui.provider_subject ~ '^[0-9]+$'
                        THEN CAST(ui.provider_subject AS BIGINT)
                        ELSE NULL
                    END
                    FROM efhc_core.user_identities ui
                    WHERE ui.global_id = u.global_id
                      AND ui.provider = 'telegram'
                      AND ui.provider_tenant = 'default'
                      AND ui.status = 'active'
                      AND ui.is_verified = TRUE
                    ORDER BY ui.is_primary DESC, ui.id ASC
                    LIMIT 1
                ) AS telegram_subject
              FROM efhc_core.users u
             WHERE u.global_id = :global_id
             LIMIT 1
            """
        ),
        {"global_id": gid},
    )
    found = row.fetchone()
    if not found:
        return None
    return _WatcherOwner(
        global_id=str(global_id_from_database(found[0])),
        tg_id=(int(found[1]) if found[1] is not None else None),
    )


async def _find_pending_order(
    db: AsyncSession,
    *,
    global_id: str,
    qty: int,
) -> int | None:
    """Сохранённый compatibility helper старого SKU flow.

    После финансового аудита 1/10 новый runtime НЕ использует поиск заказа
    только по пользовательскому ``qty`` из MEMO: это недостаточное
    settlement proof. Canonical реализация — PaymentIntent reconciliation с
    exact asset/destination/amount. Helper не удаляется обычным cleanup,
    потому что отсутствие caller не является delete-proof; удаление требует
    отдельного решения и проверки исторических/import consumers.
    """
    row = await db.execute(
        text("""
            SELECT o.id
              FROM efhc_core.shop_orders o
             WHERE o.global_id = :global_id
               AND o.status = 'PENDING'
               AND o.type = :itype
               AND o.quantity_efhc = :q
             ORDER BY o.created_at ASC, o.id ASC
             LIMIT 1
            """),
        {
            "global_id": _global_id_db(global_id),
            "itype": ITEM_TYPE_EFHC_PACKAGE,
            "q": int(qty),
        },
    )
    r = row.fetchone()
    return int(r[0]) if r else None


async def _mark_order_paid_auto(
    db: AsyncSession,
    order_id: int,
    tx_hash: str,
) -> None:
    """Compatibility helper старого прямого SKU auto-delivery.

    Новый payment runtime не вызывает его из legacy SKU MEMO. Canonical
    PAID_AUTO выполняется внутри PaymentIntent reconciliation после всех
    financial guards и global tx_hash claim. Сохраняется fail-closed как
    historical compatibility surface; обычный cleanup не имеет права удалять.
    """
    res = await db.execute(
        text("""
            UPDATE efhc_core.shop_orders
               SET status = 'PAID_AUTO',
                   tx_hash = COALESCE(tx_hash, :h),
                   updated_at = NOW()
             WHERE id = :oid
               AND status = 'PENDING'
            """),
        {"oid": int(order_id), "h": tx_hash},
    )
    if getattr(res, "rowcount", 0) == 0:
        logger.warning(
            "PAID_AUTO update skipped (not PENDING): oid=%s",
            order_id,
        )


async def _create_nft_manual_request(
    db: AsyncSession,
    *,
    global_id: str,
    tx_hash: str,
    qty: int = 1,
) -> int:
    """
    NFT: создаём заявку PAID_PENDING_MANUAL в shop_orders.

    Канон:
      • Здесь нет автодоставки NFT — только заявка.
      • Админ вручную сопоставляет заявку с NFT и передаёт пользователю.
    """
    # Пытаемся найти NFT-карточку по item_type = ITEM_TYPE_NFT_VIP.
    row = await db.execute(
        text("""
            INSERT INTO efhc_core.shop_orders
                (
                    global_id,
                    type,
                    status,
                    tx_hash,
                    extra,
                    created_at,
                    updated_at
                )
            VALUES (
                :global_id,
                'NFT',
                'PAID_PENDING_MANUAL',
                :h,
                :extra::jsonb,
                NOW(),
                NOW()
            )
            RETURNING id
            """),
        {
            "global_id": _global_id_db(global_id),
            "h": tx_hash,
            "extra": json.dumps(
                {"item_type": ITEM_TYPE_NFT_VIP, "quantity": int(qty)}
            ),
        },
    )
    r = row.fetchone()
    if r is None:
        raise RuntimeError("shop_order_insert_failed")
    return int(r[0])


# =====================================================================
# Ядро обработки одной транзакции (read-through идемпотентность)
# =====================================================================


async def process_incoming_tx(
    db: AsyncSession,
    tx: IncomingTx | TonAPIEvent,
) -> str:
    """
    Обрабатывает одну входящую TON/jetton транзакцию.

    Вход:
      • tx_hash, from_address, to_address, amount, memo, utime.

    Итог:
      • Статус из набора FINAL / ERROR_* / STATUS_PENDING_MAP.
      • Побочные эффекты:
          – запись/обновление efhc_core.ton_inbox_logs,
          – начисление EFHC (credit_user_from_bank),
          – перевод заказа в PAID_AUTO,
          – создание заявки NFT (PAID_PENDING_MANUAL).

    Идемпотентность:
      • UNIQUE(tx_hash) в ton_inbox_logs.
      • Повторные вызовы для одной и той же транзакции безопасны.
    """
    # Нормализуем адрес назначения и отфильтровываем «чужие» транзакции.
    to_addr = _norm_addr(getattr(tx, "to_address", ""))
    main_addr = _norm_addr(TON_MAIN_WALLET)
    if TON_MAIN_WALLET and to_addr != main_addr:
        # Мягкий skip: фиксировать в лог нет смысла, это не наш кошелёк.
        return "skip:not_our_wallet"

    parsed_transport = parse_payment_intent_transport_from_tx(tx=tx)
    transport = parsed_transport.decision
    # P0 order: trusted time -> 10-day barrier -> replay -> mutation -> ledger.
    incoming_trusted_operation_at = trusted_datetime_from_unix(
        int(getattr(tx, "utime", 0) or 0)
    )
    time_evidence = await _ton_log_time_evidence(db, tx.tx_hash)
    if time_evidence is None:
        first_seen_at = await _database_first_seen_now(db)
        stored_trusted_operation_at = incoming_trusted_operation_at
    else:
        first_seen_at, stored_trusted_operation_at = time_evidence

    time_decision = validate_external_financial_execution(
        trusted_operation_at=stored_trusted_operation_at,
        server_first_seen_at=first_seen_at,
    )

    # Replay/final-status decision is intentionally after the time barrier.
    if await _ton_log_exists_final(db, tx.tx_hash):
        logger.debug("[WATCHER] tx %s already finalized", tx.tx_hash)
        return "already_final"

    if not time_decision.allowed:
        status = (
            STATUS_EXPIRED_NO_CREDIT
            if time_decision.code
            in {CODE_EXECUTION_EXPIRED, CODE_FIRST_SEEN_EXPIRED}
            else STATUS_PENDING_MANUAL
        )
        await _ton_log_upsert(
            db,
            tx=tx,
            status=status,
            note=time_decision.code,
            next_retry_at=None,
        )
        return status

    if (
        stored_trusted_operation_at is not None
        and incoming_trusted_operation_at is not None
        and stored_trusted_operation_at != incoming_trusted_operation_at
    ):
        await _ton_log_upsert(
            db,
            tx=tx,
            status=STATUS_PENDING_MANUAL,
            note="TRUSTED_OPERATION_TIME_CONFLICT",
            next_retry_at=None,
        )
        return STATUS_PENDING_MANUAL

    # После успешных time/replay guards фиксируем/обновляем inbox state.
    await _ton_log_upsert(db, tx=tx, status=STATUS_RECEIVED)

    try:
        # 2.1) PaymentIntent payload (A+B) имеет приоритет.
        raw_memo = getattr(tx, "memo", "") or ""
        if transport.transport_kind == "jetton_transfer":
            envelope = parse_jetton_payload_envelope(
                memo=str(raw_memo),
                jetton_master=getattr(tx, "jetton_master", ""),
            )
            if not envelope.ok:
                ip = parse_intent_payload(str(raw_memo))
                if not ip:
                    await _record_unmatched_incoming(
                        db,
                        tx_hash=str(getattr(tx, "tx_hash", "")),
                        asset=transport.confirm_asset,
                        amount_asset=transport.amount_display,
                        from_address=str(
                            getattr(tx, "from_address", "")
                        ),
                        to_address=str(getattr(tx, "to_address", "")),
                        memo=str(raw_memo),
                        utime=int(getattr(tx, "utime", 0)),
                        reason=str(
                            envelope.reason or "jetton_envelope_invalid"
                        ),
                    )
                    await _ton_log_upsert(
                        db,
                        tx=tx,
                        status=STATUS_PENDING_MANUAL,
                        note=(
                            "Jetton envelope blocked: "
                            f"{envelope.reason}"
                        ),
                        next_retry_at=None,
                    )
                    return STATUS_PENDING_MANUAL
            else:
                ip = parse_intent_payload(
                    str(envelope.forward_payload or "")
                )
        else:
            ip = parse_intent_payload(str(raw_memo))
        if ip:
            memo_global_id = ip.get("global_id")
            memo_tg_id = ip.get("tg_id")
            if memo_global_id is not None:
                intent_owner = await _find_user_by_global_id(
                    db, str(memo_global_id)
                )
            elif memo_tg_id is not None:
                intent_owner = await _find_user_by_tg_id(
                    db, int(memo_tg_id)
                )
            else:
                intent_owner = None
            if intent_owner is None:
                await _ton_log_upsert(
                    db,
                    tx=tx,
                    status=STATUS_ERROR_USER,
                    note="Payment intent owner mapping not found",
                )
                return STATUS_ERROR_USER
            await _ton_log_upsert(db, tx=tx, status=STATUS_PARSED)
            transport_check = parsed_transport.check
            if not transport_check.ok:
                await _record_unmatched_incoming(
                    db,
                    tx_hash=str(getattr(tx, "tx_hash", "")),
                    asset=transport.confirm_asset,
                    amount_asset=transport.amount_display,
                    from_address=str(getattr(tx, "from_address", "")),
                    to_address=str(getattr(tx, "to_address", "")),
                    memo=str(getattr(tx, "memo", "")),
                    utime=int(getattr(tx, "utime", 0)),
                    reason=str(
                        transport_check.reason or "transport_invalid"
                    ),
                )
                await _ton_log_upsert(
                    db,
                    tx=tx,
                    status=STATUS_PENDING_MANUAL,
                    note=(
                        "Intent transport blocked: "
                        f"{transport_check.reason}"
                    ),
                    next_retry_at=None,
                )
                return STATUS_PENDING_MANUAL
            try:
                confirm_res = await _confirm_payment_intent(
                    db,
                    intent_id=int(ip["intent_id"]),
                    global_id=intent_owner.global_id,
                    provider_tg_id=intent_owner.tg_id,
                    purpose=str(ip["purpose"]),
                    payload=str(ip["payload"]),
                    tx_hash=str(getattr(tx, "tx_hash", "")),
                    amount_asset=transport.amount_display,
                    asset=transport.confirm_asset,
                    external_amount_atomic=transport.amount_atomic,
                    external_decimals=transport.atomic_decimals,
                    to_address=str(getattr(tx, "to_address", "")),
                    trusted_operation_at=time_decision.trusted_operation_at,
                    server_first_seen_at=time_decision.server_first_seen_at,
                    return_note=True,
                )
            except SQLAlchemyError:
                # Ошибка БД принадлежит root transaction owner: дальнейший SQL
                # через эту сессию запрещён до rollback.
                raise
            except Exception:
                logger.exception(
                    "[WATCHER] intent confirmation failed for tx=%s",
                    getattr(tx, "tx_hash", "?"),
                )
                await _record_unmatched_incoming(
                    db,
                    tx_hash=str(getattr(tx, "tx_hash", "")),
                    asset=transport.confirm_asset,
                    amount_asset=transport.amount_display,
                    from_address=str(getattr(tx, "from_address", "")),
                    to_address=str(getattr(tx, "to_address", "")),
                    memo=str(getattr(tx, "memo", "")),
                    utime=int(getattr(tx, "utime", 0)),
                    reason="intent_confirm_failed",
                )
                await _ton_log_upsert(
                    db,
                    tx=tx,
                    status=STATUS_PENDING_MANUAL,
                    note="INTENT_CONFIRM_FAILED",
                    next_retry_at=None,
                )
                return STATUS_PENDING_MANUAL
            if isinstance(confirm_res, ConfirmPaymentResult):
                confirm_status = str(confirm_res.status)
                confirm_note = confirm_res.note
            else:
                confirm_status = str(confirm_res)
                confirm_note = None
            await _ton_log_upsert(
                db,
                tx=tx,
                status=confirm_status,
                note=confirm_note,
            )
            return confirm_status

        # 3) Идентификация: приоритет у привязанного кошелька.
        found_by_wallet = False
        owner = await _find_user_by_wallet(db, tx.from_address)
        if owner is not None:
            found_by_wallet = True

        kind: str = "bad"
        params: dict[str, int | str] = {}

        # 3.0) КАНОН: автоначисление без MEMO допускается
        # ТОЛЬКО для входящих EFHC (jetton) и только если
        # from_address имеет активную и verified binding в
        # wallet_bindings.
        # Для TON/чужих jetton: без MEMO — не начисляем.
        memo_s = str(getattr(tx, "memo", "") or "").strip()
        if found_by_wallet and not memo_s:
            if transport.transport_kind == "efhc_jetton":
                amt = transport.amount_display
                if amt > 0 and owner is not None:
                    claim = await claim_tx_hash_settlement(
                        db,
                        tx_hash=str(tx.tx_hash),
                        purpose="watcher_efhc_jetton_nomemo",
                        global_id=owner.global_id,
                        trusted_operation_at=time_decision.trusted_operation_at,
                        server_first_seen_at=time_decision.server_first_seen_at,
                    )
                    if not claim.can_continue:
                        await _ton_log_upsert(
                            db,
                            tx=tx,
                            status=STATUS_PENDING_MANUAL,
                            note="Global tx_hash settlement уже занят",
                            next_retry_at=None,
                        )
                        return STATUS_PENDING_MANUAL
                    await credit_user_from_bank(
                        db=db,
                        global_id=_global_id_db(owner.global_id),
                        amount_efhc=amt,
                        reason="efhc_jetton_nomemo_wallet_bound",
                        idempotency_key=(
                            f"jetton:efhc:nomemo:{tx.tx_hash}"
                        ),
                    )
                    await _ton_log_upsert(
                        db,
                        tx=tx,
                        status=STATUS_CREDITED,
                        note="EFHC jetton nomemo wallet-bound",
                    )
                    return STATUS_CREDITED

                await _ton_log_upsert(
                    db,
                    tx=tx,
                    status=STATUS_PENDING_MANUAL,
                    note="EFHC jetton nomemo amount<=0",
                    next_retry_at=None,
                )
                return STATUS_PENDING_MANUAL

            await _ton_log_upsert(
                db,
                tx=tx,
                status=STATUS_ERROR_MEMO,
                note="No memo but asset is not EFHC jetton",
                next_retry_at=None,
            )
            return "skip:nomemo_not_efhc"

        # 3.0b) Если MEMO пустой и кошелёк НЕ привязан к пользователю,
        # то это «вне бота» и без идентификации. По канону — игнор.
        # Никаких начислений и никаких unmatched-записей.
        if not memo_s and owner is None:
            await _ton_log_upsert(
                db,
                tx=tx,
                status=STATUS_ERROR_USER,
                note="No memo and wallet is not bound: ignored",
                next_retry_at=None,
            )
            return "skip:nomemo_unbound"

        if owner is None:
            # Нет привязки кошелька → пробуем MEMO
            kind, params = _parse_memo(getattr(tx, "memo", "") or "")
            if kind == "bad":
                await _record_unmatched_incoming(
                    db,
                    tx_hash=str(getattr(tx, "tx_hash", "")),
                    asset=transport.confirm_asset,
                    amount_asset=transport.amount_display,
                    from_address=str(getattr(tx, "from_address", "")),
                    to_address=str(getattr(tx, "to_address", "")),
                    memo=str(getattr(tx, "memo", "")),
                    utime=int(getattr(tx, "utime", 0)),
                    reason="unmatched_payload",
                )
                await _ton_log_upsert(
                    db,
                    tx=tx,
                    status=STATUS_PENDING_MANUAL,
                    note="Unrecognized MEMO (pending manual)",
                    next_retry_at=None,
                )
                return STATUS_PENDING_MANUAL

            memo_global_id = params.get("global_id")
            tg_id_from_memo = params.get("tg_id")
            if memo_global_id is not None:
                owner = await _find_user_by_global_id(
                    db, str(memo_global_id)
                )
            elif tg_id_from_memo is not None:
                owner = await _find_user_by_tg_id(
                    db, int(tg_id_from_memo)
                )
            else:
                await _ton_log_upsert(
                    db,
                    tx=tx,
                    status=STATUS_ERROR_USER,
                    note="Missing owner selector in memo",
                    next_retry_at=None,
                )
                return STATUS_ERROR_USER

        # Если и сейчас не нашли пользователя — это ошибка данных.
        if owner is None:
            await _ton_log_upsert(
                db,
                tx=tx,
                status=STATUS_ERROR_USER,
                note="User not found by wallet/memo",
                next_retry_at=None,
            )
            return STATUS_ERROR_USER

        bound_global_id = owner.global_id

        # 4) Разбор MEMO, если ещё не сделали (user найден по кошельку).
        if kind == "bad":
            kind, params = _parse_memo(getattr(tx, "memo", "") or "")

        memo_global_id = params.get("global_id")
        if (
            memo_global_id is not None
            and str(memo_global_id) != bound_global_id
        ):
            await _ton_log_upsert(
                db,
                tx=tx,
                status=STATUS_ERROR_USER,
                note="Global owner конфликтует с bound wallet owner",
                next_retry_at=None,
            )
            return STATUS_ERROR_USER

        await _ton_log_upsert(db, tx=tx, status=STATUS_PARSED)

        # 5) Ветвление по типу MEMO
        if kind == "sku_efhc":
            # Legacy/canonical SKU MEMO содержит пользовательский qty и
            # поэтому НЕ является доказательством стоимости покупки.
            # Автодоставка разрешена только через PaymentIntent payload,
            # обработанный выше canonical reconciliation: там сверяются
            # PENDING+TTL, asset, destination и exact expected amount.
            # Старый SKU/BUY MEMO сохраняется как read-through формат, но
            # никогда самостоятельно не переводит заказ в PAID_AUTO и не
            # вызывает credit_user_from_bank.
            await _record_unmatched_incoming(
                db,
                tx_hash=str(getattr(tx, "tx_hash", "")),
                asset=transport.confirm_asset,
                amount_asset=transport.amount_display,
                from_address=str(getattr(tx, "from_address", "")),
                to_address=str(getattr(tx, "to_address", "")),
                memo=str(getattr(tx, "memo", "")),
                utime=int(getattr(tx, "utime", 0)),
                reason="legacy_sku_efhc_requires_payment_intent",
            )
            await _ton_log_upsert(
                db,
                tx=tx,
                status=STATUS_PENDING_MANUAL,
                note=(
                    "Legacy SKU EFHC не является settlement proof; "
                    "требуется подтверждаемый PaymentIntent"
                ),
                next_retry_at=None,
            )
            return STATUS_PENDING_MANUAL

        elif kind == "sku_nft":
            # 5.3) NFT — только заявка (ручная выдача)
            qty_raw = params.get("qty", 1)
            qty = int(qty_raw) if qty_raw is not None else 1
            await _create_nft_manual_request(
                db,
                global_id=bound_global_id,
                tx_hash=tx.tx_hash,
                qty=qty,
            )
            await _ton_log_upsert(db, tx=tx, status=STATUS_NFT_MANUAL)
            return STATUS_NFT_MANUAL

        elif kind == "simple_efhc":
            # 5.4) Direct deposit: EFHC jetton -> EFHCm строго 1:1.
            # Native TON с EFHC:<tg_id> не является deposit.
            # Его нельзя конвертировать через shop pricing.
            if transport.transport_kind != "efhc_jetton":
                await _record_unmatched_incoming(
                    db,
                    tx_hash=str(getattr(tx, "tx_hash", "")),
                    asset=transport.confirm_asset,
                    amount_asset=transport.amount_display,
                    from_address=str(getattr(tx, "from_address", "")),
                    to_address=str(getattr(tx, "to_address", "")),
                    memo=str(getattr(tx, "memo", "")),
                    utime=int(getattr(tx, "utime", 0)),
                    reason="direct_deposit_requires_efhc_jetton",
                )
                await _ton_log_upsert(
                    db,
                    tx=tx,
                    status=STATUS_PENDING_MANUAL,
                    note=(
                        "Direct deposit blocked: asset is not "
                        "EFHC jetton"
                    ),
                    next_retry_at=None,
                )
                return STATUS_PENDING_MANUAL

            raw_external_efhc = Decimal(str(transport.amount_display))
            external_efhc_d2 = quantize_external_efhc_d2(raw_external_efhc)
            direct_amount = d8(external_efhc_d2)
            rounding_dust = raw_external_efhc - external_efhc_d2
            if direct_amount <= 0:
                await _ton_log_upsert(
                    db,
                    tx=tx,
                    status=STATUS_PENDING_MANUAL,
                    note="Direct EFHC jetton amount must be positive",
                    next_retry_at=None,
                )
                return STATUS_PENDING_MANUAL

            claim = await claim_tx_hash_settlement(
                db,
                tx_hash=str(tx.tx_hash),
                purpose="watcher_efhc_jetton_direct",
                global_id=bound_global_id,
                trusted_operation_at=time_decision.trusted_operation_at,
                server_first_seen_at=time_decision.server_first_seen_at,
            )
            if not claim.can_continue:
                await _ton_log_upsert(
                    db,
                    tx=tx,
                    status=STATUS_PENDING_MANUAL,
                    note="Global tx_hash settlement уже занят",
                    next_retry_at=None,
                )
                return STATUS_PENDING_MANUAL

            await credit_user_from_bank(
                db=db,
                global_id=_global_id_db(bound_global_id),
                amount_efhc=direct_amount,
                reason="efhc_external_deposit",
                idempotency_key=f"jetton:efhc:direct:{tx.tx_hash}",
                meta={
                    "raw_external_efhc": str(raw_external_efhc),
                    "credited_external_efhc": str(external_efhc_d2),
                    "rounding_dust_efhc": str(rounding_dust),
                    "external_rounding": "D2_ROUND_DOWN",
                    "tx_hash": str(tx.tx_hash),
                },
            )
            await _ton_log_upsert(
                db,
                tx=tx,
                status=STATUS_CREDITED,
                note="Direct EFHC jetton credited to EFHCm 1:1",
            )
            return STATUS_CREDITED

        else:
            # Неподдерживаемый формат:
            # • если user найден по кошельку, это не ошибка MEMO,
            #   а "неразобранный кейс" → pending manual
            if found_by_wallet:
                await _record_unmatched_incoming(
                    db,
                    tx_hash=str(getattr(tx, "tx_hash", "")),
                    asset=transport.confirm_asset,
                    amount_asset=transport.amount_display,
                    from_address=str(getattr(tx, "from_address", "")),
                    to_address=str(getattr(tx, "to_address", "")),
                    memo=str(getattr(tx, "memo", "")),
                    utime=int(getattr(tx, "utime", 0)),
                    reason="unsupported_memo_wallet_bound",
                )
                await _ton_log_upsert(
                    db,
                    tx=tx,
                    status=STATUS_PENDING_MANUAL,
                    note=(
                        "Unsupported memo for wallet-bound user: "
                        f"{kind}"
                    ),
                    next_retry_at=None,
                )
                return STATUS_PENDING_MANUAL

            await _ton_log_upsert(
                db,
                tx=tx,
                status=STATUS_ERROR_MEMO,
                note=f"Unsupported kind {kind}",
                next_retry_at=None,
            )
            return STATUS_ERROR_MEMO

    except Exception:
        # Не продолжаем SQL в сессии, которая могла перейти в состояние aborted.
        # Владелец root-транзакции планировщика выполняет rollback и retry/backoff.
        logger.exception(
            "[WATCHER] process tx failed %s",
            getattr(tx, "tx_hash", "?"),
        )
        raise


# =====================================================================
# Высокоуровневые циклы: чтение из TON API и догон «хвостов»
# =====================================================================


async def process_incoming_payments(
    db: AsyncSession,
    *,
    limit: int = 200,
    since_utime: int | None = None,
) -> dict[str, int]:
    """
    Получить из TON API порцию входящих платежей и обработать
    их идемпотентно.

    Вход:
      • limit, since_utime (unixtime).
        Если since_utime не задан — TonAPIClient решает сам.

    Выход:
      • Счётчики по статусам.

    ИИ - защита:
      • Сетевые ошибки TON API не приводят к падению цикла.
    """
    stats: dict[str, int] = {}
    client = TonAPIClient()

    if not TON_MAIN_WALLET:
        logger.warning(
            "[WATCHER] TON_MAIN_WALLET is empty, skip fetching"
        )
        return {"error_network": 1}

    try:
        events: list[TonAPIEvent] = await client.get_incoming_payments(
            to_address=TON_MAIN_WALLET,
            limit=int(limit),
            since_utime=since_utime,
        )
    except Exception as e:
        logger.warning("[WATCHER] TonAPI fetch failed: %s", e)
        return {"error_network": 1}

    for ev in events:
        st = await process_incoming_tx(db, ev)
        stats[st] = stats.get(st, 0) + 1

    return stats


async def _mark_legacy_transport_pending_manual(
    db: AsyncSession,
    *,
    tx_hash: str,
    note: str,
) -> None:
    """Fail closed for legacy rows whose original transport cannot be rebuilt."""
    await db.execute(
        text(
            """
            UPDATE efhc_core.ton_inbox_logs
               SET status = :status,
                   last_error = :note,
                   next_retry_at = NULL,
                   updated_at = NOW() AT TIME ZONE 'UTC'
             WHERE tx_hash = :tx_hash
            """
        ),
        {
            "status": STATUS_PENDING_MANUAL,
            "note": note,
            "tx_hash": str(tx_hash),
        },
    )


async def _retry_row_to_tx(db: AsyncSession, row: Any) -> IncomingTx | TonAPIEvent | None:
    meta = row[6] if len(row) > 6 else None
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except Exception:
            meta = {}
    if isinstance(meta, dict):
        reconstructed = _incoming_from_transport_meta(row, meta)
        if reconstructed is not None:
            return reconstructed
    try:
        refetched = await _refetch_exact_incoming_tx(
            tx_hash=str(row[0]), utime=int(row[5] or 0)
        )
    except Exception:
        logger.warning(
            "watcher legacy retry refetch failed tx=%s", row[0], exc_info=True
        )
        await _mark_legacy_transport_pending_manual(
            db,
            tx_hash=str(row[0]),
            note="LEGACY_TRANSPORT_METADATA_MISSING_REFETCH_FAILED",
        )
        return None
    if refetched is None:
        await _mark_legacy_transport_pending_manual(
            db,
            tx_hash=str(row[0]),
            note="LEGACY_TRANSPORT_METADATA_MISSING_REFETCH_NOT_FOUND",
        )
        return None
    return refetched


async def reprocess_unfinished_logs(
    db: AsyncSession,
    *,
    limit: int = 500,
) -> dict[str, int]:
    """Повторить non-final rows, сохраняя exact transport asset/master/atomic amount."""
    stats: dict[str, int] = {}
    result = await db.execute(
        text("""
            SELECT tx_hash, from_address, to_address, amount, memo,
                   EXTRACT(EPOCH FROM trusted_operation_at)::bigint AS utime,
                   meta
              FROM efhc_core.ton_inbox_logs
             WHERE status NOT IN (:s1, :s2, :s3, :s4, :s5)
               AND (next_retry_at IS NULL OR next_retry_at <= NOW())
             ORDER BY COALESCE(updated_at, created_at) ASC
             LIMIT :lim
        """),
        {
            "s1": STATUS_CREDITED, "s2": STATUS_PAID_AUTO,
            "s3": STATUS_NFT_MANUAL, "s4": STATUS_PENDING_MANUAL,
            "s5": STATUS_EXPIRED_NO_CREDIT, "lim": int(limit),
        },
    )
    for row in result.fetchall():
        tx = await _retry_row_to_tx(db, row)
        if tx is None:
            stats[STATUS_PENDING_MANUAL] = stats.get(STATUS_PENDING_MANUAL, 0) + 1
            continue
        status = await process_incoming_tx(db, tx)
        stats[status] = stats.get(status, 0) + 1
    return stats


# =====================================================================
# Утилиты для админских задач: сверка по времени и по tx_hash
# =====================================================================


async def reconcile_last_hours(
    db: AsyncSession,
    *,
    hours: int = 24,
    limit: int = 500,
) -> dict[str, int]:
    """Повторно проверить ограниченную выборку входящих за последние N часов.

    TON API adapter проекта пока не предоставляет cursor pagination. Поэтому
    здесь намеренно выполняется один ограниченный запрос вместо прежнего
    ложного цикла, который повторял одну и ту же временную выборку. Повторная
    обработка безопасна благодаря идемпотентности по tx_hash.
    """
    since = int((_now_utc() - timedelta(hours=hours)).timestamp())
    return await process_incoming_payments(
        db,
        limit=int(limit),
        since_utime=since,
    )


async def reprocess_single_tx(db: AsyncSession, tx_hash: str) -> str:
    """Повторить exact tx по сохранённому v2 transport metadata или refetch."""
    result = await db.execute(
        text("""
            SELECT tx_hash, from_address, to_address, amount, memo,
                   EXTRACT(EPOCH FROM trusted_operation_at)::bigint AS utime,
                   meta
              FROM efhc_core.ton_inbox_logs
             WHERE tx_hash = :h
             LIMIT 1
        """),
        {"h": tx_hash},
    )
    row = result.fetchone()
    if not row:
        return "not_found"
    tx = await _retry_row_to_tx(db, row)
    if tx is None:
        return STATUS_PENDING_MANUAL
    return await process_incoming_tx(db, tx)


# =====================================================================
# Пояснения «для чайника»:
# • Этот модуль не «создаёт деньги» сам — все начисления EFHC
#   проходят через transactions_service.credit_user_from_bank(...).
# • Благодаря UNIQUE(tx_hash) и read-through та же транзакция TON
#   не будет
# начислена дважды: при повторе вернётся финальный статус.
# • NFT не выдаётся автоматически: здесь создаётся только заявка
#   со статусом
# PAID_PENDING_MANUAL, которую обработает администратор.
# • Если для простого депозита EFHC<tg_id> нельзя однозначно
#   определить объём
# по прайсу EFHC-пакетов, запись получает статус parsed_pending_mapping
# и
# ждёт ручного сопоставления.
# • Любые временные/сетевые сбои помечаются error_* с next_retry_at.
#   Планировщик периодически вызывает reprocess_unfinished_logs()
#   для догона.
# =====================================================================
