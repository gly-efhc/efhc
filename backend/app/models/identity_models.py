"""ORM-модель provider-neutral внешних идентичностей EFHC."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.identity.user_identities_storage_contract import (
    USER_IDENTITY_CONSTRAINTS,
    USER_IDENTITY_DEFAULT_TENANT,
    USER_IDENTITY_GLOBAL_ID_MAX,
    USER_IDENTITY_GLOBAL_ID_MIN,
    USER_IDENTITY_PROVIDER_MAX_LENGTH,
    USER_IDENTITY_STATUS_MAX_LENGTH,
    USER_IDENTITY_SUBJECT_MAX_LENGTH,
    USER_IDENTITY_TENANT_MAX_LENGTH,
    UserIdentityStatus,
)
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKeyConstraint,
    Identity,
    Index,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from .base import SCHEMA, Base


class UserIdentity(Base):
    """Проверенная provider identity одного global account.

    Модель не выполняет verification, account creation, session issue,
    merge или runtime resolution. ``global_id`` ссылается на окончательную физическую колонку
    ``users.global_id`` в единой release migration ``0001``.
    """

    __tablename__ = "user_identities"
    __table_args__ = (
        PrimaryKeyConstraint(
            "id",
            name=USER_IDENTITY_CONSTRAINTS["primary_key"],
        ),
        ForeignKeyConstraint(
            ["global_id"],
            [f"{SCHEMA}.users.global_id"],
            name=USER_IDENTITY_CONSTRAINTS["foreign_key"],
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "provider",
            "provider_tenant",
            "provider_subject",
            name=USER_IDENTITY_CONSTRAINTS["unique_subject"],
        ),
        UniqueConstraint(
            "id",
            "global_id",
            name="uq_user_identities_id_global_id",
        ),
        CheckConstraint(
            (
                "global_id BETWEEN "
                f"{USER_IDENTITY_GLOBAL_ID_MIN} AND "
                f"{USER_IDENTITY_GLOBAL_ID_MAX}"
            ),
            name=USER_IDENTITY_CONSTRAINTS["global_id_range"],
        ),
        CheckConstraint(
            "provider ~ '^[a-z][a-z0-9_]{0,31}$'",
            name=USER_IDENTITY_CONSTRAINTS["provider_format"],
        ),
        CheckConstraint(
            "provider <> 'mock'",
            name=USER_IDENTITY_CONSTRAINTS["provider_not_mock"],
        ),
        CheckConstraint(
            (
                "char_length(provider_tenant) BETWEEN 1 AND "
                f"{USER_IDENTITY_TENANT_MAX_LENGTH} AND "
                "provider_tenant = btrim(provider_tenant)"
            ),
            name=USER_IDENTITY_CONSTRAINTS["tenant_length"],
        ),
        CheckConstraint(
            (
                "char_length(provider_subject) BETWEEN 1 AND "
                f"{USER_IDENTITY_SUBJECT_MAX_LENGTH}"
            ),
            name=USER_IDENTITY_CONSTRAINTS["subject_length"],
        ),
        CheckConstraint(
            "status IN ('active', 'disabled', 'revoked')",
            name=USER_IDENTITY_CONSTRAINTS["status"],
        ),
        CheckConstraint(
            (
                "(is_verified AND verified_at IS NOT NULL) OR "
                "(NOT is_verified AND verified_at IS NULL)"
            ),
            name=USER_IDENTITY_CONSTRAINTS["verified_at"],
        ),
        CheckConstraint(
            (
                "NOT is_primary OR "
                "(is_verified AND status = 'active')"
            ),
            name=USER_IDENTITY_CONSTRAINTS["primary_state"],
        ),
        Index(
            "ix_user_identities_global_id",
            "global_id",
        ),
        Index(
            "ix_user_identities_provider_status",
            "provider",
            "status",
        ),
        Index(
            "ix_user_identities_provider_subject",
            "provider_subject",
        ),
        Index(
            USER_IDENTITY_CONSTRAINTS["primary_per_global"],
            "global_id",
            unique=True,
            postgresql_where=text("is_primary"),
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(start=1),
        nullable=False,
    )
    global_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(
        String(USER_IDENTITY_PROVIDER_MAX_LENGTH),
        nullable=False,
    )
    provider_tenant: Mapped[str] = mapped_column(
        String(USER_IDENTITY_TENANT_MAX_LENGTH),
        nullable=False,
        default=USER_IDENTITY_DEFAULT_TENANT,
        server_default=text(f"'{USER_IDENTITY_DEFAULT_TENANT}'"),
    )
    provider_subject: Mapped[str] = mapped_column(
        String(USER_IDENTITY_SUBJECT_MAX_LENGTH),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(USER_IDENTITY_STATUS_MAX_LENGTH),
        nullable=False,
        default=UserIdentityStatus.ACTIVE.value,
        server_default=text("'active'"),
    )
    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    verified_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    provider_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        """Вернуть безопасное представление без subject/global_id."""

        return (
            "<UserIdentity "
            f"id={self.id!r} "
            f"provider={self.provider!r} "
            f"status={self.status!r}>"
        )


__all__ = ["UserIdentity"]
