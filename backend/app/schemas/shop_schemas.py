# backend/app/schemas/shop_schemas.py
# ----------------------------------------------------------------------
# Pydantic-схемы: каталог, покупка за EFHC, TON-интент, NFT.
# внешние заказы и списки.
# ----------------------------------------------------------------------

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, cast

from app.deps import d8
from app.schemas.common_schemas import CursorPage, EfhcBaseModel
from app.schemas.id_schemas import ApiLifetimeId
from pydantic import (
    ConfigDict,
    Field,
    field_validator,
)

# ----------------------------------------------------------------------
# Литералы домена
# ----------------------------------------------------------------------

# Admin Shop Editor допускает новые типы карточек без новой DB-миграции.
ShopItemType = str

ShopOrderStatus = Literal[
    "PENDING",
    "PAID_AUTO",
    "PAID_PENDING_MANUAL",
    "APPROVED",
    "REJECTED",
    "CANCELLED",
]

PayMethod = Literal["EFHC", "TON", "USDT"]

SKU_MAX_LEN = 64


# ----------------------------------------------------------------------
# Витрина каталога
# ----------------------------------------------------------------------


class ShopCatalogItemOut(EfhcBaseModel):
    """Элемент витрины Shop (карточка товара)."""

    id: ApiLifetimeId = Field(..., description="ID товара.")
    type: ShopItemType = Field(..., description="Тип товара.")
    sku: str = Field(..., description="Уникальный SKU (заказы/мемо).")
    title: str
    description: str | None = None
    active: bool = True

    methods: dict[str, Any] | None = Field(
        None,
        description=(
            "Методы оплаты (канон витрины; UI-дизейблы дополняет роут)"
        ),
    )

    price_efhc: Decimal | None = Field(
        None,
        description=(
            "Цена в EFHC (Decimal/8). None - за EFHC не купить."
        ),
    )

    ton_enabled: bool = Field(
        False,
        description="Можно оплатить через TON (обычно EFHC-пакеты).",
    )
    ton_dest_address: str | None = Field(
        None,
        description="TON-адрес проекта (проверяется watcher).",
    )
    ton_price_hint: Decimal | None = Field(
        None,
        description="Ориентировочная цена в TON (информативно).",
    )
    memo_template: str | None = Field(
        None,
        description=(
            "Шаблон MEMO для TON (например "
            "'SKU:EFHC|Q:{qty}|G:{global_id}')."
        ),
    )

    max_per_user: int | None = Field(
        None,
        description=(
            "Лимит на пользователя (0 запрет, None без лимита)."
        ),
    )
    stock_total: int | None = None
    stock_left: int | None = None

    image_url: str | None = None
    category: str = "other"
    badge: str = ""
    status: str = "live"
    action_mode: str = "checkout"
    external_url: str | None = None
    delivery_mode: str = "manual"
    quantity_efhc: str | None = None
    sort_order: int = 0

    created_at: datetime
    updated_at: datetime

    @field_validator("price_efhc", mode="before")
    def _q8(
        cls,
        v: Decimal | None,
    ) -> Decimal | None:
        """Внутренний EFHC price использует D8."""
        return None if v is None else d8(v)

    model_config = ConfigDict(extra="ignore")


class ShopCatalogOut(EfhcBaseModel):
    items: list[ShopCatalogItemOut]
    user_info: dict[str, Any] | None = None


# ----------------------------------------------------------------------
# Покупка внутри бота за EFHC
# ----------------------------------------------------------------------


class ShopPurchaseByEFHCIn(EfhcBaseModel):
    """Покупка за EFHC внутри бота (денежный POST: Idempotency-Key)."""

    sku: str
    quantity: int = Field(..., description="Штуки > 0.")
    prefer_bonus_first: bool = Field(
        True,
        description="Сначала списать бонусы (канон).",
    )
    client_nonce: str | None = Field(
        None,
        min_length=1,
        max_length=128,
        description="Опциональный client nonce (1..128).",
    )


class ShopPurchaseByEFHCOut(EfhcBaseModel):
    """Результат покупки за EFHC (через банковский сервис)."""

    ok: bool = True
    sku: str
    quantity: int
    debited_bonus_efhc: Decimal = Field(Decimal("0"))
    debited__main__efhc: Decimal = Field(Decimal("0"))
    total_debited_efhc: Decimal = Field(Decimal("0"))
    bank_transfer_log_id: ApiLifetimeId = Field(
        ...,
        description="ID в efhc_transfers_log.",
    )
    idempotency_key: str
    message: str = ""
    processed_at: datetime

    @field_validator(
        "debited_bonus_efhc",
        "debited__main__efhc",
        "total_debited_efhc",
        mode="before",
    )
    def _q8(cls, v: Decimal) -> Decimal:
        return cast(Decimal, d8(v))

    model_config = ConfigDict(extra="ignore")


# ----------------------------------------------------------------------
# TON-интент (EFHC-пакеты за TON)
# ----------------------------------------------------------------------


class TonPaymentIntentIn(EfhcBaseModel):
    """Запрос параметров оплаты EFHC-пакета через TON (без списаний)."""

    sku: str
    quantity: int = Field(
        ...,
        description="Сколько единиц пакета покупаем.",
    )
    client_nonce: str | None = Field(None, min_length=1, max_length=128)


class TonPaymentIntentOut(EfhcBaseModel):
    """Параметры оплаты в TON: адрес, MEMO, подсказка суммы."""

    ok: bool = True
    dest_address: str = Field(
        ...,
        description="TON-адрес проекта (из конфигурации).",
    )
    memo: str = Field(
        ...,
        description=(
            "Строгий MEMO, например "
            "'SKU:EFHC|Q:100|G:0000000123'."
        ),
    )
    ton_amount_due_hint: Decimal | None = Field(
        None,
        description="Подсказка по сумме TON, если есть прайс.",
    )
    expires_at: datetime | None = Field(
        None,
        description="Время жизни интента (информативно).",
    )
    created_order_id: ApiLifetimeId | None = Field(
        None,
        description=(
            "ID предварительного заказа (если создаётся запись)."
        ),
    )

    @field_validator("ton_amount_due_hint", mode="before")
    def _ton_native(
        cls,
        v: Decimal | None,
    ) -> Decimal | None:
        return None if v is None else Decimal(str(v))

    model_config = ConfigDict(extra="ignore")


# ----------------------------------------------------------------------
# Заявка на NFT (ручная обработка)
# ----------------------------------------------------------------------


class NftRequestCreateIn(EfhcBaseModel):
    """Заявка на NFT (VIP). Автовыдачи NFT нет, только ручной аппрув."""

    sku: str = Field("NFT_VIP", description="По канону: 'NFT_VIP'.")
    quantity: int = Field(1, description="Обычно 1.")
    client_nonce: str | None = Field(None, min_length=1, max_length=128)


class NftRequestOut(EfhcBaseModel):
    id: ApiLifetimeId
    sku: str
    quantity: int
    status: ShopOrderStatus
    global_id: str = Field(..., pattern=r"^[0-9]{10}$")
    tx_hash: str | None = None
    created_at: datetime
    updated_at: datetime


# ----------------------------------------------------------------------
# Просмотр/история заказов
# ----------------------------------------------------------------------


class ShopOrderViewOut(EfhcBaseModel):
    id: ApiLifetimeId
    type: ShopItemType
    sku: str
    quantity: int
    status: ShopOrderStatus
    global_id: str = Field(..., pattern=r"^[0-9]{10}$")

    tx_hash: str | None = Field(
        None,
        description="Хэш платежа TON (если применимо).",
    )
    payment_method: str | None = None
    expected_amount: Decimal | None = None
    paid_at: datetime | None = None
    debited_bonus_efhc: Decimal | None = Field(
        None,
        description="Списано бонусов (если применимо).",
    )
    debited__main__efhc: Decimal | None = Field(
        None,
        description="Списано основного баланса (если применимо).",
    )
    idempotency_key: str | None = Field(
        None,
        description="Ключ идемпотентности (если применялся).",
    )

    created_at: datetime
    updated_at: datetime

    @field_validator(
        "debited_bonus_efhc",
        "debited__main__efhc",
        mode="before",
    )
    def _q8(
        cls,
        v: Decimal | None,
    ) -> Decimal | None:
        return None if v is None else d8(v)

    model_config = ConfigDict(extra="ignore")


ShopOrdersPage = CursorPage[ShopOrderViewOut]


# ----------------------------------------------------------------------
# External order DTO (старые схемы для части роутов)
# ----------------------------------------------------------------------


class ShopOrderExternalIn(EfhcBaseModel):
    sku: str
    quantity: int = Field(
        ...,
        ge=1,
        le=1,
        description="Одна catalog position на один внешний order.",
    )
    pay_method: str = Field(
        ...,
        description="TON|USDT|... (в зависимости от реализации).",
    )
    custom_efhc_amount_d8: str | None = Field(
        default=None,
        description=(
            "Whole EFHCm quantity for EFHC_PACKAGE_CUSTOM. "
            "Server recomputes external total from catalog D2 rate."
        ),
    )


class ShopOrderPayloadOut(EfhcBaseModel):
    data: dict[str, Any] = Field(default_factory=dict)
    model_config = ConfigDict(extra="allow")


class ShopPayOut(EfhcBaseModel):
    data: dict[str, Any] = Field(default_factory=dict)
    model_config = ConfigDict(extra="allow")


class ShopOrderExternalOut(EfhcBaseModel):
    order: Any
    pay: Any
    model_config = ConfigDict(extra="allow")


class ShopOrderListOut(EfhcBaseModel):
    items: list[Any]
    next_cursor: str | None = None
    model_config = ConfigDict(extra="allow")
