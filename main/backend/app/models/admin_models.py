# backend/app/models/admin_models.py
"""Админские ORM-модели EFHC Bot.

Только структура таблиц и связи. Без бизнес-логики.

Канон:
- Админские таблицы живут в схеме
  settings.DB_SCHEMA_ADMIN (= efhc_admin).
- Истина структуры БД = ORM (Base.metadata), 0001_init создаёт схемы и
  ORM-таблицы.
"""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
    validates,
)
from sqlalchemy.types import Numeric

from ..core.config_core import settings
from ..core.sql_aliases_core import canon_schema
from ..identity.ton_wallet_id_resolver import (
    resolve_canonical_ton_wallet_id,
)

try:
    from .base import Base
except Exception as exc:  # pragma: no cover
    msg = (
        "Не найден общий Declarative Base. Проверь "
        "backend/app/models/init.py и убедись, что он "
        "экспортирует 'Base' (DeclarativeBase)."
    )
    raise ImportError(msg) from exc


ADMIN_SCHEMA = canon_schema(settings.DB_SCHEMA_ADMIN)
CORE_SCHEMA = canon_schema(settings.DB_SCHEMA_CORE)
# канон: админ-таблицы в efhc_admin


class RoleEnum(StrEnum):
    """Роли администратора."""

    SUPERADMIN = "superadmin"
    ADMIN = "admin"
    SUPPORT = "support"
    AUDITOR = "auditor"


class AdminWhitelist(Base):
    """Белый список админов с canonical owner ``global_id``."""

    __tablename__ = "admin_whitelist"
    __table_args__ = (
        UniqueConstraint("tg_id", name="uq_admin_whitelist_telegram"),
        UniqueConstraint(
            "global_id",
            name="uq_admin_whitelist_global_id",
        ),
        UniqueConstraint("ton_wallet_id", name="uq_admin_whitelist_ton"),
        {"schema": ADMIN_SCHEMA},
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="PK записи",
    )

    tg_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        index=True,
        comment="Telegram provider subject; не actor owner",
    )
    global_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            f"{CORE_SCHEMA}.users.global_id",
            name="fk_admin_whitelist_global_users_global_id",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
        comment="Канонический account/actor owner администратора.",
    )
    ton_wallet_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        comment="ton_wallet_id: адрес TON-кошелька как provider subject",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
        comment="Статус: активен/заблокирован",
    )
    note: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Комментарий",
    )
    added_by_tg_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="Telegram ID того, кто добавил админа",
    )
    added_by_global_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            f"{CORE_SCHEMA}.users.global_id",
            name="fk_admin_whitelist_added_global_users_global_id",
            onupdate="RESTRICT",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
        comment="Канонический actor; tg_id остаётся provider metadata.",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("timezone('utc', now())"),
        comment="Когда создан (UTC)",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("timezone('utc', now())"),
        onupdate=text("timezone('utc', now())"),
        comment="Когда обновлён (UTC)",
    )

    roles: Mapped[list[AdminRole]] = relationship(
        back_populates="admin",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="AdminRole.created_at.desc()",
        lazy="selectin",
    )
    # NOTE: audit log хранит admin_id как обычный BIGINT без FK.
    # Это позволяет логировать попытки действий и не блокировать
    # бизнес-транзакции, даже если admin_id отсутствует в whitelist.

    _mapper_args_ = {"eager_defaults": True}

    @validates("ton_wallet_id")
    def _validate_ton_wallet_id(
        self,
        key: str,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None
        val = value.strip()
        if not val:
            return None
        ton_re = getattr(
            settings,
            "TON_ADDRESS_RE",
            re.compile(r"^(EQ|UQ)[A-Za-z0-9_-]{46,}$"),
        )
        if not ton_re.match(val):
            raise ValueError(
                "Некорректный TON-адрес в AdminWhitelist. "
                "Проверь формат EQ/UQ."
            )
        return val

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<AdminWhitelist id={self.id} tg_id={self.tg_id} "
            f"active={self.is_active} ton={self.ton_wallet_id!r}>"
        )


Index(
    "ix_admin_whitelist_created_at",
    AdminWhitelist.created_at.desc(),
)


class AdminNftWhitelist(Base):
    """Материализованный список владельцев специальных Admin NFT.

    Источник полномочия — не ручное добавление кошелька в таблицу, а
    обнаружение конкретного NFT-item address из TON_ADMIN_NFT_IDS внутри канонической VIP
    коллекции. Таблица хранит только вычисленное состояние текущего
    владельца, чтобы общий шлюз админ-доступа работал без отдельной модели
    привилегированного владельца. Исполнитель любой административной операции
    остаётся ``global_id`` проверенной серверной сессии.
    """

    __tablename__ = "admin_nft_whitelist"
    __table_args__ = (
        UniqueConstraint(
            "ton_wallet_id",
            name="uq_admin_nft_whitelist_ton_wallet_id",
        ),
        {"schema": ADMIN_SCHEMA},
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    ton_wallet_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment=(
            "Канонический TON provider subject резервного "
            "Admin NFT-доступа."
        ),
    )
    role: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text("'admin'"),
        comment="RBAC-совместимая роль резервного Admin NFT-доступа.",
    )
    nft_id: Mapped[str | None] = mapped_column(
        String(256),
        nullable=True,
        comment=(
            "Точный NFT-item address, обнаруженный у текущего владельца."
        ),
    )
    source: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text("'env_nft'"),
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("timezone('utc', now())"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("timezone('utc', now())"),
        onupdate=text("timezone('utc', now())"),
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    @validates("ton_wallet_id")
    def _validate_admin_nft_ton_wallet_id(
        self,
        key: str,
        value: str,
    ) -> str:
        del key
        return resolve_canonical_ton_wallet_id(value).ton_wallet_id


Index(
    "ix_admin_nft_whitelist_active_created",
    AdminNftWhitelist.is_active,
    AdminNftWhitelist.created_at.desc(),
)

Index(
    "uq_admin_nft_whitelist_active_nft_id",
    AdminNftWhitelist.nft_id,
    unique=True,
    postgresql_where=AdminNftWhitelist.is_active.is_(True),
)


class AdminRole(Base):
    """Роль администратора (много ролей на одного админа)."""

    __tablename__ = "admin_role"
    __table_args__ = (
        UniqueConstraint("admin_id", "role", name="uq_admin_role_pair"),
        {"schema": ADMIN_SCHEMA},
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="PK записи роли",
    )
    admin_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            f"{ADMIN_SCHEMA}.admin_whitelist.id",
            ondelete="CASCADE",
            onupdate="CASCADE",
            name="fk_admin_role_admin",
        ),
        nullable=False,
        index=True,
        comment="FK → AdminWhitelist.id",
    )
    role: Mapped[RoleEnum] = mapped_column(
        Enum(
            RoleEnum,
            name="enum_admin_role",
            schema=ADMIN_SCHEMA,
            create_constraint=True,
        ),
        nullable=False,
        comment="Название роли",
    )
    granted_by_tg_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="Кто назначил (Telegram ID)",
    )
    granted_by_global_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            f"{CORE_SCHEMA}.users.global_id",
            name="fk_admin_role_granted_global_users_global_id",
            onupdate="RESTRICT",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
        comment="Канонический actor назначения роли.",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("timezone('utc', now())"),
        comment="Когда назначена роль (UTC)",
    )

    admin: Mapped[AdminWhitelist] = relationship(
        back_populates="roles",
        lazy="joined",
    )

    _mapper_args_ = {"eager_defaults": True}

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<AdminRole id={self.id} admin_id={self.admin_id} "
            f"role={self.role}>"
        )


Index(
    "ix_admin_role_created_at",
    AdminRole.created_at.desc(),
)


class AdminActionLog(Base):
    """Аудит действий администраторов."""

    __tablename__ = "admin_action_log"
    __table_args__ = ({"schema": ADMIN_SCHEMA},)

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="PK записи лога",
    )

    admin_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        index=True,
        comment="Legacy local/provider audit metadata; не actor owner",
    )
    actor_global_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            f"{CORE_SCHEMA}.users.global_id",
            name="fk_admin_action_actor_global_users_global_id",
            onupdate="RESTRICT",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
        comment="Канонический actor owner административного действия.",
    )

    action: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="Короткое имя действия",
    )
    target_type: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
        comment="Тип цели",
    )
    target_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        index=True,
        comment="Идентификатор цели",
    )

    details_json: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Подробности действия в JSON",
    )

    ip: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="IP-адрес источника (если известен)",
    )
    user_agent: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="User-Agent клиента (если известен)",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("timezone('utc', now())"),
        comment="Когда зафиксировано действие (UTC)",
    )

    # NOTE: связи с AdminWhitelist намеренно нет.
    # admin_id хранится без FK, чтобы аудит писал любые попытки.
    # Это предотвращает падения ORM при конфигурации mapper.

    _mapper_args_ = {"eager_defaults": True}

    def __repr__(self) -> str:  # pragma: no cover
        tgt = f"{self.target_type}:{self.target_id}"
        return (
            f"<AdminActionLog id={self.id} admin_id={self.admin_id} "
            f"action={self.action} target={tgt}>"
        )


Index(
    "ix_admin_action_log_created_at",
    AdminActionLog.created_at.desc(),
)
Index(
    "ix_admin_action_log_action_type",
    AdminActionLog.action,
    AdminActionLog.target_type,
)


class IdempotencyKey(Base):
    """Ключи идемпотентности для опасных операций."""

    __tablename__ = "idempotency_key"
    __table_args__ = (
        UniqueConstraint("key", name="uq_idempotency_key_key"),
        {"schema": ADMIN_SCHEMA},
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="PK записи ключа",
    )

    key: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="Уникальный идемпотентный ключ (или его хэш)",
    )
    scope: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
        comment="Область применения ключа",
    )
    request_fingerprint: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        comment="Хэш входных данных запроса",
    )

    used: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
        index=True,
        comment="Признак, что ключ уже использован",
    )
    response_code: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="Код результата первой обработки",
    )
    response_payload_json: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Часть ответа первой обработки",
    )

    admin_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            f"{ADMIN_SCHEMA}.admin_whitelist.id",
            ondelete="SET NULL",
            onupdate="CASCADE",
            name="fk_idempotency_key_admin",
        ),
        nullable=True,
        index=True,
        comment="FK → AdminWhitelist.id (если из админки)",
    )
    global_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            f"{CORE_SCHEMA}.users.global_id",
            name="fk_idempotency_global_users_global_id",
            onupdate="RESTRICT",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
        comment="Канонический owner административной идемпотентности.",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("timezone('utc', now())"),
        comment="Когда создан ключ (UTC)",
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="Когда ключ истекает (UTC)",
    )

    _mapper_args_ = {"eager_defaults": True}

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<IdempotencyKey id={self.id} key={self.key} "
            f"scope={self.scope} used={self.used} "
            f"admin_id={self.admin_id}>"
        )


# ----------------------------------------------------------------------
# EFHC sale packages (pricing для deposit_efhc)
# ----------------------------------------------------------------------


class EFHCSalePackage(Base):
    """Админ-таблица прайс-пакетов продажи EFHC.

    Требуется сервисом:
    backend/app/services/admin/admin_sale_packages_service.py
    (SELECT/INSERT/UPDATE в efhc_admin.efhc_sale_packages).
    """

    __tablename__ = "efhc_sale_packages"
    __table_args__ = ({"schema": ADMIN_SCHEMA},)

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="PK пакета",
    )

    title: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="Название пакета",
    )

    asset: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'TON'"),
        comment="Актив цены (TON/USDT и т.п.)",
    )

    price_asset_d8: Mapped[Decimal] = mapped_column(
        Numeric(30, 8),
        nullable=False,
        comment="Цена в asset (scale=8)",
    )

    efhc_amount_d8: Mapped[Decimal] = mapped_column(
        Numeric(30, 8),
        nullable=False,
        comment="Сколько EFHC выдаём (scale=8)",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
        comment="Активен ли пакет",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("timezone('utc', now())"),
        comment="Когда создан (UTC)",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("timezone('utc', now())"),
        onupdate=text("timezone('utc', now())"),
        comment="Когда обновлён (UTC)",
    )


Index(
    "ix_idempotency_key_expiry",
    IdempotencyKey.expires_at,
)
Index(
    "ix_idempotency_key_scope_used",
    IdempotencyKey.scope,
    IdempotencyKey.used,
)


__all__ = [
    "RoleEnum",
    "AdminWhitelist",
    "AdminNftWhitelist",
    "AdminRole",
    "AdminActionLog",
    "IdempotencyKey",
    "EFHCSalePackage",
]


class AdminNotification(Base):
    """Сохранённое admin-уведомление для БД/Telegram-алертов."""

    __tablename__ = "admin_notifications"
    __table_args__ = (
        Index("ix_admin_notifications_status", "status"),
        Index("ix_admin_notifications_created_at", "created_at"),
        {"schema": ADMIN_SCHEMA},
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    event: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text("'NEW'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("timezone('utc', now())"),
    )
