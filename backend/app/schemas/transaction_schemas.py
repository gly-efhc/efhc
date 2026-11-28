# backend/app/schemas/transaction_schemas.py
# ----------------------------------------------------------------------
# Pydantic-схемы для денежных операций и журнала efhc_transfers_log.
# ----------------------------------------------------------------------

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from app.schemas.common_schemas import (
    CursorPage,
    EfhcBaseModel,
    IdempotencyContract,
    OkMeta,
    d8_str,
)
from app.schemas.id_schemas import ApiDatabaseGlobalId, ApiLifetimeId
from pydantic import (
    ConfigDict,
    Field,
    field_validator,
)


class TransferLogRow(EfhcBaseModel):
    """Витрина одной записи из efhc_transfers_log."""

    id: ApiLifetimeId = Field(..., description="Первичный ключ записи.")
    global_id: ApiDatabaseGlobalId = Field(
        ...,
        description="Канонический идентификатор владельца.",
    )
    amount_efhc: str = Field(
        ...,
        description="Сумма операции (str, 8).",
    )
    direction: str = Field(..., description="credit или debit.")
    balance_type: str = Field(..., description="main или bonus.")
    reason: str = Field(..., description="Причина/контекст операции.")
    idempotency_key: str = Field(..., description="Уникальный ключ.")
    processed_with_bank_deficit: bool = Field(
        False,
        description="True, если операция прошла при дефиците банка.",
    )
    extra_info: dict[str, Any] | None = Field(
        None,
        description="Произвольные метаданные (например SKU/TX).",
    )
    created_at: datetime = Field(..., description="Время фиксации.")

    model_config = ConfigDict(extra="ignore")


TransfersPage = CursorPage[TransferLogRow]


class AdminCreditUserIn(IdempotencyContract):
    """Эмиссия из банка пользователю (Idempotency-Key)."""

    global_id: ApiDatabaseGlobalId = Field(
        ...,
        description="Канонический идентификатор пользователя.",
    )
    amount_efhc: Decimal = Field(
        ...,
        description="Сумма EFHC для начисления пользователю.",
    )
    reason: str = Field(
        "emission",
        min_length=1,
        max_length=64,
        description="Причина (по умолчанию 'emission').",
    )
    note: str | None = Field(
        None,
        description="Короткая приметка для журнала/админки.",
    )


class AdminDebitUserIn(IdempotencyContract):
    """Списание у пользователя в банк (Idempotency-Key)."""

    global_id: ApiDatabaseGlobalId = Field(
        ...,
        description="Канонический идентификатор пользователя.",
    )
    amount_efhc: Decimal = Field(
        ...,
        description="Сумма EFHC для списания в банк.",
    )
    balance_type: str = Field(
        "main",
        description="С какого баланса списывать (main|bonus).",
    )
    reason: str = Field(
        "burn",
        min_length=1,
        max_length=64,
        description="Причина (по умолчанию 'burn').",
    )
    note: str | None = Field(
        None,
        description="Короткая приметка для журнала/админки.",
    )


class ExchangeKwhToEfhsIn(IdempotencyContract):
    """Конвертация kWh в EFHC 1:1 (Idempotency-Key)."""

    global_id: ApiDatabaseGlobalId | None = Field(
        None,
        description=(
            "Канонический owner; self route может взять из auth."
        ),
    )
    amount_kwh: Decimal | None = Field(
        None,
        description="Сколько kWh обменять на EFHC 1:1.",
    )
    exchange_all: bool = Field(
        False,
        description="Если True - игнорируем amount_kwh и меняем всё.",
    )


class TransactionResultOut(EfhcBaseModel):
    """Результат денежной операции (эмиссия/списание/обмен)."""

    meta: OkMeta = Field(default_factory=OkMeta)
    log_id: ApiLifetimeId = Field(
        ...,
        description="ID записи в efhc_transfers_log.",
    )
    idempotency_key: str = Field(..., description="Эхо ключа.")
    direction: str
    balance_type: str
    reason: str
    amount_efhc: str = Field(
        ...,
        description="Сумма операции (str, 8).",
    )
    processed_with_bank_deficit: bool = Field(
        False,
        description="True, если операция прошла при дефиците банка.",
    )

    global_id: ApiDatabaseGlobalId
    main_balance: str
    bonus_balance: str
    available_kwh: str
    total_generated_kwh: str
    created_at: datetime

    @field_validator(
        "amount_efhc",
        "main_balance",
        "bonus_balance",
        "available_kwh",
        "total_generated_kwh",
        mode="before",
    )
    def _q8(cls, v: Any) -> str:
        return str(d8_str(v))

    model_config = ConfigDict(extra="ignore")


class TransfersQueryIn(EfhcBaseModel):
    """Фильтры/курсоры для листинга efhc_transfers_log."""

    next_cursor: str | None = Field(
        None,
        description="Курсор следующей страницы (base64).",
    )
    limit: int | None = Field(
        None,
        description="Размер страницы (1..200).",
    )

    global_id: ApiDatabaseGlobalId | None = Field(
        None,
        description="Фильтр по global_id (только админ).",
    )
    direction: str | None = Field(
        None,
        description="credit | debit.",
    )
    balance_type: str | None = Field(
        None,
        description="main | bonus.",
    )
    reason: str | None = Field(
        None,
        description="Подстрока/точное совпадение причины.",
    )
    idempotency_key: str | None = Field(
        None,
        description="Фильтр по ключу идемпотентности.",
    )
    date_from: datetime | None = Field(
        None,
        description="Нижняя граница created_at.",
    )
    date_to: datetime | None = Field(
        None,
        description="Верхняя граница created_at.",
    )


class TransactionsSyncOut(EfhcBaseModel):
    """Результат служебной синхронизации (догон/диагностика)."""

    meta: OkMeta = Field(default_factory=OkMeta)
    refreshed: int = Field(..., ge=0, description="Сколько освежено.")
    errors: int = Field(..., ge=0, description="Сколько ошибок.")
    note: str | None = Field(
        None,
        description="Короткая приметка ('ok'/'partial').",
    )

    model_config = ConfigDict(extra="ignore")
