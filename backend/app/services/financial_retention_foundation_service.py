"""Простая owner-approved политика financial-history retention.

Цикл 1777 отменяет physical monthly partitioning как неоправданно
сложный механизм для первого production launch. Этот модуль намеренно
НЕ выполняет DELETE и не меняет schema. Он фиксирует age-based policy
и строит чистый cleanup plan для следующего staged runtime-cycle.

Инварианты:
- external financial execution: trusted age < 180 days;
- trusted age >= 180 days: EXPIRED / NO CREDIT до replay/money mutation;
- detailed history deletion cutoff: age >= 370 days;
- cleanup запускается только когда history достигает age >= 400 days;
- после 370 days status PENDING/unresolved/manual-review не даёт
  отдельной retention-защиты: запись уже старше execution window;
- current balances/BANK/current ownership этим контуром не удаляются.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

FINANCIAL_EXECUTION_DAYS = 180
FINANCIAL_HISTORY_DELETE_AGE_DAYS = 370
FINANCIAL_HISTORY_CLEANUP_TRIGGER_DAYS = 400

if not (
    FINANCIAL_EXECUTION_DAYS
    < FINANCIAL_HISTORY_DELETE_AGE_DAYS
    < FINANCIAL_HISTORY_CLEANUP_TRIGGER_DAYS
):
    raise RuntimeError("INVALID_SIMPLE_FINANCIAL_RETENTION_POLICY")

SIMPLE_FINANCIAL_HISTORY_TABLES = (
    "efhc_transfers_log",
    "payment_intents",
    "shop_orders",
    "withdraw_requests",
    "withdraw_outcome_events",
    "ton_inbox_logs",
)

# Дочерняя запись удаляется раньше родителя, чтобы сохранить существующий FK:
# Связь FK: withdraw_outcome_events.withdraw_request_id -> withdraw_requests.id.
SIMPLE_FINANCIAL_HISTORY_DELETE_ORDER = (
    "withdraw_outcome_events",
    "efhc_transfers_log",
    "payment_intents",
    "shop_orders",
    "ton_inbox_logs",
    "withdraw_requests",
)

FINANCIAL_HISTORY_RETENTION_TIMESTAMP = "created_at"


@dataclass(frozen=True, slots=True)
class SimpleFinancialRetentionPlan:
    """Чистый план; фактический DELETE реализуется и включается отдельно."""

    cleanup_required: bool
    delete_before: datetime
    trigger_before: datetime
    tables_in_delete_order: tuple[str, ...]
    status_independent: bool = True


def require_utc(value: datetime) -> datetime:
    """Принять только timezone-aware UTC без конвертации."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("RETENTION_TIME_MUST_BE_AWARE_UTC")
    if value.utcoffset() != timedelta(0):
        raise ValueError("RETENTION_TIME_MUST_BE_UTC")
    return value



def financial_execution_record_eligible(
    operation_at: datetime,
    *,
    now: datetime,
) -> bool:
    """Вернуть True только пока возраст операции строго меньше 180 суток."""

    operation = require_utc(operation_at)
    current = require_utc(now)
    return operation > current - timedelta(days=FINANCIAL_EXECUTION_DAYS)

def financial_history_delete_cutoff(now: datetime) -> datetime:
    """Удалять history с created_at <= now - 370 days."""

    return require_utc(now) - timedelta(days=FINANCIAL_HISTORY_DELETE_AGE_DAYS)


def financial_history_cleanup_trigger_cutoff(now: datetime) -> datetime:
    """Запускать cleanup при наличии history age >= 400 days."""

    return require_utc(now) - timedelta(
        days=FINANCIAL_HISTORY_CLEANUP_TRIGGER_DAYS
    )


def financial_history_record_delete_eligible(
    created_at: datetime,
    *,
    now: datetime,
) -> bool:
    """Проверка только по возрасту; статус намеренно не учитывается."""

    created = require_utc(created_at)
    return created <= financial_history_delete_cutoff(now)


def financial_history_cleanup_required(
    oldest_created_at: datetime | None,
    *,
    now: datetime,
) -> bool:
    """Определить необходимость уборки по самой старой записи истории."""

    require_utc(now)
    if oldest_created_at is None:
        return False
    oldest = require_utc(oldest_created_at)
    return oldest <= financial_history_cleanup_trigger_cutoff(now)


def build_simple_financial_retention_plan(
    *,
    now: datetime,
    oldest_created_at: datetime | None,
) -> SimpleFinancialRetentionPlan:
    """Сформировать чистый план без выполнения DELETE."""

    return SimpleFinancialRetentionPlan(
        cleanup_required=financial_history_cleanup_required(
            oldest_created_at,
            now=now,
        ),
        delete_before=financial_history_delete_cutoff(now),
        trigger_before=financial_history_cleanup_trigger_cutoff(now),
        tables_in_delete_order=SIMPLE_FINANCIAL_HISTORY_DELETE_ORDER,
    )


def tx_hash_cleanup_cutoff(now: datetime) -> datetime:
    """Строгая owner-approved граница replay cleanup: age >= 180 days."""

    return require_utc(now) - timedelta(days=FINANCIAL_EXECUTION_DAYS)


def tx_hash_cleanup_eligible(
    trusted_operation_at: datetime,
    *,
    now: datetime,
) -> bool:
    """Маркер можно очищать только при доверенном возрасте >= 180 суток."""

    trusted = require_utc(trusted_operation_at)
    return trusted <= tx_hash_cleanup_cutoff(now)


__all__ = [
    "FINANCIAL_EXECUTION_DAYS",
    "FINANCIAL_HISTORY_CLEANUP_TRIGGER_DAYS",
    "FINANCIAL_HISTORY_DELETE_AGE_DAYS",
    "FINANCIAL_HISTORY_RETENTION_TIMESTAMP",
    "SIMPLE_FINANCIAL_HISTORY_DELETE_ORDER",
    "SIMPLE_FINANCIAL_HISTORY_TABLES",
    "SimpleFinancialRetentionPlan",
    "build_simple_financial_retention_plan",
    "financial_execution_record_eligible",
    "financial_history_cleanup_required",
    "financial_history_cleanup_trigger_cutoff",
    "financial_history_delete_cutoff",
    "financial_history_record_delete_eligible",
    "require_utc",
    "tx_hash_cleanup_cutoff",
    "tx_hash_cleanup_eligible",
]
