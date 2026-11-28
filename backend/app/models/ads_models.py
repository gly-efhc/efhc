"""ORM-модели рекламной инфраструктуры EFHC.

Контуры намеренно разделены:
- ``ads`` — исторические объявления/ротация; сохраняется без переиспользования;
- ``ad_provider_configs`` — runtime-конфигурация внешних рекламных сетей;
- ``ad_sessions`` — серверная rewarded-сессия;
- ``ad_daily_counters`` — concurrency-safe дневной лимит UTC;
- ``ad_events`` — append-only журнал mediation/reward/revenue событий;
- ``ad_admin_audit_log`` — audit изменений Admin → ADS без секретных значений;
- ``ad_provider_daily_metrics`` — агрегаты/импорт provider statistics.

Business owner рекламного runtime — только canonical ``global_id``. Telegram
``tg_id`` в этих таблицах owner-колонкой не является.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..core.config_core import get_settings
from ..core.sql_aliases_core import canon_schema
from .base import Base

settings = get_settings()
SCHEMA: str = canon_schema(getattr(settings, "DB_SCHEMA_CORE", "efhc_core"))


class Ad(Base):
    """Историческая таблица объявлений/ротации; не provider config."""

    __tablename__ = "ads"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="active"
    )
    weight: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1"
    )
    starts_at: Mapped[object | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ends_at: Mapped[object | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AdProviderConfig(Base):
    """Admin DB override конфигурации рекламного provider."""

    __tablename__ = "ad_provider_configs"
    __table_args__ = (
        UniqueConstraint("code", name="uq_ad_provider_configs_code"),
        CheckConstraint("priority >= 0", name="ck_ad_provider_priority_nonnegative"),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    miniapp_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    bot_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rewarded_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    config_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    public_config_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    secret_config_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    countries_allow: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    countries_block: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    languages_allow: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    languages_block: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    verification_mode: Mapped[str] = mapped_column(
        String(32), nullable=False, default="client_plus_session"
    )
    verification_level: Mapped[str] = mapped_column(
        String(8), nullable=False, default="C"
    )
    moderation_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    health_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unknown"
    )
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("timezone('utc', now())")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=text("timezone('utc', now())"),
        onupdate=text("timezone('utc', now())"),
    )


class AdSession(Base):
    """Одна server-owned попытка rewarded advertising flow."""

    __tablename__ = "ad_sessions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["global_id"], [f"{SCHEMA}.users.global_id"],
            name="fk_ad_sessions_global_users_global_id",
            onupdate="RESTRICT", ondelete="RESTRICT",
        ),
        CheckConstraint(
            "global_id BETWEEN 1 AND 9999999999",
            name="ck_ad_sessions_global_id_range",
        ),
        CheckConstraint("fallback_count >= 0", name="ck_ad_sessions_fallback_nonnegative"),
        UniqueConstraint("actual_provider", "provider_ref", name="uq_ad_sessions_provider_ref"),
        {"schema": SCHEMA},
    )

    session_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    global_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    task_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    primary_provider: Mapped[str | None] = mapped_column(String(48), nullable=True)
    actual_provider: Mapped[str | None] = mapped_column(String(48), nullable=True, index=True)
    provider_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="created", index=True)
    app_language: Mapped[str] = mapped_column(String(16), nullable=False, default="en")
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    platform: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reward_snapshot_efhcb: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), nullable=False, default=Decimal("0.00000000")
    )
    provider_public_config: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    attempted_providers: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    verification_level: Mapped[str | None] = mapped_column(String(8), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("timezone('utc', now())")
    )
    shown_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rewarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reward_slot_reserved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    task_slot_reserved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    estimated_revenue_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    actual_revenue_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fallback_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    test_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=text("timezone('utc', now())"),
        onupdate=text("timezone('utc', now())"),
    )


Index("ix_ad_sessions_global_task_started", AdSession.global_id, AdSession.task_code, AdSession.started_at)


class AdDailyCounter(Base):
    """Серверный дневной лимит rewarded completions, день = UTC."""

    __tablename__ = "ad_daily_counters"
    __table_args__ = (
        UniqueConstraint(
            "global_id", "task_code", "utc_date",
            name="uq_ad_daily_counter_owner_task_day",
        ),
        ForeignKeyConstraint(
            ["global_id"], [f"{SCHEMA}.users.global_id"],
            name="fk_ad_daily_counter_global_users_global_id",
            onupdate="RESTRICT", ondelete="RESTRICT",
        ),
        CheckConstraint("attempts >= 0", name="ck_ad_daily_attempts_nonnegative"),
        CheckConstraint("successful_views >= 0", name="ck_ad_daily_success_nonnegative"),
        CheckConstraint("rewards >= 0", name="ck_ad_daily_rewards_nonnegative"),
        CheckConstraint("reserved_rewards >= 0", name="ck_ad_daily_reserved_nonnegative"),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    global_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    task_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    utc_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    successful_views: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rewards: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reserved_rewards: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_view_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=text("timezone('utc', now())"),
        onupdate=text("timezone('utc', now())"),
    )


class AdEvent(Base):
    """Append-only событие mediation, verification и revenue telemetry."""

    __tablename__ = "ad_events"
    __table_args__ = (
        UniqueConstraint(
            "provider", "provider_event_id", "event_type",
            name="uq_ad_events_provider_event_type",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    provider: Mapped[str | None] = mapped_column(String(48), nullable=True, index=True)
    task_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    provider_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    estimated_revenue_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    actual_revenue_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("timezone('utc', now())"), index=True
    )


class AdProviderClaim(Base):
    """Одноразовый financial claim provider-события rewarded ADS."""

    __tablename__ = "ad_provider_claims"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_event_id",
            name="uq_ad_provider_claims_provider_event",
        ),
        ForeignKeyConstraint(
            ["session_id"],
            [f"{SCHEMA}.ad_sessions.session_id"],
            name="fk_ad_provider_claims_session",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["global_id"],
            [f"{SCHEMA}.users.global_id"],
            name="fk_ad_provider_claims_global_users_global_id",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "global_id BETWEEN 1 AND 9999999999",
            name="ck_ad_provider_claims_global_id_range",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    provider: Mapped[str] = mapped_column(
        String(48), nullable=False, index=True
    )
    provider_event_id: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    session_id: Mapped[str] = mapped_column(
        String(36), nullable=False, index=True
    )
    global_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, index=True
    )
    claimed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("timezone('utc', now())"),
    )


class AdAdminAuditLog(Base):
    """Audit Admin → ADS. Секретные значения сюда никогда не записываются."""

    __tablename__ = "ad_admin_audit_log"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    admin_global_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    field_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("timezone('utc', now())"), index=True
    )


class AdProviderDailyMetric(Base):
    """Нормализованные суточные provider metrics для revenue optimizer."""

    __tablename__ = "ad_provider_daily_metrics"
    __table_args__ = (
        UniqueConstraint(
            "metric_date", "provider", "country_code", "app_language", "task_code",
            name="uq_ad_provider_daily_metric_dimensions",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    metric_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    app_language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    task_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    requests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fills: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    impressions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_views: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    valued_events: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    clicks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fallbacks_in: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fallbacks_out: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    errors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    no_fill: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_revenue_usd: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), nullable=False, default=Decimal("0.00000000")
    )
    confirmed_revenue_usd: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), nullable=False, default=Decimal("0.00000000")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=text("timezone('utc', now())"),
        onupdate=text("timezone('utc', now())"),
    )
