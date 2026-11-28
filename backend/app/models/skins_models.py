"""backend/app/models/skins_models.py

ORM модели домена «Skins» (картинки/скины) EFHC Bot.

Таблицы создаются единой release migration 0001:
- user_skins
- user_cosmetics
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from ..core.config_core import get_settings
from ..core.sql_aliases_core import canon_schema
from .base import Base

settings = get_settings()
CORE_SCHEMA = canon_schema(settings.DB_SCHEMA_CORE)


class UserSkin(Base):
    __tablename__ = "user_skins"
    __table_args__ = (
        UniqueConstraint(
            "global_id",
            "skin_id",
            name="uq_user_skins_global_skin",
        ),
        Index("ix_user_skins_global_id", "global_id"),
        CheckConstraint(
            "global_id BETWEEN 1 AND 9999999999",
            name="ck_user_skins_global_id_range",
        ),
        {"schema": CORE_SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    global_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            f"{CORE_SCHEMA}.users.global_id",
            name="fk_user_skins_global_users_global_id",
            onupdate="RESTRICT",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    skin_id: Mapped[int] = mapped_column(Integer, nullable=False)
    purchased_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class UserCosmetics(Base):
    __tablename__ = "user_cosmetics"
    __table_args__ = (
        UniqueConstraint(
            "global_id",
            name="uq_user_cosmetics_global_id",
        ),
        Index("ix_user_cosmetics_global_id", "global_id"),
        CheckConstraint(
            "global_id BETWEEN 1 AND 9999999999",
            name="ck_user_cosmetics_global_id_range",
        ),
        {"schema": CORE_SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    global_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            f"{CORE_SCHEMA}.users.global_id",
            name="fk_user_cosmetics_global_users_global_id",
            onupdate="RESTRICT",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    active_skin_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
