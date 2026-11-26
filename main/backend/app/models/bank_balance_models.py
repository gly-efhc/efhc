# backend/app/models/bank_balance_models.py
# =====================================================================
# Назначение:
# Единый системный объект баланса банка EFHC (вариант A):
#   efhc_core.bank_balance
#
# Канон:
# - Банк хранится как системный объект BANK_EFHC.
# - Истина баланса банка хранится в efhc_core.bank_balance.
# - В банке есть ТОЛЬКО EFHC main.
# - Баланс банка МОЖЕТ уходить в минус (внешнее обеспечение).
# - Все изменения выполняются только через transactions_service.
#
# Идентичность банковской ledger-строки:
# - Новая банковская строка: system_entity="BANK_EFHC",
#   поля global_id=NULL и tg_id=NULL не идентифицируют банк.
# - Хранение истинного баланса — только тут.
# =====================================================================

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Index, String, func
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Numeric

from ..core.config_core import get_settings
from .base import Base

S = get_settings()
CORE_SCHEMA = S.DB_SCHEMA_CORE

KEY_MAIN = "EFHC_MAIN"


class BankBalance(Base):
    """Системный баланс банка EFHC по ключу."""

    __tablename__ = "bank_balance"
    __table_args__ = ({"schema": CORE_SCHEMA},)

    key: Mapped[str] = mapped_column(
        String(32),
        primary_key=True,
    )

    balance: Mapped[Decimal] = mapped_column(
        Numeric(30, 8),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
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


Index(
    "ix_bank_balance_updated",
    BankBalance.updated_at,
    postgresql_using="btree",
)
