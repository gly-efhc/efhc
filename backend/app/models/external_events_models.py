# backend/app/models/external_events_models.py
# ======================================================================
# EFHC Bot — Processed external events (dedupe for webhooks/callbacks).
# Канон:
# - Схема: efhc_core (CORE_SCHEMA)
# - UNIQUE(provider, event_id)
# - Используется dependency external_event_dedupe_dep() в app.deps
# ======================================================================

from __future__ import annotations

from app.core.config_core import get_settings
from app.core.sql_aliases_core import canon_schema
from sqlalchemy import (
    BigInteger,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin

_settings = get_settings()
CORE_SCHEMA = canon_schema(_settings.DB_SCHEMA_CORE)


class ProcessedExternalEvent(Base, TimestampMixin):
    __tablename__ = "processed_external_events"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "event_id",
            name="uq_processed_external_events_provider_event_id",
        ),
        {"schema": CORE_SCHEMA},
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="Идентификатор записи.",
    )

    provider: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="Имя провайдера (telegram, ads, ...).",
    )

    event_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
        comment="Хеш внешнего идентификатора события.",
    )
    resolved_global_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            f"{CORE_SCHEMA}.users.global_id",
            name="fk_external_event_resolved_global_users_global_id",
            onupdate="RESTRICT",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
        comment="Будущий resolved owner; provider/event_id неизменны.",
    )


Index(
    "ix_processed_external_events_provider_event",
    ProcessedExternalEvent.provider,
    ProcessedExternalEvent.event_id,
)
