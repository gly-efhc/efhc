from __future__ import annotations

from datetime import datetime

from app.core.config_core import get_settings
from app.core.sql_aliases_core import canon_schema
from app.models.base import Base
from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

_settings = get_settings()
CORE_SCHEMA: str = canon_schema(
    getattr(_settings, "DB_SCHEMA_CORE", "efhc_core")
)


class TxHashLock(Base):
    """Core-side lock table for blockchain tx_hash reconciliation."""

    __tablename__ = "tx_hash_locks"
    __table_args__ = (
        UniqueConstraint("tx_hash", name="uq_tx_hash_locks_tx_hash"),
        Index("ix_tx_hash_locks_intent_id", "intent_id"),
        Index("ix_tx_hash_locks_global_id", "global_id"),
        Index(
            "ix_tx_hash_locks_trusted_operation_at",
            "trusted_operation_at",
        ),
        {"schema": CORE_SCHEMA},
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    tx_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    purpose: Mapped[str] = mapped_column(String(64), nullable=False)
    intent_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    order_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    global_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            f"{CORE_SCHEMA}.users.global_id",
            name="fk_tx_hash_locks_global_users_global_id",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        nullable=False,
        comment="Канонический владелец tx hash lock.",
    )
    trusted_operation_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment=(
            "Доверенное время on-chain операции; после 180 суток "
            "первичный settlement запрещён."
        ),
    )
    server_first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment=(
            "Первое server-side наблюдение операции; вторая временная "
            "граница settlement."
        ),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
