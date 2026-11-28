"""ORM-модели auth challenges, sessions и roles цикла 1613."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from app.identity.auth_runtime_storage_contract import (
    AUTH_DEFAULT_TENANT,
    AUTH_DOMAIN_MAX_LENGTH,
    AUTH_HASH_HEX_LENGTH,
    AUTH_PROVIDER_MAX_LENGTH,
    AUTH_PURPOSE_MAX_LENGTH,
    AUTH_ROLE_MAX_LENGTH,
    AUTH_ROLE_SOURCE_MAX_LENGTH,
    AUTH_RUNTIME_CONSTRAINTS,
    AUTH_TENANT_MAX_LENGTH,
    AuthSessionStatus,
    UserRoleStatus,
)
from sqlalchemy import (
    BigInteger,
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
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import SCHEMA, Base


class AuthChallenge(Base):
    """Одноразовый challenge: в storage хранится только hash."""

    __tablename__ = "auth_challenges"
    __table_args__ = (
        PrimaryKeyConstraint(
            "id",
            name=AUTH_RUNTIME_CONSTRAINTS["challenge_pk"],
        ),
        UniqueConstraint(
            "challenge_hash",
            name=AUTH_RUNTIME_CONSTRAINTS["challenge_hash_unique"],
        ),
        CheckConstraint(
            "provider ~ '^[a-z][a-z0-9_]{0,31}$'",
            name=AUTH_RUNTIME_CONSTRAINTS["challenge_provider_format"],
        ),
        CheckConstraint(
            "provider <> 'mock'",
            name=AUTH_RUNTIME_CONSTRAINTS[
                "challenge_provider_not_mock"
            ],
        ),
        CheckConstraint(
            "char_length(provider_tenant) BETWEEN 1 AND 128 "
            "AND provider_tenant = btrim(provider_tenant)",
            name=AUTH_RUNTIME_CONSTRAINTS["challenge_tenant"],
        ),
        CheckConstraint(
            "purpose ~ '^[a-z][a-z0-9_.:-]{0,63}$'",
            name=AUTH_RUNTIME_CONSTRAINTS["challenge_purpose"],
        ),
        CheckConstraint(
            "char_length(domain) BETWEEN 1 AND 255 "
            "AND domain = btrim(domain)",
            name=AUTH_RUNTIME_CONSTRAINTS["challenge_domain"],
        ),
        CheckConstraint(
            "challenge_hash ~ '^[0-9a-f]{64}$'",
            name=AUTH_RUNTIME_CONSTRAINTS["challenge_hash"],
        ),
        CheckConstraint(
            "expires_at > created_at",
            name=AUTH_RUNTIME_CONSTRAINTS["challenge_expiry"],
        ),
        CheckConstraint(
            "NOT (consumed_at IS NOT NULL "
            "AND invalidated_at IS NOT NULL) "
            "AND (consumed_at IS NULL "
            "OR consumed_at >= created_at) "
            "AND (invalidated_at IS NULL "
            "OR invalidated_at >= created_at)",
            name=AUTH_RUNTIME_CONSTRAINTS["challenge_terminal_state"],
        ),
        Index("ix_auth_challenges_expires_at", "expires_at"),
        Index(
            "ix_auth_challenges_provider_purpose",
            "provider",
            "purpose",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=False,
        default=uuid.uuid4,
    )
    provider: Mapped[str] = mapped_column(
        String(AUTH_PROVIDER_MAX_LENGTH),
        nullable=False,
    )
    provider_tenant: Mapped[str] = mapped_column(
        String(AUTH_TENANT_MAX_LENGTH),
        nullable=False,
        default=AUTH_DEFAULT_TENANT,
        server_default=text(f"'{AUTH_DEFAULT_TENANT}'"),
    )
    purpose: Mapped[str] = mapped_column(
        String(AUTH_PURPOSE_MAX_LENGTH),
        nullable=False,
    )
    domain: Mapped[str] = mapped_column(
        String(AUTH_DOMAIN_MAX_LENGTH),
        nullable=False,
    )
    challenge_hash: Mapped[str] = mapped_column(
        String(AUTH_HASH_HEX_LENGTH),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    invalidated_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    challenge_metadata: Mapped[dict[str, Any]] = mapped_column(
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

    def __repr__(self) -> str:
        return (
            "<AuthChallenge "
            f"id={self.id!r} provider={self.provider!r} "
            f"purpose={self.purpose!r}>"
        )


class AuthSession(Base):
    """Server-side session без хранения raw bearer token."""

    __tablename__ = "auth_sessions"
    __table_args__ = (
        PrimaryKeyConstraint(
            "id",
            name=AUTH_RUNTIME_CONSTRAINTS["session_pk"],
        ),
        ForeignKeyConstraint(
            ["global_id"],
            [f"{SCHEMA}.users.global_id"],
            name=AUTH_RUNTIME_CONSTRAINTS["session_global_fk"],
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["identity_id", "global_id"],
            [
                f"{SCHEMA}.user_identities.id",
                f"{SCHEMA}.user_identities.global_id",
            ],
            name=AUTH_RUNTIME_CONSTRAINTS["session_identity_fk"],
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "token_hash",
            name=AUTH_RUNTIME_CONSTRAINTS["session_hash_unique"],
        ),
        CheckConstraint(
            "token_hash ~ '^[0-9a-f]{64}$'",
            name=AUTH_RUNTIME_CONSTRAINTS["session_hash"],
        ),
        CheckConstraint(
            "status IN ('active', 'revoked')",
            name=AUTH_RUNTIME_CONSTRAINTS["session_status"],
        ),
        CheckConstraint(
            "expires_at > created_at",
            name=AUTH_RUNTIME_CONSTRAINTS["session_expiry"],
        ),
        CheckConstraint(
            "(status = 'active' AND revoked_at IS NULL) OR "
            "(status = 'revoked' AND revoked_at IS NOT NULL)",
            name=AUTH_RUNTIME_CONSTRAINTS["session_revocation"],
        ),
        Index(
            "ix_auth_sessions_global_status",
            "global_id",
            "status",
        ),
        Index("ix_auth_sessions_identity_id", "identity_id"),
        Index("ix_auth_sessions_expires_at", "expires_at"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        default=uuid.uuid4,
    )
    global_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    identity_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    token_hash: Mapped[str] = mapped_column(
        String(AUTH_HASH_HEX_LENGTH),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=AuthSessionStatus.ACTIVE.value,
        server_default=text("'active'"),
    )
    expires_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
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
        return (
            "<AuthSession "
            f"id={self.id!r} status={self.status!r}>"
        )


class UserRole(Base):
    """Provider-neutral роль, принадлежащая global account."""

    __tablename__ = "user_roles"
    __table_args__ = (
        PrimaryKeyConstraint(
            "id",
            name=AUTH_RUNTIME_CONSTRAINTS["role_pk"],
        ),
        ForeignKeyConstraint(
            ["global_id"],
            [f"{SCHEMA}.users.global_id"],
            name=AUTH_RUNTIME_CONSTRAINTS["role_global_fk"],
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "global_id",
            "role",
            name=AUTH_RUNTIME_CONSTRAINTS["role_unique"],
        ),
        CheckConstraint(
            "role ~ '^[a-z][a-z0-9_.:-]{0,63}$'",
            name=AUTH_RUNTIME_CONSTRAINTS["role_format"],
        ),
        CheckConstraint(
            "source ~ '^[a-z][a-z0-9_.:-]{0,31}$'",
            name=AUTH_RUNTIME_CONSTRAINTS["role_source"],
        ),
        CheckConstraint(
            "status IN ('active', 'revoked')",
            name=AUTH_RUNTIME_CONSTRAINTS["role_status"],
        ),
        CheckConstraint(
            "(status = 'active' AND revoked_at IS NULL) OR "
            "(status = 'revoked' AND revoked_at IS NOT NULL)",
            name=AUTH_RUNTIME_CONSTRAINTS["role_revocation"],
        ),
        Index("ix_user_roles_global_status", "global_id", "status"),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(start=1),
        nullable=False,
    )
    global_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    role: Mapped[str] = mapped_column(
        String(AUTH_ROLE_MAX_LENGTH),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(
        String(AUTH_ROLE_SOURCE_MAX_LENGTH),
        nullable=False,
        default="system",
        server_default=text("'system'"),
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=UserRoleStatus.ACTIVE.value,
        server_default=text("'active'"),
    )
    granted_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
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
        return (
            "<UserRole "
            f"id={self.id!r} role={self.role!r} "
            f"status={self.status!r}>"
        )


__all__ = ["AuthChallenge", "AuthSession", "UserRole"]
