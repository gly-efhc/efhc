from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.services import tasks_service

pytestmark = pytest.mark.asyncio


class _ScalarResult:
    def __init__(self, value: object) -> None:
        self._value = value

    def scalar_one_or_none(self) -> object:
        return self._value


class _PaidSubmissionDb:
    def __init__(self) -> None:
        self.task = SimpleNamespace(active=True, bonus_efhc=Decimal("1"))
        self.submission = SimpleNamespace(
            id=41,
            status="approved",
            paid=True,
            paid_tx_id=71,
            bonus_amount_efhc=Decimal("2.50000000"),
        )
        self.commit = AsyncMock()

    async def get(self, model: object, task_id: int) -> object:
        _ = model, task_id
        return self.task

    async def execute(self, statement: object) -> _ScalarResult:
        _ = statement
        return _ScalarResult(self.submission)


async def test_paid_submission_returns_without_second_credit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _PaidSubmissionDb()
    get_balances = AsyncMock(
        return_value=(
            Decimal("100.00000000"),
            Decimal("12.50000000"),
        )
    )
    credit = AsyncMock(side_effect=AssertionError("double credit"))
    monkeypatch.setattr(
        tasks_service.transactions_service,
        "get_user_balances_snapshot",
        get_balances,
    )
    monkeypatch.setattr(
        tasks_service,
        "_resolve_task_write_owner",
        AsyncMock(
            return_value=SimpleNamespace(
                global_id=2001,
                provider_tg_id=1001,
            )
        ),
    )
    monkeypatch.setattr(
        tasks_service.transactions_service,
        "credit_user_bonus_from_bank",
        credit,
    )

    result = await tasks_service.claim_task_bonus(
        db,  # type: ignore[arg-type]
        global_id=2001,
        task_id=7,
        idempotency_key="task-paid-replay-1557",
    )

    assert result.ok is True
    assert result.detail == "already_paid"
    assert result.bonus_efhc == Decimal("2.50000000")
    credit.assert_not_awaited()
    db.commit.assert_not_awaited()
    get_balances.assert_awaited_once_with(db, global_id=2001)
