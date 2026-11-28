"""backend/app/models/user_models.py

ORM-модель домена «Пользователи» EFHC Bot.

Канон/инварианты:
- системный владелец — только global_id; Telegram provider subject хранится
  в user_identities и не владеет domain records.
- Физическая и ORM owner-колонка называется global_id.
- Legacy ORM aliases удалены: внутренний runtime использует только
  global_id.
- Денежные/энергетические поля: Numeric(30, 8), округление вниз делают
  сервисы.
- Запрет «минуса»: main_balance, bonus_balance, available_kwh,
  total_generated_kwh всегда >= 0; exchanged_kwh_total всегда >= 0;
  exchanged_kwh_total <= total_generated_kwh;
  available_kwh — зеркальная ветка:
  available_kwh = total_generated_kwh - exchanged_kwh_total.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Computed,
    Index,
    Sequence,
    String,
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

GLOBAL_ID_SEQUENCE = Sequence(
    "users_global_id_seq",
    schema=CORE_SCHEMA,
    start=1,
    increment=1,
    minvalue=1,
    maxvalue=9_999_999_999,
    cycle=False,
)


class User(Base):
    """Единый аккаунт EFHC с каноническим владельцем ``global_id``.

    ``global_id`` является одновременно business identity и физическим PK.
    Provider subjects хранятся только в ``user_identities``; TON wallets —
    только в ``wallet_bindings``.
    """

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "global_id BETWEEN 1 AND 9999999999",
            name="ck_users_global_id_range",
        ),
        CheckConstraint(
            "global_id <> 1313131313 OR "
            "COALESCE(meta ->> 'reserved_identity', '') = 'superadmin'",
            name="ck_users_superadmin_global_id_reserved",
        ),
        CheckConstraint(
            "main_balance >= 0",
            name="ck_users__main__balance_nonneg",
        ),
        CheckConstraint(
            "bonus_balance >= 0",
            name="ck_users_bonus_balance_nonneg",
        ),
        CheckConstraint(
            "available_kwh >= 0",
            name="ck_users_available_kwh_nonneg",
        ),
        CheckConstraint(
            "total_generated_kwh >= 0",
            name="ck_users_total_generated_kwh_nonneg",
        ),
        CheckConstraint(
            "exchanged_kwh_total >= 0",
            name="ck_users_exchanged_kwh_total_nonneg",
        ),
        CheckConstraint(
            "exchanged_kwh_total <= total_generated_kwh",
            name="ck_users_exchanged_le_total",
        ),
        CheckConstraint(
            (
                "available_kwh = "
                "(total_generated_kwh - exchanged_kwh_total)"
            ),
            name="ck_users_available_eq_mirror",
        ),
        {"schema": CORE_SCHEMA},
    )

    global_id: Mapped[int] = mapped_column(
        BigInteger,
        GLOBAL_ID_SEQUENCE,
        server_default=GLOBAL_ID_SEQUENCE.next_value(),
        primary_key=True,
        nullable=False,
    )

    username: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )

    is_active: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
        server_default="true",
        index=True,
    )
    is_vip: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        server_default="false",
        index=True,
    )
    vip_since: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    vip_checked_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
        index=True,
    )

    main_balance: Mapped[str] = mapped_column(
        Numeric(30, 8),
        nullable=False,
        default="0",
        server_default="0",
    )
    bonus_balance: Mapped[str] = mapped_column(
        Numeric(30, 8),
        nullable=False,
        default="0",
        server_default="0",
    )
    # NOTE:
    # str(Decimal("0.00000000")) в Python даёт "0E-8".
    # Некоторые тесты сравнивают str(value) со строкой "0".
    # Поэтому зеркальное поле хранится как numeric без typmod:
    # Postgres отдаёт "0" → Decimal("0") → str == "0".
    available_kwh: Mapped[str] = mapped_column(
        Numeric,
        Computed(
            "CAST(GREATEST("
            "CAST(total_generated_kwh AS numeric) - "
            "CAST(exchanged_kwh_total AS numeric), 0) AS numeric)",
            persisted=True,
        ),
        nullable=False,
    )
    total_generated_kwh: Mapped[str] = mapped_column(
        Numeric(30, 8),
        nullable=False,
        default="0",
        server_default="0",
    )
    exchanged_kwh_total: Mapped[str] = mapped_column(
        Numeric(30, 8),
        nullable=False,
        default="0",
        server_default="0",
    )

    rank_position: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        index=True,
    )
    rank_score_kwh: Mapped[str | None] = mapped_column(
        Numeric(30, 8),
        nullable=True,
    )
    rank_calculated_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
        index=True,
    )

    last_seen_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
        index=True,
    )
    last_sync_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
        index=True,
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
            f"<User global_id={self.global_id} vip={self.is_vip} "
            f"main={self.main_balance} bonus={self.bonus_balance}>"
        )


Index(
    "ix_users_created_global_id",
    User.created_at,
    User.global_id,
    postgresql_using="btree",
)
Index(
    "ix_users_total_kwh_global_id",
    User.total_generated_kwh,
    User.global_id,
    postgresql_using="btree",
)
Index(
    "ix_users_available_kwh_global_id",
    User.available_kwh,
    User.global_id,
    postgresql_using="btree",
)
Index(
    "ix_users_rank_position_global_id",
    User.rank_position,
    User.global_id,
    postgresql_using="btree",
)


__all__ = [
    "GLOBAL_ID_SEQUENCE",
    "User",
]
