"""Wallet models (TonConnect bindings).

SSOT:
- ``global_id`` is the only wallet-binding business owner.
- ``tg_id`` is nullable Telegram proof metadata.
- Wallet connected := at least one active wallet binding.
- wallet_address stores EFHC canonical TON address.

Notes:
- ``users.ton_wallet`` удалён из Greenfield schema; ownership хранится здесь.
- UI may display friendly/masked address outside ownership logic.
"""

from __future__ import annotations

from datetime import datetime

from app.core.config_core import get_settings
from app.core.sql_aliases_core import canon_schema
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin

settings = get_settings()
SCHEMA = canon_schema(
    getattr(settings, "DB_SCHEMA_CORE", "efhc_core"),
)


class WalletBinding(Base, TimestampMixin):
    """TON wallet binding owned by canonical ``global_id``."""

    __tablename__ = "wallet_bindings"

    __table_args__ = (
        ForeignKeyConstraint(
            ["global_id"],
            [f"{SCHEMA}.users.global_id"],
            name=(
                "fk_wallet_bindings_global_id_users_global_id"
            ),
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "global_id IS NOT NULL",
            name="ck_wallet_bindings_owner_reference",
        ),
        CheckConstraint(
            (
                "global_id IS NULL OR "
                "global_id BETWEEN 1 AND 9999999999"
            ),
            name="ck_wallet_bindings_global_id_range",
        ),
        Index("ix_wallet_bindings_global_id", "global_id"),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    global_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    tg_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        index=True,
    )
    # EFHC canonical TON address: ``workchain:account_hex``.
    # This field is the ownership/conflict/lookup unique key.
    wallet_address: Mapped[str] = mapped_column(Text, unique=True)
    wallet_app: Mapped[str | None] = mapped_column(String(32))

    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    proof_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    proof_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    proof_payload_hash: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    proof_source: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # created_at/updated_at — из TimestampMixin


class WalletConnectIdempotency(Base):
    """Идемпотентность привязки кошелька (TonConnect).

    Требуется кодом wallets_service.connect_wallet().
    Канон: таблица должна быть ORM и создаваться через 0001.
    """

    __tablename__ = "wallet_connect_idempotency"
    __table_args__ = (
        UniqueConstraint(
            "global_id",
            "idempotency_key",
            name="uq_wallet_connect_global_idk",
        ),
        {"schema": SCHEMA},
    )

    global_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            f"{SCHEMA}.users.global_id",
            name="fk_wallet_connect_global_users_global_id",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        nullable=False,
        primary_key=True,
        index=True,
        comment="Канонический account owner.",
    )
    tg_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True
    )
    idempotency_key: Mapped[str] = mapped_column(Text, primary_key=True)
    wallet_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    wallet_address: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("timezone('utc', now())"),
    )


class WalletProofTokenUse(Base):
    """Single-use TonConnect proof-token marker.

    Prevents replay of a verified payload token with a different
    Idempotency-Key. A normal idempotent replay is handled before this
    table is touched.
    """

    __tablename__ = "wallet_proof_token_uses"
    __table_args__ = (
        UniqueConstraint(
            "proof_payload_hash",
            name="uq_wallet_proof_payload_hash",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tg_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )
    global_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            f"{SCHEMA}.users.global_id",
            name="fk_wallet_proof_global_users_global_id",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
        comment="Канонический account owner proof marker.",
    )
    wallet_address: Mapped[str] = mapped_column(Text, nullable=False)
    proof_payload_hash: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("timezone('utc', now())"),
    )
