from __future__ import annotations

from datetime import datetime

from app.core.config_core import get_settings
from app.core.sql_aliases_core import canon_schema
from sqlalchemy import DateTime, text
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    declarative_mixin,
    mapped_column,
)

settings = get_settings()

SCHEMA: str = canon_schema(
    getattr(settings, "DB_SCHEMA_CORE", "efhc_core"),
)


class Base(DeclarativeBase):
    """Единый Declarative Base проекта."""


@declarative_mixin
class TimestampMixin:
    """Примесь created_at / updated_at (UTC, tz-aware)."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("timezone('utc', now())"),
        comment="Когда запись создана (UTC).",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("timezone('utc', now())"),
        onupdate=text("timezone('utc', now())"),
        comment="Когда запись обновлена (UTC).",
    )
