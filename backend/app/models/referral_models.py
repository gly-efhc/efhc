"""ORM-модели provider-neutral реферального домена EFHC."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from ..core.config_core import get_settings
from ..core.sql_aliases_core import canon_schema
from .base import Base

settings = get_settings()
CORE_SCHEMA = canon_schema(settings.DB_SCHEMA_CORE)


class ReferralLink(Base):
    """Связь ``inviter_global_id -> invitee_global_id``.

    Ownership хранится только через canonical global_id.
    """

    __tablename__ = "referral_links"
    __table_args__ = (
        UniqueConstraint(
            "invitee_global_id",
            name="uq_referral_links_invitee_global_id",
        ),
        UniqueConstraint(
            "inviter_global_id",
            "unit_reward_no",
            name="uq_referral_links_inviter_unit_reward_no",
        ),
        ForeignKeyConstraint(
            ["inviter_global_id"],
            [f"{CORE_SCHEMA}.users.global_id"],
            name="fk_ref_links_inviter_global_users_global_id",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["invitee_global_id"],
            [f"{CORE_SCHEMA}.users.global_id"],
            name="fk_ref_links_invitee_global_users_global_id",
            onupdate="RESTRICT",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "inviter_global_id BETWEEN 1 AND 9999999999",
            name="ck_ref_links_inviter_global_range",
        ),
        CheckConstraint(
            "invitee_global_id BETWEEN 1 AND 9999999999",
            name="ck_ref_links_invitee_global_range",
        ),
        CheckConstraint(
            "inviter_global_id <> invitee_global_id",
            name="ck_ref_links_global_not_self",
        ),
        CheckConstraint(
            "unit_reward_no IS NULL OR "
            "unit_reward_no BETWEEN 1 AND 10000",
            name="ck_ref_links_unit_reward_no_range",
        ),
        {"schema": CORE_SCHEMA},
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    inviter_global_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
    )
    invitee_global_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    activated_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
        index=True,
    )
    unit_reward_no: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Номер monetary slot 1..10000 для direct referral reward.",
    )
    campaign: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )
    meta: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    def __repr__(self) -> str:
        active = self.activated_at is not None
        return (
            "<ReferralLink "
            f"id={self.id} "
            f"{self.inviter_global_id}->{self.invitee_global_id} "
            f"active={active}>"
        )


Index(
    "ix_ref_links_created_id",
    ReferralLink.created_at,
    ReferralLink.id,
    postgresql_using="btree",
)
Index(
    "ix_referral_links_inviter_created_invitee_global",
    ReferralLink.inviter_global_id,
    ReferralLink.created_at.desc(),
    ReferralLink.invitee_global_id.desc(),
    postgresql_using="btree",
)
Index(
    "ix_ref_links_activated_at",
    ReferralLink.activated_at,
    postgresql_using="btree",
)


class ReferralBonusLedger(Base):
    """Журнал реферальных начислений по canonical ``global_id``."""

    __tablename__ = "referral_bonus_ledger"
    __table_args__ = (
        ForeignKeyConstraint(
            ["global_id"],
            [f"{CORE_SCHEMA}.users.global_id"],
            name="fk_ref_bonus_global_id_users_global_id",
            onupdate="RESTRICT",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "global_id BETWEEN 1 AND 9999999999",
            name="ck_ref_bonus_global_id_range",
        ),
        {"schema": CORE_SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    global_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
    )
    tg_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    amount_efhc: Mapped[object] = mapped_column(
        Numeric(20, 8),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
    )
    meta: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


__all__ = ["ReferralLink", "ReferralBonusLedger"]
