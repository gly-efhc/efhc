# backend/app/contracts/withdraw_contract.py

from __future__ import annotations

from typing import Protocol

from app.schemas.withdraw_schemas import (
    WithdrawCreateIn,
    WithdrawListOut,
    WithdrawPublicOut,
)


class WithdrawContract(Protocol):
    """Интерфейс withdraw-контура.

    Учёт заявок + hold/refund через transactions_service.
    """

    async def request_withdraw(
        self,
        global_id: int,
        payload: WithdrawCreateIn,
        idempotency_key: str,
    ) -> WithdrawPublicOut:
        """Создаёт заявку на вывод и выполняет hold."""

    async def list_withdraws(
        self,
        global_id: int,
        limit: int,
        cursor: str | None,
    ) -> WithdrawListOut:
        """Возвращает список заявок пользователя."""
