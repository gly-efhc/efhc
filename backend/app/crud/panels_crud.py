# backend/app/crud/panels_crud.py
# ======================================================================
# CRUD уровня БД для сущностей панелей:
# - создание панели пользователю (ставка per-sec);
# - выборка активных панелей с курсором (без OFFSET);
# - безопасная блокировка панелей под начисление (SKIP LOCKED);
# - накопление generated_kwh с округлением вниз до d8;
# - reconcile проверки целостности generated_kwh/last_generated_at.
#
# Канон:
# per-sec ставки берутся только из Settings через SSOT helper.
# В БД панель хранит base_gen_per_sec (Decimal d8).
# Денежных операций EFHC здесь нет: только данные панелей.
# ======================================================================
from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from decimal import Decimal
from typing import cast

from app.core.config_core import get_settings
from app.core.logging_core import get_logger
from app.core.system_locks import (
    GEN_PER_SEC_BASE_KWH_CANON,
    get_rate_base_d8,
    get_rate_vip_d8,
)
from app.deps import d8
from app.lib.time import utcnow
from app.models.panels_models import Panel, panel_is_operational_clause
from app.utils.cursor_codec import decode_cursor, encode_cursor
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)
settings = get_settings()


# Канон per-sec ставок (SSOT helper; без локальных копий литералов)
def _canon_rate_base_d8() -> Decimal:
    return cast(Decimal, get_rate_base_d8())


def _canon_rate_vip_d8() -> Decimal:
    return cast(Decimal, get_rate_vip_d8())


# Срок жизни панели по умолчанию (дней)
DEFAULT_PANEL_LIFETIME_DAYS: int = 180

# Максимум активных панелей у пользователя (канон)
MAX_PANELS: int = int(getattr(settings, "MAX_PANELS", 1000) or 1000)


# ======================================================================
# ВСПОМОГАТЕЛЬНОЕ: генерация курсора из записи панели
# ----------------------------------------------------------------------


def _make_cursor_for_panel(p: Panel) -> str:
    """
    Курсор строим по (created_at, id) — стабильный порядок, без OFFSET.
    """
    return cast(
        str,
        encode_cursor(
            {"ts": p.created_at.isoformat(), "id": int(p.id)}
        ),
    )


# ======================================================================
# CREATE
# ----------------------------------------------------------------------
async def create_panel(
    db: AsyncSession,
    *,
    global_id: int,
    base_gen_per_sec: Decimal | None = None,
    lifetime_days: int = DEFAULT_PANEL_LIFETIME_DAYS,
    now: datetime | None = None,
) -> Panel:
    """Reject direct creation: it bypasses paid atomic PNL issuance.

    All purchases, including ADMIN actions and batch purchases, must go
    through services.panels_service.activate_panel with Idempotency-Key.
    Keeping this compatibility symbol fail-closed prevents legacy callers
    from creating unnumbered, unpaid records on an existing TEST schema.
    """
    raise RuntimeError(
        "Direct panel creation is forbidden; use canonical paid "
        "panels_service.activate_panel with Idempotency-Key."
    )

# ======================================================================
# READ: одна панель, счётчики, лимиты
# ----------------------------------------------------------------------
async def get_panel(db: AsyncSession, panel_id: int) -> Panel | None:
    """Возвращает панель по id (или None)."""
    res = await db.execute(select(Panel).where(Panel.id == panel_id))
    return res.scalars().first()


async def count_active_by_user(db: AsyncSession, global_id: int) -> int:
    """Считает активные панели пользователя."""
    stmt = select(func.count(Panel.id)).where(
        and_(
            Panel.global_id == global_id,
            Panel.is_active.is_(True),
            panel_is_operational_clause(),
        )
    )
    res = await db.execute(stmt)
    return int(res.scalar_one() or 0)


# ======================================================================
# LIST: активные панели пользователя (курсоры без OFFSET)
# ----------------------------------------------------------------------
async def list_active_by_user_cursor(
    db: AsyncSession,
    *,
    global_id: int,
    limit: int = 50,
    next_cursor: str | None = None,
    asc: bool = False,
) -> tuple[list[Panel], str | None]:
    """
    Возвращает страницу активных панелей пользователя.
    Пагинация — по курсору (created_at, id), без OFFSET.
    """
    limit = max(1, min(int(limit), 200))

    created_from: datetime | None = None
    id_from: int | None = None
    if next_cursor:
        payload = decode_cursor(next_cursor)
        ts = payload.get("ts")
        created_from = datetime.fromisoformat(ts) if ts else None
        raw_id = payload.get("id")
        if raw_id is not None:
            id_from = int(raw_id or 0)

    q = select(Panel).where(
        and_(
            Panel.global_id == global_id,
            Panel.is_active.is_(True),
            panel_is_operational_clause(),
        )
    )

    if created_from is not None and id_from is not None:
        # курсор: (created_at, id)
        if asc:
            q = q.where(
                or_(
                    Panel.created_at > created_from,
                    and_(
                        Panel.created_at == created_from,
                        Panel.id > id_from,
                    ),
                )
            )
        else:
            q = q.where(
                or_(
                    Panel.created_at < created_from,
                    and_(
                        Panel.created_at == created_from,
                        Panel.id < id_from,
                    ),
                )
            )

    # порядок стабилен, курсор построен аналогично
    if asc:
        q = q.order_by(Panel.created_at.asc(), Panel.id.asc())
    else:
        q = q.order_by(Panel.created_at.desc(), Panel.id.desc())

    q = q.limit(limit)
    res = await db.execute(q)
    items: list[Panel] = list(res.scalars().all())

    next_c = None
    if items and len(items) == limit:
        next_c = _make_cursor_for_panel(items[-1])
    return items, next_c


# ======================================================================
# LOCK-FETCH: выдача активных панелей для начисления энергии
# ----------------------------------------------------------------------
async def lock_active_panels_for_energy(
    db: AsyncSession,
    *,
    limit: int = 500,
) -> list[Panel]:
    """
    Возвращает пакет активных панелей под начисление,
    с FOR UPDATE SKIP LOCKED.
    блокируя их SKIP LOCKED — чтобы несколько воркеров не обрабатывали
    одни и те же панели.
    Порядок: по id (стабильно).
    """
    limit = max(1, min(int(limit), 2000))
    q = (
        select(Panel)
        .where(
            Panel.is_active.is_(True),
            panel_is_operational_clause(),
        )
        .order_by(Panel.id.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    res = await db.execute(q)
    panels: list[Panel] = list(res.scalars().all())
    return panels


# ======================================================================
# UPDATE: накапливание энергии по панели
# ----------------------------------------------------------------------
async def accrue_generated_kwh(
    db: AsyncSession,
    *,
    panel_id: int,
    delta_kwh: Decimal,
    new_last_generated_at: datetime | None = None,
) -> Panel | None:
    """Накопить generated_kwh на панели и обновить last_generated_at."""

    if delta_kwh <= 0:
        # ничего не делаем — это не ошибка
        logger.debug(
            "accrue_generated_kwh: skip non - positive "
            "delta (panel_id=%s, delta=%s)",
            panel_id,
            delta_kwh,
        )
        res = await db.execute(
            select(Panel).where(Panel.id == panel_id)
        )
        return res.scalars().first()

    stmt = select(Panel).where(
        and_(
            Panel.id == panel_id,
            Panel.is_active.is_(True),
            panel_is_operational_clause(),
        )
    )
    res = await db.execute(stmt)
    p: Panel | None = res.scalars().first()
    if not p:
        return None

    # вычисляем новое значение
    new_val = d8(Decimal(p.generated_kwh or 0) + Decimal(delta_kwh))
    p.generated_kwh = new_val
    if new_last_generated_at:
        p.last_generated_at = new_last_generated_at
    await db.flush()
    return p


# ======================================================================
# RECONCILE / HEALING: самовосстановительные помощники
# ----------------------------------------------------------------------
async def reconcile_negative_or_nulls(db: AsyncSession) -> int:
    """
    ИИ-защита: приводит поля generated_kwh к допустимым значениям.
    • Если где-то generated_kwh < 0 — поднимаем до 0.
    • last_generated_at NULL — ставим created_at.
    Возвращает количество «подлеченных» строк.
    """
    fixed = 0

    # generated_kwh < 0 → 0
    stmt = select(Panel).where(
        and_(Panel.generated_kwh.isnot(None), Panel.generated_kwh < 0)
    )
    res = await db.execute(stmt)
    bad_panels: list[Panel] = list(res.scalars().all())
    for p in bad_panels:
        p.generated_kwh = d8(0)
        fixed += 1

    # last_generated_at is NULL → created_at
    stmt = select(Panel).where(Panel.last_generated_at.is_(None))
    res = await db.execute(stmt)
    missing_ts: list[Panel] = list(res.scalars().all())
    for p in missing_ts:
        p.last_generated_at = p.created_at
        fixed += 1

    if fixed:
        await db.flush()
        logger.warning("reconcile_negative_or_nulls: fixed=%s", fixed)
    return fixed


# ======================================================================
# ВСПОМОГАТЕЛЬНОЕ: правка ставки на канон (если нужно).
# ----------------------------------------------------------------------
async def force_reset_base_rate_to_canon(
    db: AsyncSession,
    *,
    panel_ids: Sequence[int],
) -> int:
    """
    Опционально: для аварийного исправления панелей, которым ошибочно
    проставили «не каноническую» ставку base_gen_per_sec.
    Здесь просто возвращаем значение на GEN_PER_SEC_BASE_KWH (не VIP!).
    Возвращает число обновлённых строк.
    """
    if not panel_ids:
        return 0
    q = (
        update(Panel)
        .where(Panel.id.in_(list(panel_ids)))
        .values(base_gen_per_sec=d8(GEN_PER_SEC_BASE_KWH_CANON))
    )
    res = await db.execute(q.returning(Panel.id))
    n = len(list(res.scalars().all()))
    if n:
        await db.flush()
        logger.warning("force_reset_base_rate_to_canon: fixed=%s", n)
    return n


# ======================================================================
# Пояснения для ревью:
# • archive — это состояние строки Panel: is_active=false + archived_at;
#   отдельной таблицы архива нет.
# • lock_active_panels_for_energy использует SKIP LOCKED между workers.
# • accrue_generated_kwh изменяет только энергию панели, не EFHC balances.
# ======================================================================
