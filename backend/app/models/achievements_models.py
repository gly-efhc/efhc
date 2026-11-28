# backend/app/models/achievements_models.py
# =====================================================================
# Назначение кода:
# ORM-модели достижений пользователя (уровни 1..12).
# Канон:
# • Это только данные. Логика достижений — в services/ranks_service.py.
# =====================================================================

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    UniqueConstraint,
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


class Achievement(Base):
    __tablename__ = "achievements"
    __table_args__ = (
        UniqueConstraint(
            "global_id",
            "level",
            name="uq_achievements_global_level",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    global_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            f"{SCHEMA}.users.global_id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
