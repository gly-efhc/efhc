"""
Модели таблиц заданий и task-bonus runtime helper tables.

Назначение:
  • tasks — справочник заданий, которые видят пользователи.
  • task_submissions — пользовательские отправки и модерация.
  • user_tasks_status — текущий статус выполнения по task_code.
  • task_bonus_log — журнал начислений бонусов по заданиям.
  • task_complete_lock — idempotency lock для ad/task credit path.

Схема БД канонически только efhc_core через settings.DB_SCHEMA_CORE.
Все денежные поля — Decimal(18, 8).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from app.core.sql_aliases_core import canon_schema
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.config_core import settings
from .base import Base, TimestampMixin

SCHEMA_TASKS = canon_schema(settings.DB_SCHEMA_CORE)


class Task(Base, TimestampMixin):
    """EFHC задание, которое создаёт админ."""

    __tablename__ = "tasks"
    __table_args__ = (
        UniqueConstraint("code", name="uq_tasks_code"),
        CheckConstraint(
            "bonus_efhc >= 0",
            name="chk_tasks_bonus_nonnegative",
        ),
        CheckConstraint(
            "limit_per_user >= 0",
            name="chk_tasks_limit_per_user_nonnegative",
        ),
        CheckConstraint(
            "(total_limit IS NULL) OR (total_limit >= 0)",
            name="chk_tasks_total_limit_nonnegative",
        ),
        {"schema": SCHEMA_TASKS},
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="Идентификатор задания.",
    )
    code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="Код задания, уникален в рамках таблицы.",
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Короткий заголовок задания.",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Описание задания, инструкции для пользователя.",
    )
    type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="custom",
        index=True,
        comment="Тип задания: subscribe/join/visit/custom/watch_ad/...",
    )
    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
        comment="Видимость задания пользователям.",
    )
    bonus_efhc: Mapped[Decimal] = mapped_column(
        "bonus_efhc",
        Numeric(18, 8),
        nullable=False,
        default=Decimal(
            str(
                getattr(
                    settings,
                    "TASK_REWARD_BONUS_EFHC_DEFAULT",
                    0,
                )
            )
        ),
        comment="Сколько бонусных EFHC начислять за выполнение.",
    )
    price_usd_hint: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 8),
        nullable=True,
        comment="Подсказка админам: сколько стоит задание в USD.",
    )
    limit_per_user: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment=(
            "Сколько раз один пользователь может выполнить задание."
        ),
    )
    total_limit: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Глобальный лимит выполнений; NULL = без лимита.",
    )
    performed_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Сколько выполнений уже одобрено.",
    )
    proof_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Тип доказательства: url/screenshot/text/none/...",
    )
    proof_hint: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Подсказка пользователю по доказательству.",
    )
    meta: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="JSON-метаданные задания для UI и portal continuity.",
    )

    submissions: Mapped[list[TaskSubmission]] = relationship(
        "TaskSubmission",
        back_populates="task",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


Index("ix_tasks_active_type", Task.active, Task.type)


class TaskSubmission(Base, TimestampMixin):
    """Отправка выполнения задания пользователем."""

    __tablename__ = "task_submissions"
    __table_args__ = (
        UniqueConstraint(
            "task_id",
            "global_id",
            name="uq_task_submissions_task_global_once",
        ),
        ForeignKeyConstraint(
            ["global_id"],
            [f"{SCHEMA_TASKS}.users.global_id"],
            name="fk_task_submissions_global_users_global_id",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "global_id BETWEEN 1 AND 9999999999",
            name="ck_task_submissions_global_id_range",
        ),
        CheckConstraint(
            "bonus_amount_efhc >= 0",
            name="chk_task_submissions_bonus_nonnegative",
        ),
        {"schema": SCHEMA_TASKS},
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="Идентификатор отправки.",
    )
    task_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(f"{SCHEMA_TASKS}.tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="FK → tasks.id",
    )
    tg_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="Telegram ID только для уведомления пользователю.",
    )
    global_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="Канонический владелец отправки задания.",
    )
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="pending",
        index=True,
        comment="Статус модерации/выплаты.",
    )
    proof_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Текстовое доказательство/комментарий.",
    )
    proof_url: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
        comment="URL-доказательство.",
    )
    bonus_amount_efhc: Mapped[Decimal] = mapped_column(
        "bonus_amount_efhc",
        Numeric(18, 8),
        nullable=False,
        default=Decimal("0.00000000"),
        comment="Сколько EFHC начислено при одобрении.",
    )
    paid: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
        comment="Флаг фактической выплаты EFHC.",
    )
    paid_tx_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        index=True,
        comment="ID внутренней EFHC-транзакции, если есть.",
    )
    moderator_global_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            f"{SCHEMA_TASKS}.users.global_id",
            name="fk_task_submissions_moderator_global_users_global_id",
            onupdate="RESTRICT",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
        comment="Канонический actor модерации по global_id.",
    )
    moderator_note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Комментарий модератора.",
    )

    task: Mapped[Task] = relationship(
        "Task",
        back_populates="submissions",
    )


Index(
    "ix_task_submissions_global_status",
    TaskSubmission.global_id,
    TaskSubmission.status,
)


class UserTaskStatus(Base):
    """Текущий статус пользователя по task_code."""

    __tablename__ = "user_tasks_status"
    __table_args__ = (
        UniqueConstraint(
            "global_id",
            "task_code",
            name="uq_user_tasks_status_global_task_code",
        ),
        ForeignKeyConstraint(
            ["global_id"],
            [f"{SCHEMA_TASKS}.users.global_id"],
            name="fk_user_tasks_status_global_users_global_id",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "global_id BETWEEN 1 AND 9999999999",
            name="ck_user_tasks_status_global_id_range",
        ),
        {"schema": SCHEMA_TASKS},
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="Идентификатор статуса.",
    )
    global_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="Канонический владелец задания.",
    )
    task_code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="Код задания.",
    )
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        index=True,
        comment="available/done/cooldown/pending_check/...",
    )
    last_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Когда задание было завершено последний раз.",
    )
    next_available_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Когда задание снова станет доступным.",
    )


Index(
    "ix_user_tasks_status_global_status",
    UserTaskStatus.global_id,
    UserTaskStatus.status,
)


class TaskBonusLog(Base):
    """Журнал начислений бонусов по заданиям."""

    __tablename__ = "task_bonus_log"
    __table_args__ = (
        UniqueConstraint(
            "idempotency_key",
            name="uq_task_bonus_log_idempotency_key",
        ),
        ForeignKeyConstraint(
            ["global_id"],
            [f"{SCHEMA_TASKS}.users.global_id"],
            name="fk_task_bonus_log_global_users_global_id",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "global_id BETWEEN 1 AND 9999999999",
            name="ck_task_bonus_log_global_id_range",
        ),
        {"schema": SCHEMA_TASKS},
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="Идентификатор записи журнала.",
    )
    global_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="Канонический владелец начисления.",
    )
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("timezone('utc', now())"),
        comment="Время начисления бонуса.",
    )
    task_code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="Код задания.",
    )
    amount_bonus_efhc: Mapped[Decimal] = mapped_column(
        Numeric(18, 8),
        nullable=False,
        comment="Сумма начисленного бонуса.",
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Идемпотентный ключ начисления.",
    )


Index(
    "ix_task_bonus_log_global_id_id",
    TaskBonusLog.global_id,
    TaskBonusLog.id,
)


class TaskCompleteLock(Base, TimestampMixin):
    """Idempotency lock для ad/task credit path."""

    __tablename__ = "task_complete_lock"
    __table_args__ = (
        UniqueConstraint(
            "idempotency_key",
            name="uq_task_complete_lock_idempotency_key",
        ),
        ForeignKeyConstraint(
            ["global_id"],
            [f"{SCHEMA_TASKS}.users.global_id"],
            name="fk_task_complete_lock_global_users_global_id",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "global_id BETWEEN 1 AND 9999999999",
            name="ck_task_complete_lock_global_id_range",
        ),
        {"schema": SCHEMA_TASKS},
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="Идентификатор lock-записи.",
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(255),
        nullable=True,
        comment="Идемпотентный ключ.",
    )
    global_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="Канонический владелец lock-записи.",
    )
    task_code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="Код задания.",
    )
    credited: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
        comment="Флаг успешного начисления бонуса.",
    )


Index(
    "ix_task_complete_lock_global_task_code",
    TaskCompleteLock.global_id,
    TaskCompleteLock.task_code,
)
