# backend/app/services/admin/admin_panels_service.py
# ----------------------------------------------------------------------
# EFHC Bot — Панели пользователей (админ-управление)
# ----------------------------------------------------------------------
# Назначение:
# • Административное управление Панелями пользователей:
# - просмотр обычных Панелей без dead-записей;
# - защитная ручная деактивация по точному Panel ID;
# - платная повторная активация только мёртвой Панели;
# - health-сводка по обычному Panel contour.
#
# Ключевые инварианты канона:
# 1) Финансовые Admin lifecycle операции делегируются каноническому
#    protective service; этот facade сам не владеет commit/rollback.
# • Защитная деактивация рассчитывает net refund и energy void атомарно.
# • Повторная активация мёртвой Панели списывает свежие 100 EFHC.
# 2) Максимум панелей на пользователя — MAX_PANELS_PER_USER (по канону
# 1000).
# • Админ не может создать/активировать панель, если лимит достигнут.
# 3) Генерация энергии по панелям делается ТОЛЬКО через energy_service:
# • last_generated_at / expires_at используются для идемпотентного
# начисления kWh; здесь мы не вмешиваемся в генерацию.
# 4) Панель считается:
# • активной, если is_active = TRUE и NOW() < expires_at;
# • истёкшей, если NOW() >= expires_at (is_active может быть TRUE или
# FALSE).
# 5) Все критичные админ-действия логируются (AdminLogger) и,
# при необходимости, сопровождаются уведомлениями (AdminNotifier).
#
# ИИ-защита:
# • Проверка лимитов панелей.
# • Защита от «бессмысленных» операций (повторная
# активация/деактивация).
# • Health-диагностика: аномалии по last_generated_at/expires_at.
# ----------------------------------------------------------------------

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from app.core.config_core import get_settings
from app.core.logging_core import get_logger
from app.lib.time import utcnow
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.engine import Result
from sqlalchemy.ext.asyncio import AsyncSession

from .admin_rbac import RBAC, AdminRole, AdminUser

logger = get_logger(__name__)
S = get_settings()

SCHEMA_CORE: str = (
    getattr(S, "DB_SCHEMA_CORE", "efhc_core") or "efhc_core"
)

# Максимум панелей на пользователя (канон: 1000, но можно переопределить
# в
# .env)
MAX_PANELS_PER_USER: int = int(
    getattr(S, "MAX_PANELS_PER_USER", 1000) or 1000
)

# Канонический срок жизни любой панели — 180 дней.
# Admin-операции не имеют отдельной экономики/lifetime.
PANEL_LIFESPAN_DAYS: int = 180


# ----------------------------------------------------------------------
# Ошибки уровня сервиса (для дружелюбных сообщений в админке)
# ----------------------------------------------------------------------


class PanelAdminError(Exception):
    """Базовая ошибка при админ - операциях с панелями."""


class PanelLimitExceeded(PanelAdminError):
    """Превышен лимит панелей на пользователя."""


class PanelNotFound(PanelAdminError):
    """Панель не найдена или не принадлежит пользователю."""


class FreePanelActivationForbidden(PanelAdminError):
    """Бесплатная admin-активация панели запрещена."""


# ----------------------------------------------------------------------
# DTO для админки
# ----------------------------------------------------------------------


class PanelToggleRequest(BaseModel):
    """
    Запрос на включение/выключение панели пользователя.

    Сценарии:
      • panel_id всегда обязателен; Admin работает с точной Панелью;
      • activate = False → защитная ручная деактивация;
      • activate = True → повторная платная активация только dead Панели;
      • обе операции требуют Idempotency-Key и root transaction владельца.
    """

    global_id: int = Field(
        ...,
        description="global_id пользователя (канон)",
    )
    panel_id: int | None = Field(
        default=None,
        description="ID панели (если выключаем конкретную)",
    )
    activate: bool = Field(
        True,
        description="True — включить, False — выключить",
    )
    lifespan_days: int | None = Field(
        default=None,
        ge=180,
        le=180,
        description="Канонический срок жизни панели: только 180 дней",
    )
    idempotency_key: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        description="Idempotency-Key для финансовой Admin Panel операции",
    )

    @field_validator("global_id")
    def _v_global_id(cls, v: int) -> int:
        """Validate panel_id is None or > 0."""
        if v <= 0:
            raise ValueError("global_id должен быть > 0")
        return v

    @field_validator("panel_id")
    def _v_pid(cls, v: int | None) -> int | None:
        """Validate global_id > 0."""
        if v is not None and v <= 0:
            raise ValueError("panel_id должен быть > 0")
        return v


class PanelBrief(BaseModel):
    """Краткое описание панели для списка в админке."""

    id: int
    global_id: int
    is_active: bool
    activated_at: str | None
    expires_at: str | None
    archived_at: str | None = None
    # Compatibility-only API field: старая Admin DTO называла это
    # deactivated_at, хотя такого столбца никогда нет в canonical schema.
    # Значение зеркалит archived_at; новый код использует archived_at.
    deactivated_at: str | None = None
    last_generated_at: str | None
    generated_kwh: str


class PanelsHealthSnapshot(BaseModel):
    """
    Health-сводка по панелям:
      • общее количество,
      • активные/истёкшие,
      • аномалии (для ИИ-диагностики).
    """

    total_panels: int
    active_panels: int
    expired_panels: int
    anomalous_last_gt_expiry: int
    anomalous_last_in_future: int
    anomalous_expired_but_active: int


# ----------------------------------------------------------------------
# Вспомогательные функции
# ----------------------------------------------------------------------


def _now_utc() -> datetime:
    """Return current UTC timestamp."""
    return cast(datetime, utcnow())


def _to_iso(value: object) -> str | None:
    """Return ISO string for datetime-like values."""
    if value is None:
        return None
    iso = getattr(value, "isoformat", None)
    return iso() if callable(iso) else None


async def _count_user_panels(db: AsyncSession, global_id: int) -> int:
    """Возвращает количество панелей пользователя (любых)."""
    r: Result = await db.execute(
        text(
            """
            SELECT COUNT(1) AS cnt
            FROM efhc_core.panels
            WHERE global_id = :global_id
              AND COALESCE(meta ->> 'protectively_voided', 'false') <> 'true'"""
        ),
        {"global_id": int(global_id)},
    )
    row = r.fetchone()
    return int(row.cnt or 0) if row else 0


async def _count_user_active_panels(
    db: AsyncSession,
    global_id: int,
    *,
    now: datetime,
) -> int:
    """Считать только фактически active и ещё не истёкшие панели."""
    r: Result = await db.execute(
        text(
            """
            SELECT COUNT(1) AS cnt
            FROM efhc_core.panels
            WHERE global_id = :global_id
              AND is_active = TRUE
              AND expires_at > :now
              AND COALESCE(meta ->> 'protectively_voided', 'false') <> 'true'"""
        ),
        {"global_id": int(global_id), "now": now},
    )
    row = r.fetchone()
    return int(row.cnt or 0) if row else 0


async def _lock_user_panel_lifecycle(
    db: AsyncSession,
    global_id: int,
) -> None:
    """Сериализовать create/reactivate limit-check для одного owner."""

    row = (
        await db.execute(
            text(
                """
                SELECT global_id
                  FROM efhc_core.users
                 WHERE global_id = :global_id
                 FOR UPDATE
                """
            ),
            {"global_id": int(global_id)},
        )
    ).first()
    if row is None:
        raise PanelAdminError("Пользователь не найден")


async def _ensure_user_exists(db: AsyncSession, global_id: int) -> None:
    """Проверка существования пользователя (для дружелюбной ошибки)."""
    r: Result = await db.execute(
        text(
            """
            SELECT 1
            FROM efhc_core.users
            WHERE global_id = :global_id
            LIMIT 1"""
        ),
        {"global_id": int(global_id)},
    )
    if not r.fetchone():
        raise PanelAdminError("Пользователь не найден")


# ----------------------------------------------------------------------
# AdminPanelsService — операции над панелями
# ----------------------------------------------------------------------


class AdminPanelsService:
    """Сервис административного управления Панелями."""

    # ---
    # ВКЛЮЧЕНИЕ / ВЫКЛЮЧЕНИЕ ПАНЕЛЕЙ
    # ---

    @staticmethod
    async def toggle_panel(
        db: AsyncSession,
        req: PanelToggleRequest,
        admin: AdminUser,
    ) -> Any:
        """Совместимый facade платной reactivation и protective void."""
        RBAC.require_role(admin, AdminRole.MODERATOR)
        await _ensure_user_exists(db, req.global_id)
        if not req.panel_id:
            raise PanelAdminError(
                "Для защитной Admin-операции обязателен точный Panel ID."
            )
        if not req.idempotency_key:
            raise PanelAdminError(
                "Idempotency-Key обязателен для финансовой Admin Panel операции."
            )
        return await AdminPanelsService.set_panel_active(
            db,
            panel_id=int(req.panel_id),
            activate=bool(req.activate),
            admin=admin,
            expected_global_id=int(req.global_id),
            idempotency_key=str(req.idempotency_key),
        )

    @staticmethod
    async def set_panel_active(
        db: AsyncSession,
        *,
        panel_id: int,
        activate: bool,
        admin: AdminUser,
        expected_global_id: int | None = None,
        idempotency_key: str | None = None,
    ) -> Any:
        """Выполнить каноническую финансовую Admin lifecycle-операцию Панели."""
        RBAC.require_role(admin, AdminRole.MODERATOR)
        idem = str(idempotency_key or "").strip()
        if not idem:
            raise PanelAdminError(
                "Idempotency-Key обязателен для финансовой Admin Panel операции."
            )

        from .admin_panel_protective_service import (
            PanelProtectiveError,
            protectively_deactivate_panel_nocommit,
            reactivate_dead_panel_nocommit,
        )

        if expected_global_id is not None:
            owner_row = (
                await db.execute(
                    text(
                        """
                        SELECT global_id
                          FROM efhc_core.panels
                         WHERE id = :panel_id
                        """
                    ),
                    {"panel_id": int(panel_id)},
                )
            ).fetchone()
            if owner_row is None or int(owner_row[0]) != int(expected_global_id):
                raise PanelNotFound(f"Панель #{panel_id} не найдена")

        try:
            if activate:
                return await reactivate_dead_panel_nocommit(
                    db,
                    panel_id=int(panel_id),
                    admin=admin,
                    idempotency_key=idem,
                )
            return await protectively_deactivate_panel_nocommit(
                db,
                panel_id=int(panel_id),
                admin=admin,
                idempotency_key=idem,
            )
        except PanelProtectiveError as exc:
            if exc.code == "ADMIN_PANEL_NOT_FOUND":
                raise PanelNotFound(f"Панель #{panel_id} не найдена") from exc
            if activate and exc.code == "ADMIN_PANEL_NOT_DEAD":
                raise FreePanelActivationForbidden(
                    "Повторная Admin-активация разрешена только для мёртвой Панели."
                ) from exc
            raise

    @staticmethod
    async def _deactivate_panel(
        db: AsyncSession,
        req: PanelToggleRequest,
        admin: AdminUser,
    ) -> Any:
        """Legacy-имя; делегирует канонической protective operation."""
        if not req.panel_id:
            raise PanelAdminError(
                "Защитная деактивация требует точный Panel ID."
            )
        return await AdminPanelsService.toggle_panel(db, req, admin)

    # ---
    # ПРОСМОТР ПАНЕЛЕЙ ПОЛЬЗОВАТЕЛЯ
    # ---

    @staticmethod
    async def list_user_panels(
        db: AsyncSession,
        *,
        global_id: int,
        include_expired: bool = True,
    ) -> list[PanelBrief]:
        """
        Возвращает список панелей пользователя для админки.

        Параметры:
          • global_id — внутренний ID пользователя.
          • include_expired — если False, только активные панели.
        """
        await _ensure_user_exists(db, global_id)

        where = [
            "global_id = :global_id",
            "COALESCE(meta ->> 'protectively_voided', 'false') <> 'true'",
        ]
        params: dict[str, Any] = {"global_id": int(global_id)}

        if not include_expired:
            where.append("is_active = TRUE")

        sql = text(
            "\n".join(
                [
                    "SELECT",
                    "    id,",
                    "    global_id,",
                    "    is_active,",
                    "    activated_at,",
                    "    expires_at,",
                    "    archived_at,",
                    "    last_generated_at,",
                    "    COALESCE(generated_kwh, 0) AS generated_kwh",
                    "FROM efhc_core.panels",
                    f"WHERE {' AND '.join(where)}",
                    "ORDER BY id DESC",
                ]
            )
        )
        r: Result = await db.execute(sql, params)

        out: list[PanelBrief] = []
        for row in r.fetchall():
            activated_at = _to_iso(getattr(row, "activated_at", None))
            expires_at = _to_iso(getattr(row, "expires_at", None))
            archived_at = _to_iso(getattr(row, "archived_at", None))
            last_generated_at = _to_iso(
                getattr(row, "last_generated_at", None)
            )
            out.append(
                PanelBrief(
                    id=int(row.id),
                    global_id=int(row.global_id),
                    is_active=bool(row.is_active),
                    activated_at=activated_at,
                    expires_at=expires_at,
                    archived_at=archived_at,
                    deactivated_at=archived_at,
                    last_generated_at=last_generated_at,
                    generated_kwh=str(row.generated_kwh),
                )
            )
        return out

    # ---
    # HEALTH-ДИАГНОСТИКА ПАНЕЛЕЙ (ИИ-поддержка)
    # ---

    @staticmethod
    async def panels_health_snapshot(
        db: AsyncSession,
    ) -> PanelsHealthSnapshot:
        """
        Лёгкая health - диагностика таблицы panels:

          • total_panels          — всего панелей в системе;
          • active_panels         — is_active = TRUE;
          • expired_panels — is_active=FALSE или expires_at < NOW();
          • anomalous_last_gt_expiry
               — число панелей с last_generated_at > expires_at;
          • anomalous_last_in_future
               — количество панелей, где last_generated_at > NOW();
          • anomalous_expired_but_active
               — количество панелей, у которых is_active = TRUE,
                 но expires_at < NOW() (логическая аномалия).

        Функция не меняет данные. Пригодна для периодического
        мониторинга и отображения в админ - дэшборде.
        """
        _now_utc()

        # Общая статистика
        r1: Result = await db.execute(
            text(
                """
            SELECT
                    COUNT(1) AS total_panels,
                    SUM(CASE WHEN is_active THEN 1 ELSE 0 END)
                      AS active_panels
                FROM efhc_core.panels
                WHERE COALESCE(meta ->> 'protectively_voided', 'false') <> 'true'
                """
            )
        )
        s1: Any = r1.fetchone() or {}
        total_panels = int(getattr(s1, "total_panels", 0) or 0)
        active_panels = int(getattr(s1, "active_panels", 0) or 0)

        # Истёкшие панели (по expires_at)
        r2: Result = await db.execute(
            text(
                """
            SELECT COUNT(1) AS expired_panels
                FROM efhc_core.panels
                WHERE expires_at < NOW()
                  AND COALESCE(meta ->> 'protectively_voided', 'false') <> 'true'
                """
            )
        )
        s2: Any = r2.fetchone() or {}
        expired_panels = int(getattr(s2, "expired_panels", 0) or 0)

        # Аномалия: last_generated_at > expires_at
        r3: Result = await db.execute(
            text(
                """
            SELECT COUNT(1) AS cnt
                FROM efhc_core.panels
                WHERE last_generated_at IS NOT NULL
                  AND expires_at IS NOT NULL
                  AND last_generated_at > expires_at
                  AND COALESCE(meta ->> 'protectively_voided', 'false') <> 'true'
                """
            )
        )
        s3: Any = r3.fetchone() or {}
        anomalous_last_gt_expiry = int(getattr(s3, "cnt", 0) or 0)

        # Аномалия: last_generated_at в будущем
        r4: Result = await db.execute(
            text(
                """
            SELECT COUNT(1) AS cnt
                FROM efhc_core.panels
                WHERE last_generated_at IS NOT NULL
                  AND last_generated_at > NOW()
                  AND COALESCE(meta ->> 'protectively_voided', 'false') <> 'true'
                """
            )
        )
        s4: Any = r4.fetchone() or {}
        anomalous_last_in_future = int(getattr(s4, "cnt", 0) or 0)

        # Аномалия: is_active = TRUE, но expires_at < NOW()
        r5: Result = await db.execute(
            text(
                """
            SELECT COUNT(1) AS cnt
                FROM efhc_core.panels
                WHERE is_active = TRUE
                  AND expires_at < NOW()
                  AND COALESCE(meta ->> 'protectively_voided', 'false') <> 'true'
                """
            )
        )
        s5: Any = r5.fetchone() or {}
        anomalous_expired_but_active = int(getattr(s5, "cnt", 0) or 0)

        return PanelsHealthSnapshot(
            total_panels=total_panels,
            active_panels=active_panels,
            expired_panels=expired_panels,
            anomalous_last_gt_expiry=anomalous_last_gt_expiry,
            anomalous_last_in_future=anomalous_last_in_future,
            anomalous_expired_but_active=anomalous_expired_but_active,
        )


__all__ = [
    "PanelAdminError",
    "PanelLimitExceeded",
    "PanelNotFound",
    "PanelToggleRequest",
    "PanelBrief",
    "PanelsHealthSnapshot",
    "AdminPanelsService",
    "FreePanelActivationForbidden",
]
