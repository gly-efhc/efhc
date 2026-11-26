# backend/app/models/shop_models.py
# ======================================================================
# Назначение кода:
# ORM-модели домена «Магазин» EFHC Bot:
# • каталог товаров (опционально) — ShopItem;
# • заказы пользователя — ShopOrder (EFHC-пакеты и NFT-заявки).
#
# Канон/инварианты:
# • Денежные/энергетические величины — Numeric(30,8)
#   (Decimal с 8 знаками, округление вниз в сервисах).
# • EFHC-пакеты: автодоставка после оплаты (TON → вотчер → банк →
# пользователь).
# • NFT: никаких авто-выдач; только заявка (ручная обработка)
#   и статус PAID_PENDING_MANUAL.
# • Идемпотентность входящих оплат — по tx_hash
#   (UNIQUE в shop_orders и ton_inbox_logs).
# • Никаких P2P: только «банк ↔ пользователь» через сервисы.
#   Модели денег не двигают.
#
# ИИ-защиты:
# • Курсорные индексы (created_at, id) для быстрых витрин/истории.
# • Поля audit/extra для безопасного расширения без миграций (JSONB).
# • global_id обязателен: внешний provider должен быть разрешён до
#   создания заказа.
#
# Запреты:
# • Никаких «суточных» ставок/полей.
# • Никаких скрытых «балансов» в магазине; деньги двигает только
#   банковский сервис.
# ======================================================================

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Numeric

from ..core.config_core import get_settings
from ..core.sql_aliases_core import canon_schema
from .base import Base

settings = get_settings()
CORE_SCHEMA = canon_schema(settings.DB_SCHEMA_CORE)
# например, "efhc_core"


# ----------------------------------------------------------------------
# Типы и статусы заказов
# ----------------------------------------------------------------------


class ShopOrderType(StrEnum):
    """Тип заказа магазина."""

    EFHC = "EFHC"  # пакет EFHC (автодоставка после оплаты)
    NFT = "NFT"  # заявка на NFT (только ручная выдача админом)


class ShopOrderStatus(StrEnum):
    """Статус заказа магазина (унифицирован для EFHC и NFT)."""

    PENDING = "PENDING"  # создан, ожидает оплаты
    PAID_AUTO = "PAID_AUTO"  # оплачен (EFHC): автодоставка выполнена
    PAID_PENDING_MANUAL = "PAID_PENDING_MANUAL"
    # оплачен (NFT): ждёт ручной выдачи админом
    APPROVED = "APPROVED"  # админ подтвердил (обычно для NFT)
    REJECTED = "REJECTED"  # отклонён админом (возврат решается вручную)
    CANCELED = "CANCELED"  # отменён пользователем/системой


# ----------------------------------------------------------------------
# Каталог товаров (опционально)
# ----------------------------------------------------------------------


class ShopItem(Base):
    """
    Каталожная позиция магазина (опционально для витрины).
    В простейшем сценарии EFHC/NFT позиции могут быть зашиты
    конфигом, а эта таблица — для расширения через админку.
    """

    __tablename__ = "shop_items"
    __table_args__ = (
        UniqueConstraint(
            "sku",
            name="uq_shop_items_sku",
        ),
        {"schema": CORE_SCHEMA, "extend_existing": True},
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    # Уникальный артикул (напр., "EFHC_PACK_100", "NFT_VIP")
    sku: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )

    title: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
    )

    # Бизнес-поля (для EFHC-пакетов quantity_efhc > 0).
    quantity_efhc: Mapped[str | None] = mapped_column(
        Numeric(30, 8),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
        server_default="true",
    )

    extra: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        """Диагностическое представление позиции."""
        return (
            f"<ShopItem id={self.id} sku={self.sku} "
            f"active={self.is_active}>"
        )


Index(
    "ix_shop_items_created_id",
    ShopItem.created_at,
    ShopItem.id,
    postgresql_using="btree",
)


# ----------------------------------------------------------------------
# Заказ магазина
# ----------------------------------------------------------------------


class ShopOrder(Base):
    """
    Заказ магазина. Создаётся фронтом/ботом (PENDING), затем
    оплачивается в TON. Вотчер по MEMO/tx_hash сопоставляет
    оплату и меняет статус.

    Семантика ключевых полей:
      • type:
          - EFHC — покупка пакета EFHC (оплата → PAID_AUTO).
          - NFT — заявка на NFT (оплата → PAID_PENDING_MANUAL;
            далее админ APPROVED/REJECTED).
      • status — см. ShopOrderStatus.
      • global_id — обязательный владелец единого аккаунта EFHC.
      • tx_hash — уникальный идентификатор входящего платежа TON.
      • memo — исходный MEMO из TON для аудита.
      • quantity_efhc — количество EFHC в заказе (для NFT обычно NULL).
      • expected_amount — ожидаемая сумма в базовой валюте оплаты.
      • idempotency_key — ключ идемпотентности создания/изменения.
    """

    __tablename__ = "shop_orders"
    __table_args__ = (
        UniqueConstraint(
            "tx_hash",
            name="uq_shop_orders_tx_hash",
        ),
        UniqueConstraint(
            "global_id",
            "idempotency_key",
            name="uq_shop_orders_global_id_idempotency",
        ),
        CheckConstraint(
            "(type = 'EFHC' OR type = 'NFT')",
            name="ck_shop_orders_type_enum",
        ),
        CheckConstraint(
            "quantity_efhc IS NULL OR quantity_efhc >= 0",
            name="ck_shop_orders_qty_nonneg",
        ),
        CheckConstraint(
            "expected_amount IS NULL OR expected_amount >= 0",
            name="ck_shop_orders_expected_nonneg",
        ),
        CheckConstraint(
            "global_id BETWEEN 1 AND 9999999999",
            name="ck_shop_orders_global_id_range",
        ),
        {"schema": CORE_SCHEMA, "extend_existing": True},
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    # Единственный канонический владелец заказа.
    global_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            f"{CORE_SCHEMA}.users.global_id",
            name="fk_shop_orders_global_users_global_id",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        index=True,
        nullable=False,
        comment="Canonical global account owner",
    )

    type: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        index=True,
        default=ShopOrderStatus.PENDING.value,
    )

    # Бизнес-параметры
    quantity_efhc: Mapped[str | None] = mapped_column(
        Numeric(30, 8),
        nullable=True,
    )
    expected_amount: Mapped[str | None] = mapped_column(
        Numeric(30, 8),
        nullable=True,
        comment="Ожидаемая сумма оплаты (TON и т.п.)",
    )

    # TON-сопоставление
    tx_hash: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        index=True,
    )
    memo: Mapped[str | None] = mapped_column(
        String(256),
        nullable=True,
    )
    payment_error_log: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Последняя текстовая ошибка реконсиляции/оплаты",
    )

    # Идемпотентность уровня заказов (не денежная).
    # Полезна для повторных запросов фронта/бота.
    idempotency_key: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        index=True,
    )

    # Произвольные данные: SKU, ценовые параметры,
    # источник рекламной кампании и др.
    extra: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    paid_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    fulfilled_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )

    def __repr__(self) -> str:
        """Диагностическое представление заказа."""
        return (
            f"<ShopOrder id={self.id} type={self.type} "
            f"status={self.status} global_id={self.global_id} "
            f"tx={self.tx_hash}>"
        )


# Индексы под курсор/выборки
Index(
    "ix_shop_orders_created_id",
    ShopOrder.created_at,
    ShopOrder.id,
    postgresql_using="btree",
)
Index(
    "ix_shop_orders_global_created",
    ShopOrder.global_id,
    ShopOrder.created_at,
    postgresql_using="btree",
)
Index(
    "ix_shop_orders_status",
    ShopOrder.status,
    postgresql_using="btree",
)
Index(
    "ix_shop_orders_idem",
    ShopOrder.idempotency_key,
    postgresql_using="btree",
)


# ----------------------------------------------------------------------
# Экспорт
# ----------------------------------------------------------------------
__all__ = [
    "ShopItem",
    "ShopOrder",
    "ShopOrderType",
    "ShopOrderStatus",
]
# ======================================================================
# Пояснения «для чайника»:
# • Почему global_id обязателен?
# Provider identity разрешается до создания заказа. MEMO и watcher
# несут canonical global_id, поэтому доменный объект
# не бывает бесхозным.
#
# • Чем отличается EFHC от NFT в статусах?
# EFHC после оплаты уходит в PAID_AUTO (автодоставка — банк зачисляет
# пользователю EFHC).
# NFT после оплаты становится PAID_PENDING_MANUAL — админ
# вручную подтверждает выдачу NFT (APPROVED/REJECTED).
#
# • Зачем expected_amount и extra?
# expected_amount помогает валидировать сумму платежа TON
# (анти-ошибки/анти-фрод).
# extra — гибкое поле для SKU/курсов/кампаний, чтобы не менять схему при
# расширениях.
# ======================================================================
