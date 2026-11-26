from __future__ import annotations

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..core.config_core import get_settings
from ..core.sql_aliases_core import canon_schema
from .base import Base, TimestampMixin

settings = get_settings()
CORE_SCHEMA = canon_schema(settings.DB_SCHEMA_CORE)


class SystemTemplate(TimestampMixin, Base):
    __tablename__ = "system_templates"
    __table_args__ = ({"schema": CORE_SCHEMA},)

    key: Mapped[str] = mapped_column(
        String(128),
        primary_key=True,
        comment="Уникальный ключ шаблона.",
    )
    content: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Содержимое шаблона.",
    )
    description: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Описание шаблона для администратора.",
    )
