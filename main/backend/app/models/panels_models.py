# backend/app/models/panels_models.py
# ======================================================================
# Назначение кода:
# ORM-модель домена «Панели» EFHC Bot:
# • Panel — панели пользователя в одной таблице.
# • Канон SSOT для Panels опирается на activated_at/expires_at и
#   вычисляет Active/Archive через сравнение server_now_utc
#   с expires_at.
# • Некоторые поля ниже могут быть legacy-совместимостью (не SSOT)
#   и должны постепенно выводиться из использования на уровне сервисов.
#
# Канон/инварианты:
# • Генерация энергии считается только в сервисах (per-sec ставки
# GEN_PER_SEC_BASE_KWH / GEN_PER_SEC_VIP_KWH).
# • Никаких «суточных» полей. Все суммы энергии — Decimal(30,8), без
# отрицательных значений.
# • Архивация панели: is_active=false, archived_at NOT NULL;
#   активация новой — через банк (в сервисах).
# • Лимит на пользователя: 1000 активных панелей
#   (контроль — в сервисах).
#
# ИИ-защиты:
# • Индексы под курсорную пагинацию (created_at,id) и выборки по
# пользователю/активности/сроку.
# • Поля last_generated_at и generated_kwh — для «догон-начисления» при
# сбоях/перезапусках.
# • meta(JSONB) — безопасное расширение (например, источник активации,
#   SKU, примечания аудита).
#
# Запреты:
# • Модель НЕ выполняет расчётов/списаний/начислений и не проверяет
#   лимиты — это делает сервис.
# • Никакой автокоррекции балансов пользователя — только чтение и
#   хранение фактов о панелях.
# ======================================================================

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Numeric

from ..core.config_core import get_settings
from ..core.sql_aliases_core import canon_schema
from .base import Base

settings = get_settings()
CORE_SCHEMA = canon_schema(settings.DB_SCHEMA_CORE)
# например, "efhc_core"


class Panel(Base):
    """
    Панель пользователя (активная или архивная).

    Поля:
      • global_id        — канонический владелец панели.
      • is_active          — флаг активности; FALSE ⇒ панель в архиве.
      • created_at         — дата создания (момент активации).
      • expires_at — дата окончания срока (например, +180 дней).
      • archived_at — дата архивирования (для неактивных панелей).
      • last_generated_at — последний момент, до которого начислена
        энергия «догоном».
      • base_gen_per_sec — ставка генерации, зафиксированная при
        создании (аудитное поле).
      • generated_kwh — накопленная энергия по панели (d8, ≥ 0).
      • title — имя/серия (опционально для UI).
      • meta — расширения (SKU, источник заказа и т.д.).
    """

    __tablename__ = "panels"
    __table_args__ = (
        # Никаких отрицательных энергий/ставок
        CheckConstraint(
            "generated_kwh >= 0",
            name="ck_panels_generated_nonneg",
        ),
        CheckConstraint(
            "base_gen_per_sec >= 0",
            name="ck_panels_base_rate_nonneg",
        ),
        # Каноничный инвариант времени для SSOT Panels
        CheckConstraint(
            "expires_at > activated_at",
            name="ck_panels_expires_gt_activated",
        ),
        UniqueConstraint(
            "public_id",
            name="uq_panels_public_id",
        ),
        CheckConstraint(
            "public_id ~ '^PNL-[0-9]{8}$' AND public_id <> 'PNL-00000000'",
            name="ck_panels_public_id_pnl8",
        ),
        ForeignKeyConstraint(
            ["global_id"],
            [f"{CORE_SCHEMA}.users.global_id"],
            name="fk_panels_global_id_users_global_id",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "global_id BETWEEN 1 AND 9999999999",
            name="ck_panels_global_id_range",
        ),
        {"schema": CORE_SCHEMA},
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    # Канонический владелец business-объекта
    global_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    # Статус жизненного цикла
    is_active: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
        server_default="true",
        index=True,
    )

    # Совместимость с тестами: явный флаг архивирования.
    is_archived: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        server_default="false",
        index=True,
    )

    # Публичный PNL+8, выданный один раз в оплаченной транзакции.
    # Не выводить из внутреннего id и не заполнять после INSERT.
    public_id: Mapped[str] = mapped_column(
        String(12),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Канон SSOT: дата активации панели = дата активации/создания
    activated_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
        index=True,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
        index=True,
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
        index=True,
    )

    # Данные для «догон-начисления»
    last_generated_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
        index=True,
    )

    # Ставка (для аудита) и накопленная энергия
    base_gen_per_sec: Mapped[str] = mapped_column(
        Numeric(30, 8),
        nullable=False,
        default="0",
        server_default="0",
    )
    generated_kwh: Mapped[str] = mapped_column(
        Numeric(30, 8),
        nullable=False,
        default="0",
        server_default="0",
    )

    # UI/расширения
    title: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    meta: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    # Авто-обновление updated_at
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        """Диагностическое представление панели для логов."""
        st = "active" if self.is_active else "archived"
        return (
            f"<Panel id={self.id} global_id={self.global_id} "
            f"{st} gen={self.generated_kwh}>"
        )


def panel_is_operational_clause():
    """SQLAlchemy guard: обычный контур Панелей не читает мёртвые строки."""

    return func.coalesce(
        Panel.meta["protectively_voided"].as_boolean(),
        false(),
    ).is_(False)


# Индексы под курсоры и быстрые выборки
Index(
    "ix_panels_created_id",
    Panel.created_at,
    Panel.id,
    postgresql_using="btree",
)
Index(
    "ix_panels_global_id",
    Panel.global_id,
    postgresql_using="btree",
)
Index(
    "ix_panels_global_active",
    Panel.global_id,
    Panel.is_active,
    postgresql_using="btree",
)
Index(
    "ix_panels_global_expire",
    Panel.global_id,
    Panel.expires_at,
    postgresql_using="btree",
)
Index(
    "ix_panels_global_activated",
    Panel.global_id,
    Panel.activated_at,
    postgresql_using="btree",
)

__all__ = [
    "Panel",
    "panel_is_operational_clause",
]
# ======================================================================
# Пояснения «для чайника»:
# • Где хранится «архив»?
# В той же таблице: is_active=false и заполнено archived_at.
# Это упрощает
# витрины и миграции.
#
# • Зачем base_gen_per_sec в панели, если расчёт по пользователю?
# Это аудиторское поле и подсказка для UI. Фактическое
# начисление делает energy_service, опираясь на текущий
# is_vip пользователя и канонические GEN_PER_SEC_*.
#
# • Что делает last_generated_at?
# Помогает планировщику «догонять» начисления: сколько
# времени с последнего тика надо
# домножить на ставку при восстановлении после сбоя/перезапуска.
# ======================================================================
