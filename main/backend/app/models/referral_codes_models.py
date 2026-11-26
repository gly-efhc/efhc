# backend/app/models/referral_codes_models.py
# =====================================================================
# EFHC Bot — ORM модель для реферальных кодов.
#
# Канон:
# - Истина БД = ORM (Base.metadata).
# - Таблица создаётся через 0001 (ORM-only).
# - Никаких runtime DDL в сервисах.
# =====================================================================

from __future__ import annotations

from app.core.config_core import get_settings
from app.models.base import Base
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from ..core.sql_aliases_core import canon_schema

settings = get_settings()
CORE_SCHEMA = canon_schema(settings.DB_SCHEMA_CORE)


class ReferralCode(Base):
    __tablename__ = "referral_codes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["inviter_global_id"],
            [f"{CORE_SCHEMA}.users.global_id"],
            name="fk_ref_codes_inviter_global_users_global_id",
            onupdate="RESTRICT",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "inviter_global_id",
            name="uq_referral_codes_inviter_global_id",
        ),
        CheckConstraint(
            "inviter_global_id IS NULL OR "
            "inviter_global_id BETWEEN 1 AND 9999999999",
            name="ck_ref_codes_inviter_global_range",
        ),
        Index("ix_referral_codes_created_at", "created_at"),
        {"schema": CORE_SCHEMA},
    )

    code: Mapped[str] = mapped_column(String, primary_key=True)

    inviter_global_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    created_at: Mapped[object] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


__all__ = ["ReferralCode"]
