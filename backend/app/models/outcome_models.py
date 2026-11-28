from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import BigInteger, Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..core.config_core import get_settings
from ..core.sql_aliases_core import canon_schema
from .base import Base, TimestampMixin

settings = get_settings()
SCHEMA = canon_schema(
    getattr(settings, "DB_SCHEMA_CORE", "efhc_core"),
)


class WithdrawOutcomeEvent(TimestampMixin, Base):
    __tablename__ = "withdraw_outcome_events"
    __table_args__ = (
        sa.UniqueConstraint(
            "withdraw_request_id",
            name="uq_withdraw_outcome_events_request_id",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    withdraw_request_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            f"{SCHEMA}.withdraw_requests.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    tg_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="Telegram recipient; not a business owner.",
    )
    global_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            f"{SCHEMA}.users.global_id",
            name="fk_withdraw_outcome_global_users_global_id",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
        comment="Единственный business owner записи.",
    )
    outcome_kind: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    locale: Mapped[str] = mapped_column(String(16), nullable=False)
    comment_template_key: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )
    comment_text: Mapped[str] = mapped_column(Text, nullable=False)
    comment_source: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    manual_override_used: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=sa.text("false"),
    )
    auto_translated: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=sa.text("false"),
    )
    promo_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=sa.text("false"),
    )
    promo_key: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )
    promo_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    promo_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    promo_cta_label: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    promo_cta_url: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
    )
    promo_source: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )
    source_snapshot: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )


class OutcomeFallbackPromo(TimestampMixin, Base):
    __tablename__ = "outcome_fallback_promos"
    __table_args__ = (
        sa.UniqueConstraint(
            "domain",
            "locale",
            "context",
            name="uq_outcome_fallback_promos_domain_locale_context",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    domain: Mapped[str] = mapped_column(String(64), nullable=False)
    locale: Mapped[str] = mapped_column(String(16), nullable=False)
    context: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    cta_label: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    cta_url: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=sa.text("true"),
    )
