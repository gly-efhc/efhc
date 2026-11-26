# backend/app/models/settings_models.py
# ======================================================================
# Назначение кода:
# ORM-модель «настройки проекта» (key-value) для админки.
# Используется только для конфигов, которые допустимо хранить в БД
# (НЕ секреты).
# ======================================================================

from __future__ import annotations

from sqlalchemy import BigInteger, Index, String, func
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from ..core.config_core import get_settings
from ..core.sql_aliases_core import canon_schema
from .base import Base

settings = get_settings()
CORE_SCHEMA = canon_schema(settings.DB_SCHEMA_CORE)


class AppSetting(Base):
    __tablename__ = "app_settings"
    __table_args__ = (
        Index(
            "ix_app_settings_key",
            "key",
            unique=True,
        ),
        {"schema": CORE_SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[str] = mapped_column(String(2048), nullable=False)
    updated_at: Mapped[object] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
