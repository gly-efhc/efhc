# backend/app/schemas/withdraw_schemas.py
# ----------------------------------------------------------------------
# Схемы вывода EFHC (Jetton): заявки, модерация, витрины.
# ----------------------------------------------------------------------

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, cast

from app.deps import d8
from app.identity.api_contract import ApiExternalGlobalId
from app.schemas.common_schemas import (
    CursorPage,
    EfhcBaseModel,
    OkMeta,
    StrictIn,
    d8_str,
)
from app.schemas.id_schemas import ApiLifetimeId
from pydantic import (
    ConfigDict,
    Field,
    field_validator,
)

WithdrawStatus = str


def _is_lite_ton_address(addr: str) -> bool:
    """Валидация TON-адреса через общий TonConnect parser."""
    if not isinstance(addr, str) or not addr:
        return False
    try:
        from app.services.tonconnect_proof_service import (
            parse_ton_address,
        )

        parse_ton_address(str(addr).strip())
        return True
    except Exception:
        return False


class WithdrawCreateIn(StrictIn):
    """Создание заявки на вывод EFHC (Idempotency-Key)."""

    amount_efhc: Decimal = Field(
        ...,
        gt=Decimal("0"),
        max_digits=30,
        decimal_places=10,
        description="Сумма EFHC к выводу (>0). Округление вниз до 8.",
    )
    dest_ton_address: str = Field(
        ...,
        min_length=48,
        max_length=68,
        description="Целевой TON-адрес для перевода EFHC (Jetton).",
    )
    memo: str | None = Field(
        None,
        max_length=140,
        description="Необязательное примечание пользователя.",
    )
    client_nonce: str | None = Field(
        None,
        min_length=1,
        max_length=128,
        description="Доп. предохранитель, не заменяет Idempotency-Key.",
    )

    @field_validator("amount_efhc", mode="before")
    def _q8_amount(cls, v: Any) -> Decimal:
        return cast(Decimal, d8(v))

    @field_validator("dest_ton_address")
    def _check_addr(cls, v: str) -> str:
        if not _is_lite_ton_address(v):
            raise ValueError("Некорректный формат TON-адреса.")
        return v


class WithdrawPublicOut(EfhcBaseModel):
    """Публичная витрина заявки на вывод."""

    meta: OkMeta = Field(default_factory=OkMeta)
    id: ApiLifetimeId
    global_id: ApiExternalGlobalId
    status: str

    amount_efhc: str
    dest_ton_address: str
    memo: str | None = None

    tx_hash: str | None = None
    fee_efhc: str | None = None
    operator_global_id: ApiExternalGlobalId | None = None

    created_at: datetime
    updated_at: datetime

    @field_validator("amount_efhc", "fee_efhc", mode="before")
    def _q8_str(cls, v: Any | None) -> str | None:
        if v is None:
            return None
        return cast(str, d8_str(v))

    model_config = ConfigDict(extra="ignore")


WithdrawListOut = CursorPage[WithdrawPublicOut]


class AdminWithdrawTakeIn(StrictIn):
    """Взять заявку в обработку (UNDER_REVIEW)."""

    operator_global_id: ApiExternalGlobalId = Field(
        ...,
        description="global_id оператора, взявшего в работу.",
    )


class AdminWithdrawDecisionIn(StrictIn):
    """Одобрить или отклонить заявку."""

    approved: bool = Field(
        ...,
        description="True - одобрить; False - отклонить.",
    )
    operator_global_id: ApiExternalGlobalId = Field(..., description="global_id оператора.")
    reason: str | None = Field(
        None,
        max_length=240,
        description="Причина/комментарий.",
    )


class AdminWithdrawMarkPaidIn(StrictIn):
    """Отметить заявку как PAID (денежный POST: Idempotency-Key)."""

    operator_global_id: ApiExternalGlobalId = Field(..., description="global_id оператора.")
    tx_hash: str = Field(
        ...,
        min_length=16,
        max_length=128,
        description="Хэш Jetton-транзакции выплаты EFHC.",
    )
    fee_efhc: Decimal | None = Field(
        None,
        description="Комиссия EFHC, если применима (>=0).",
    )
    admin_memo: str | None = Field(
        None,
        max_length=240,
        description="Комментарий оператора/админа.",
    )
    client_nonce: str | None = Field(
        None,
        description="Доп. предохранитель идемпотентности.",
    )

    @field_validator("fee_efhc", mode="before")
    def _q8_fee(cls, v: Decimal | None) -> Decimal | None:
        return None if v is None else d8(v)
