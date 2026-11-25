"""Pydantic-схемы для модуля Shop Orders.

В этом файле только формы данных и валидация.
Денежные строки наружу: str с d8 (Decimal, ROUND_DOWN).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, cast

from app.schemas.common_schemas import (
    BalancePair,
    CursorPage,
    EfhcBaseModel,
    IdempotencyContract,
    OkMeta,
    d8_str,
)
from app.schemas.id_schemas import ApiLifetimeId
from pydantic import Field, field_validator

OrderType = Literal["EFHC_PACKAGE", "NFT_VIP", "GOOD"]


OrderStatus = Literal[
    "PENDING",
    "PAID_AUTO",
    "PAID_PENDING_MANUAL",
    "APPROVED",
    "REJECTED",
    "CANCELLED",
]


PaymentMode = Literal["TON", "EFHC"]


class OrderRow(EfhcBaseModel):
    """Короткая строка заказа для листинга."""

    order_id: ApiLifetimeId = Field(..., description="ID заказа")
    global_id: str = Field(..., pattern=r"^[0-9]{10}$")
    order_type: OrderType = Field(..., description="Тип заказа")
    title: str = Field(
        ...,
        max_length=140,
        description="Заголовок/название позиции",
    )
    status: OrderStatus = Field(..., description="Статус заказа")
    payment_mode: PaymentMode = Field(..., description="Способ оплаты")
    amount_ton: str | None = Field(
        None,
        description="Сумма TON (str, d8) при оплате TON",
    )
    amount_efhc: str | None = Field(
        None,
        description="Сумма EFHC (str, d8) при оплате EFHC",
    )
    tx_hash: str | None = Field(
        None,
        description="TON tx_hash, если применимо",
    )
    created_at: datetime = Field(..., description="Когда создан (UTC)")
    updated_at: datetime | None = Field(
        None,
        description="Когда обновлён (UTC)",
    )

    @field_validator("amount_ton", "amount_efhc", mode="before")
    def _q8(cls, v: Any) -> str | None:
        if v is None:
            return None
        return cast(str, d8_str(v))


MyOrdersPage = CursorPage[OrderRow]


class OrderDetailsOut(EfhcBaseModel):
    """Карточка заказа для экрана деталей."""

    meta: OkMeta = Field(default_factory=OkMeta)
    order_id: ApiLifetimeId
    global_id: str
    order_type: OrderType
    title: str
    description: str | None
    status: OrderStatus
    payment_mode: PaymentMode
    amount_ton: str | None
    amount_efhc: str | None
    tx_hash: str | None
    memo: str | None = Field(
        None,
        description="Ожидаемый MEMO для строгого парсинга",
    )
    to_address: str | None = Field(
        None,
        description="TON адрес проекта для оплаты",
    )
    expires_at: datetime | None = Field(
        None,
        description="Срок действия инвойса (если используется)",
    )

    @field_validator("amount_ton", "amount_efhc", mode="before")
    def _q8(cls, v: Any) -> str | None:
        if v is None:
            return None
        return cast(str, d8_str(v))


class TonInvoiceCreateIn(IdempotencyContract):
    """Создание TON-инвойса (денежный POST)."""

    item_id: ApiLifetimeId = Field(
        ...,
        description="ID позиции (EFHC-пакет/NFT)",
    )
    quantity: int = Field(
        ...,
        ge=1,
        le=1000,
        description="Количество (для пакетов EFHC)",
    )


class TonInvoiceCreateOut(EfhcBaseModel):
    """Результат создания TON-инвойса."""

    meta: OkMeta = Field(default_factory=OkMeta)
    order_id: ApiLifetimeId = Field(..., description="ID заказа")
    order_status: OrderStatus = Field(
        ...,
        description="Ожидаемый статус (обычно PENDING)",
    )
    to_address: str = Field(..., description="TON адрес проекта")
    amount_ton: str = Field(..., description="Сумма TON (str, d8)")
    memo: str = Field(..., description="Строгий MEMO")
    expires_at: datetime | None = Field(
        None,
        description="Срок действия инвойса (если применяется)",
    )

    @field_validator("amount_ton", mode="before")
    def _q8(cls, v: Any) -> str:
        return cast(str, d8_str(v))


class EfhcOrderPurchaseIn(IdempotencyContract):
    """Покупка витринного товара за EFHC (GOOD)."""

    item_id: ApiLifetimeId = Field(..., description="ID позиции типа GOOD")
    quantity: int = Field(
        ...,
        ge=1,
        le=1000,
        description="Количество (>0)",
    )


class EfhcOrderPurchaseOut(EfhcBaseModel):
    """Результат покупки за EFHC."""

    meta: OkMeta = Field(default_factory=OkMeta)
    order_id: ApiLifetimeId = Field(..., description="ID заказа")
    order_status: OrderStatus = Field(
        ...,
        description="Статус заказа после списания",
    )
    charged_efhc: str = Field(
        ...,
        description="Сколько EFHC списано (str, d8)",
    )
    balances_after: BalancePair = Field(
        ...,
        description="Баланс пользователя после операции",
    )

    @field_validator("charged_efhc", mode="before")
    def _q8(cls, v: Any) -> str:
        return cast(str, d8_str(v))


class MyOrdersQueryIn(EfhcBaseModel):
    """Параметры курсорной пагинации для «Мои заказы»."""

    next_cursor: str | None = Field(
        None,
        description="Курсор следующей страницы (base64)",
    )
    limit: int | None = Field(
        None,
        ge=1,
        le=200,
        description="Размер страницы",
    )
    type: OrderType | None = Field(
        None,
        description="Фильтр по типу заказа",
    )
    status: OrderStatus | None = Field(
        None,
        description="Фильтр по статусу",
    )


class OrdersSyncOut(EfhcBaseModel):
    """Результат принудительной синхронизации витрины/заказов."""

    meta: OkMeta = Field(default_factory=OkMeta)
    refreshed: int = Field(
        ...,
        ge=0,
        description="Сколько записей освежено",
    )
    errors: int = Field(
        ...,
        ge=0,
        description="Сколько ошибок при синхронизации",
    )
    note: str | None = Field(
        None,
        description="Например: partial/rate_limited/ok",
    )
