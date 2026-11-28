"""backend/app/models/ton_logs_models.py

ORM-модель журнала входящих транзакций TON, которые отслеживает вотчер.

Канон:
- Уникальность tx_hash обеспечивает идемпотентность обработки.
- Денежная точность: Numeric(30, 8). Округление вниз делают сервисы.
- Денежные движения выполняются банковскими сервисами, не моделью.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
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


class TonInboxLog(Base):
    """Запись входящей транзакции TON, обработанной вотчером."""

    __tablename__ = "ton_inbox_logs"
    __table_args__ = (
        UniqueConstraint(
            "tx_hash",
            name="uq_ton_inbox_tx",
        ),
        CheckConstraint(
            "amount >= 0",
            name="ck_ton_inbox_amount_nonneg",
        ),
        {"schema": CORE_SCHEMA},
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    tx_hash: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
    )
    from_address: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        index=True,
    )
    to_address: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        index=True,
    )

    amount: Mapped[str] = mapped_column(
        Numeric(30, 8),
        nullable=False,
        default="0",
        server_default="0",
    )

    memo: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
    )
    parsed_kind: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        index=True,
    )
    parsed_tg_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        index=True,
    )
    resolved_global_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            f"{CORE_SCHEMA}.users.global_id",
            name="fk_ton_inbox_resolved_global_users_global_id",
            onupdate="RESTRICT",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
        comment="Будущий resolved owner; parsed_tg_id сохраняется.",
    )
    parsed_sku: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
        default="received",
        server_default="received",
    )
    retries_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    next_retry_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    trusted_operation_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
        comment=(
            "Доверенное время внешней финансовой операции; "
            "NULL означает fail-closed для первичного зачисления."
        ),
    )

    last_error: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
    )
    meta: Mapped[dict[str, Any] | None] = mapped_column(
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
        return (
            f"<TonInboxLog tx_hash={self.tx_hash} "
            f"status={self.status} kind={self.parsed_kind} "
            f"tg_id={self.parsed_tg_id}>"
        )


Index(
    "ix_ton_inbox_created_id",
    TonInboxLog.created_at,
    TonInboxLog.id,
    postgresql_using="btree",
)
Index(
    "ix_ton_inbox_status_nextretry",
    TonInboxLog.status,
    TonInboxLog.next_retry_at,
    postgresql_using="btree",
)
Index(
    "ix_ton_inbox_parsed_kind",
    TonInboxLog.parsed_kind,
    postgresql_using="btree",
)


class UnmatchedIncoming(Base):
    """Не сопоставленные входящие транзакции (аудит).

    Канон:
    - Пишем сюда входящие EFHC jetton события, когда payload/memo
      отсутствует или не каноничен.
    - Также можно писать TON/другие активы для ручного разбора,
      но автоначисление разрешено только для EFHC jetton.
    """

    __tablename__ = "unmatched_incoming"
    __table_args__ = (
        UniqueConstraint(
            "tx_hash",
            name="uq_unmatched_incoming_tx",
        ),
        {"schema": CORE_SCHEMA},
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    tx_hash: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
    )

    asset: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default="TON",
    )

    amount_asset_d8: Mapped[Decimal] = mapped_column(
        Numeric(30, 8),
        nullable=False,
        server_default="0",
    )

    from_address: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    to_address: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    memo: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
    )

    utime: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    reason: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )
    resolved_global_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            f"{CORE_SCHEMA}.users.global_id",
            name="fk_unmatched_resolved_global_users_global_id",
            onupdate="RESTRICT",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
        comment="Будущий resolved owner; raw source сохраняется.",
    )

    meta: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


__all__ = [
    "TonInboxLog",
    "UnmatchedIncoming",
]
