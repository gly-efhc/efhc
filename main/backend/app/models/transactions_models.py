"""backend/app/models/transactions_models.py

ORM-модель единого банковского журнала EFHC.

Канон:
- Идемпотентность: idempotency_key UNIQUE.
- Запрещены P2P-переводы: журнал хранит операции «банк ↔ пользователь».
- Денежная точность: Numeric(30, 8). Округление вниз делают сервисы.
"""

from __future__ import annotations

from datetime import datetime

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
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Numeric

from ..core.config_core import get_settings
from ..core.sql_aliases_core import canon_schema
from .base import Base

settings = get_settings()
CORE_SCHEMA = canon_schema(settings.DB_SCHEMA_CORE)
# например, "efhc_core"


class EfhcTransferLog(Base):
    """Запись журнала движения EFHC (пользователь ↔ банк)."""

    __tablename__ = "efhc_transfers_log"
    __table_args__ = (
        UniqueConstraint(
            "idempotency_key",
            name="uq_efhc_transfers_idem_key",
        ),
        CheckConstraint(
            "amount >= 0",
            name="ck_efhc_transfers_amount_nonneg",
        ),
        CheckConstraint(
            "direction IN ('credit','debit')",
            name="ck_efhc_transfers_direction_enum",
        ),
        CheckConstraint(
            "balance_type IN ('main','bonus')",
            name="ck_efhc_transfers_baltype_enum",
        ),
        CheckConstraint(
            "system_entity IS NULL OR system_entity = 'BANK_EFHC'",
            name="ck_efhc_transfers_system_entity_enum",
        ),
        CheckConstraint(
            "(system_entity = 'BANK_EFHC' AND global_id IS NULL AND tg_id IS NULL) "
            "OR (system_entity IS NULL AND global_id IS NOT NULL)",
            name="ck_efhc_transfers_owner_shape",
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
        index=True,
        comment=(
            "Telegram provider attribute; nullable for "
            "TON-only owner."
        ),
    )
    system_entity: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
        comment=(
            "Системная сторона проводки; для центрального банка "
            "используется BANK_EFHC. У банковской строки global_id/tg_id NULL."
        ),
    )
    global_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            f"{CORE_SCHEMA}.users.global_id",
            name="fk_efhc_transfers_global_users_global_id",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        nullable=True,
        index=True,
        comment=(
            "Канонический владелец аккаунта; NULL допустим "
            "только для системной зеркальной строки банка."
        ),
    )
    amount: Mapped[str] = mapped_column(
        Numeric(30, 8),
        nullable=False,
    )
    direction: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        index=True,
    )
    balance_type: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        index=True,
    )
    reason: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
    )
    # meta хранится как JSON-строка.
    # Причина: часть тестов читает meta сырым SQL и делает json.loads
    # от str(raw). Для JSONB драйвер asyncpg возвращает dict, а
    # str(dict) не является валидным JSON.
    meta: Mapped[str | None] = mapped_column(
        Text,
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
            f"<EfhcTransferLog id={self.id} "
            f"global_id={self.global_id} system_entity={self.system_entity} "
            f"{self.direction} "
            f"{self.amount} {self.balance_type}>"
        )


Index(
    "ix_eftl_created_id",
    EfhcTransferLog.created_at,
    EfhcTransferLog.id,
    postgresql_using="btree",
)
Index(
    "ix_eftl_owner_created",
    EfhcTransferLog.global_id,
    EfhcTransferLog.created_at,
    postgresql_using="btree",
)
Index(
    "ix_eftl_reason_created",
    EfhcTransferLog.reason,
    EfhcTransferLog.created_at,
    postgresql_using="btree",
)


TonInboxLog = __import__(
    "app.models.ton_logs_models",
    fromlist=["TonInboxLog"],
).TonInboxLog
WithdrawalRequest = __import__(
    "app.models.withdraw_models",
    fromlist=["WithdrawRequest"],
).WithdrawRequest

__all__ = [
    "EfhcTransferLog",
    "TonInboxLog",
    "WithdrawalRequest",
]

Index(
    "ix_eftl_system_entity_created",
    EfhcTransferLog.system_entity,
    EfhcTransferLog.created_at,
    postgresql_using="btree",
)
