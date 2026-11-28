# backend/app/models/withdraw_models.py
# =====================================================================
# Назначение кода:
# ORM-модели заявок на вывод EFHC.
# Канон:
# • Выводы — деньги → через transactions_service.py.
# • Уникальность по idempotency_key.
# =====================================================================

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..core.config_core import get_settings
from ..core.sql_aliases_core import canon_schema
from .base import Base

settings = get_settings()
SCHEMA: str = canon_schema(
    getattr(settings, "DB_SCHEMA_CORE", "efhc_core"),
)


class WithdrawRequest(Base):
    """Каноничная заявка на вывод EFHC.

    Источник истины: {SCHEMA}.withdraw_requests.

    Важно:
      • idempotency_key хранит Idempotency-Key заявки.
      • Служебные поля: hold/refund/payout/tx/processed/error.
    """

    __tablename__ = "withdraw_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING','PAID','REJECTED','CANCELED')",
            name="ck_withdraw_requests_status_enum",
        ),
        sa.UniqueConstraint(
            "processing_idempotency_key",
            name="uq_withdraw_processing_idempotency_key",
        ),
        sa.UniqueConstraint(
            "payout_ref",
            name="uq_withdraw_payout_ref",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tg_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment=(
            "Telegram delivery metadata; never a business owner or FK."
        ),
    )
    global_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            f"{SCHEMA}.users.global_id",
            name="fk_withdraw_requests_global_users_global_id",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
        comment="Канонический и единственный владелец заявки.",
    )

    amount: Mapped[object] = mapped_column(
        Numeric(30, 8),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="PENDING",
    )

    idempotency_key: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        unique=True,
    )

    hold_done: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        server_default=sa.text("false"),
    )
    refund_done: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        server_default=sa.text("false"),
    )

    payout_ref: Mapped[object] = mapped_column(
        String(128),
        nullable=True,
    )
    external_address: Mapped[object] = mapped_column(
        String(256),
        nullable=True,
    )
    processing_idempotency_key: Mapped[object] = mapped_column(
        String(128),
        nullable=True,
    )

    tx_hash: Mapped[object] = mapped_column(
        String(128),
        nullable=True,
    )
    processed_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    error_message: Mapped[object] = mapped_column(
        sa.Text,
        nullable=True,
    )

    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Withdrawal(Base):
    """DEPRECATED: для старых окружений.

    Ранее таблица называлась withdrawals.
    Канонично теперь: withdraw_requests.
    Не используйте этот класс в новом коде.

    P3 legacy cosmetic drift: old CHECK constraint name
    ``ck_payment_intents_status_enum`` is intentionally documented and
    not renamed to avoid migration noise for a deprecated table.
    """

    __tablename__ = "withdrawals"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING','PAID','REJECTED','CANCELED')",
            name="ck_payment_intents_status_enum",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tg_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment=(
            "Historical Telegram delivery metadata; not an owner or FK."
        ),
    )
    global_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            f"{SCHEMA}.users.global_id",
            name="fk_withdrawals_global_users_global_id",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
        comment="Канонический owner deprecated-таблицы.",
    )
    amount_efhc: Mapped[object] = mapped_column(
        Numeric(20, 8),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="requested",
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
