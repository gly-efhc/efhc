from __future__ import annotations

from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..core.config_core import get_settings
from ..core.sql_aliases_core import canon_schema
from .base import Base, TimestampMixin

settings = get_settings()
CORE_SCHEMA = canon_schema(settings.DB_SCHEMA_CORE)


class HubTargetKind(StrEnum):
    EXTERNAL_URL = "external_url"
    INTERNAL_ROUTE = "internal_route"
    BACKEND_HANDOFF = "backend_handoff"


class HubOpenMode(StrEnum):
    SAME_APP = "same_app"
    NEW_TAB = "new_tab"
    EXTERNAL_BROWSER = "external_browser"
    TELEGRAM_WEBAPP_ROUTE = "telegram_webapp_route"


class HubLink(Base, TimestampMixin):
    """Hub link entity for admin-managed navigation cards."""

    __tablename__ = "hub_links"
    __table_args__ = (
        UniqueConstraint("code", name="uq_hub_links_code"),
        CheckConstraint(
            "target_kind IN ("
            "'external_url',"
            "'internal_route',"
            "'backend_handoff'"
            ")",
            name="ck_hub_links_target_kind",
        ),
        CheckConstraint(
            "open_mode IN ("
            "'same_app',"
            "'new_tab',"
            "'external_browser',"
            "'telegram_webapp_route'"
            ")",
            name="ck_hub_links_open_mode",
        ),
        Index(
            "ix_hub_links_sort_order_id",
            "sort_order",
            "id",
        ),
        {"schema": CORE_SCHEMA},
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    subtitle: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    url: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
    )
    target_kind: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    open_mode: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    sort_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("100"),
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )
    icon_key: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
