"""Fail-closed окно первичной исполнимости внешней финансовой операции.

Канон владельца:
- доверенное время внешней операции обязательно;
- server first-seen является второй независимой временной границей;
- первичное изменение денег разрешено только раньше 10 суток;
- ровно 10 суток и старше — EXPIRED / NO CREDIT;
- более новое first-seen никогда не «омолаживает» старую операцию;
- replay/idempotency проверяется только после успешной временной проверки.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

from app.lib.time import utcnow

FINANCIAL_EXECUTION_WINDOW_DAYS: Final[int] = 10
FINANCIAL_EXECUTION_WINDOW: Final[timedelta] = timedelta(
    days=FINANCIAL_EXECUTION_WINDOW_DAYS
)

CODE_OK: Final[str] = "FINANCIAL_TIME_OK"
CODE_TRUSTED_TIME_MISSING: Final[str] = "TRUSTED_OPERATION_TIME_MISSING"
CODE_FIRST_SEEN_MISSING: Final[str] = "SERVER_FIRST_SEEN_TIME_MISSING"
CODE_TRUSTED_TIME_FUTURE: Final[str] = "TRUSTED_OPERATION_TIME_IN_FUTURE"
CODE_FIRST_SEEN_FUTURE: Final[str] = "SERVER_FIRST_SEEN_TIME_IN_FUTURE"
CODE_FIRST_SEEN_BEFORE_TRUSTED: Final[str] = (
    "SERVER_FIRST_SEEN_BEFORE_TRUSTED_OPERATION"
)
CODE_EXECUTION_EXPIRED: Final[str] = "FINANCIAL_EXECUTION_WINDOW_EXPIRED"
CODE_FIRST_SEEN_EXPIRED: Final[str] = "SERVER_FIRST_SEEN_WINDOW_EXPIRED"


@dataclass(frozen=True, slots=True)
class FinancialExecutionDecision:
    """Результат двойной проверки времени перед денежным settlement."""

    allowed: bool
    code: str
    checked_at: datetime
    trusted_operation_at: datetime | None
    server_first_seen_at: datetime | None

    @property
    def expired(self) -> bool:
        """Отличить окончательное истечение от временной аномалии."""
        return self.code in {
            CODE_EXECUTION_EXPIRED,
            CODE_FIRST_SEEN_EXPIRED,
        }


class FinancialExecutionWindowError(RuntimeError):
    """Fail-closed ошибка попытки settlement вне разрешённого окна."""

    def __init__(self, decision: FinancialExecutionDecision) -> None:
        self.decision = decision
        super().__init__(decision.code)


def _aware_utc(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is None or value.utcoffset() is None:
        return None
    return value.astimezone(UTC)


def trusted_datetime_from_unix(value: int | str | None) -> datetime | None:
    """Преобразовать trusted unix-time без догадок и локальной timezone."""
    try:
        raw = int(value or 0)
    except (TypeError, ValueError):
        return None
    if raw <= 0:
        return None
    try:
        return datetime.fromtimestamp(raw, UTC)
    except (OverflowError, OSError, ValueError):
        return None


def replay_retention_deadline(trusted_operation_at: datetime) -> datetime:
    """Последний момент, до которого нужен ordinary replay guard."""
    trusted = _aware_utc(trusted_operation_at)
    if trusted is None:
        raise ValueError("trusted_operation_at must be timezone-aware")
    return trusted + FINANCIAL_EXECUTION_WINDOW


def validate_external_financial_execution(
    *,
    trusted_operation_at: datetime | None,
    server_first_seen_at: datetime | None,
    now: datetime | None = None,
) -> FinancialExecutionDecision:
    """Проверить двойную временную границу до replay и money mutation."""
    checked_at = _aware_utc(now) if now is not None else _aware_utc(utcnow())
    if checked_at is None:
        raise RuntimeError("canonical UTC clock returned naive timestamp")

    trusted = _aware_utc(trusted_operation_at)
    first_seen = _aware_utc(server_first_seen_at)

    if trusted is None:
        return FinancialExecutionDecision(
            False,
            CODE_TRUSTED_TIME_MISSING,
            checked_at,
            None,
            first_seen,
        )
    if first_seen is None:
        return FinancialExecutionDecision(
            False,
            CODE_FIRST_SEEN_MISSING,
            checked_at,
            trusted,
            None,
        )
    if trusted > checked_at:
        return FinancialExecutionDecision(
            False,
            CODE_TRUSTED_TIME_FUTURE,
            checked_at,
            trusted,
            first_seen,
        )
    if first_seen > checked_at:
        return FinancialExecutionDecision(
            False,
            CODE_FIRST_SEEN_FUTURE,
            checked_at,
            trusted,
            first_seen,
        )
    if first_seen < trusted:
        return FinancialExecutionDecision(
            False,
            CODE_FIRST_SEEN_BEFORE_TRUSTED,
            checked_at,
            trusted,
            first_seen,
        )
    if checked_at - trusted >= FINANCIAL_EXECUTION_WINDOW:
        return FinancialExecutionDecision(
            False,
            CODE_EXECUTION_EXPIRED,
            checked_at,
            trusted,
            first_seen,
        )
    if checked_at - first_seen >= FINANCIAL_EXECUTION_WINDOW:
        return FinancialExecutionDecision(
            False,
            CODE_FIRST_SEEN_EXPIRED,
            checked_at,
            trusted,
            first_seen,
        )
    return FinancialExecutionDecision(
        True,
        CODE_OK,
        checked_at,
        trusted,
        first_seen,
    )


def require_external_financial_execution(
    *,
    trusted_operation_at: datetime | None,
    server_first_seen_at: datetime | None,
    now: datetime | None = None,
) -> FinancialExecutionDecision:
    """Вернуть решение либо fail-closed исключение до replay claim."""
    decision = validate_external_financial_execution(
        trusted_operation_at=trusted_operation_at,
        server_first_seen_at=server_first_seen_at,
        now=now,
    )
    if not decision.allowed:
        raise FinancialExecutionWindowError(decision)
    return decision


__all__ = [
    "CODE_EXECUTION_EXPIRED",
    "CODE_FIRST_SEEN_BEFORE_TRUSTED",
    "CODE_FIRST_SEEN_EXPIRED",
    "CODE_FIRST_SEEN_FUTURE",
    "CODE_FIRST_SEEN_MISSING",
    "CODE_OK",
    "CODE_TRUSTED_TIME_FUTURE",
    "CODE_TRUSTED_TIME_MISSING",
    "FINANCIAL_EXECUTION_WINDOW",
    "FINANCIAL_EXECUTION_WINDOW_DAYS",
    "FinancialExecutionDecision",
    "FinancialExecutionWindowError",
    "replay_retention_deadline",
    "require_external_financial_execution",
    "trusted_datetime_from_unix",
    "validate_external_financial_execution",
]
