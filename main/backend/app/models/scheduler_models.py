"""backend/app/models/scheduler_models.py

Канон:
- Все ORM-таблицы живут в efhc_core (DB_SCHEMA_CORE).
- Миграция 0001 поднимает таблицы строго из Base.metadata.

Эта модель нужна, потому что /sync/me ставит фолбэк-задачу
на догон генерации (scheduler_task_log). Таблица обязана быть в ORM,
чтобы не было runtime-DDL и рассинхрона с миграциями.
"""

from __future__ import annotations

from app.core.config_core import get_settings
from app.models.base import Base
from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    func,
)

_settings = get_settings()
CORE_SCHEMA = getattr(_settings, "DB_SCHEMA_CORE", "efhc_core")


class SchedulerTaskLog(Base):
    __tablename__ = "scheduler_task_log"
    __table_args__ = (
        ForeignKeyConstraint(
            ["global_id"],
            [f"{CORE_SCHEMA}.users.global_id"],
            name="fk_scheduler_task_log_global_id_users_global_id",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "global_id IS NULL OR "
            "global_id BETWEEN 1 AND 9999999999",
            name="ck_scheduler_task_log_global_id_range",
        ),
        Index(
            "ix_scheduler_task_log_status_retry_time",
            "status",
            "retry_time",
        ),
        Index(
            "ix_scheduler_task_log_global_id",
            "global_id",
        ),
        {"schema": CORE_SCHEMA},
    )

    id = Column(BigInteger, primary_key=True)
    global_id = Column(BigInteger, nullable=True)
    task_name = Column(String(128), nullable=False)
    status = Column(String(32), nullable=False)
    error_text = Column(Text, nullable=True)
    payload = Column(JSON, nullable=True)

    retry_time = Column(DateTime(timezone=True), nullable=True)
    executed_at = Column(DateTime(timezone=True), nullable=True)
    duration_sec = Column(Integer, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
