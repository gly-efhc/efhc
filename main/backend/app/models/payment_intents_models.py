# backend/app/models/payment_intents_models.py
# ======================================================================
# Канон:
# - Схема: efhc_core (settings.DB_SCHEMA_CORE)
# - Денежные значения: Decimal(scale=8) / Numeric(..., 8)
# - Никаких schema=... в Column (schema только на уровне таблицы)
# ======================================================================

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from app.core.config_core import get_settings
from app.core.sql_aliases_core import canon_schema
from app.models.base import Base
from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

_settings = get_settings()
CORE_SCHEMA: str = canon_schema(
    getattr(_settings, "DB_SCHEMA_CORE", "efhc_core")
)


class PaymentIntent(Base):
    """Платёжный интент (TON/USDT и т.п.) для внешней оплаты.

    Важно: это не баланс/банк. Денежно-опасные операции
    (hold/refund/commit) обязаны идти через
    transactions_service, но интенты — это учет
    намерений/статусов.
    """

    __tablename__ = "payment_intents"
    __table_args__ = (
        Index("ix_payment_intents_global_id", "global_id"),
        UniqueConstraint(
            "global_id",
            "purpose",
            "idempotency_key",
            name="uq_payment_intents_global_idempo",
        ),
        Index("ix_payment_intents_status", "status"),
        Index(
            "ux_payment_intents_external_tx_hash_nn",
            "external_tx_hash",
            unique=True,
            postgresql_where=text("external_tx_hash IS NOT NULL"),
        ),
        {"schema": CORE_SCHEMA},
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    tg_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment=(
            "Telegram provider attribute; nullable for "
            "TON-only owner."
        ),
    )
    global_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            f"{CORE_SCHEMA}.users.global_id",
            name="fk_payment_intents_global_users_global_id",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        nullable=False,
        comment="Канонический владелец payment intent.",
    )

    purpose: Mapped[str] = mapped_column(String(64), nullable=False)
    # HEAL-0040: package_id is required for package-based intents, but
    # custom/package-less flows store NULL by contract. Do not use 0 as
    # a fake package sentinel.
    package_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    asset: Mapped[str] = mapped_column(String(16), nullable=False)

    amount_asset_d8: Mapped[Decimal] = mapped_column(
        Numeric(38, 8),
        nullable=False,
    )
    efhc_amount_d8: Mapped[Decimal] = mapped_column(
        Numeric(38, 8),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(String(32), nullable=False)

    idempotency_key: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )

    payload: Mapped[str] = mapped_column(Text, nullable=False)
    to_address: Mapped[str] = mapped_column(String(128), nullable=False)

    external_tx_hash: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
