# backend/app/services/energy_service.py
# =====================================================================
# EFHC Bot — Сервис генерации энергии (только посекундные ставки,
# ИИ-самовосстановление)
# --------------------------------------------------------------------
# Назначение:
# • Начисляет энергию (kWh) по активным панелям, строго используя ТОЛЬКО
# посекундные константы из конфигурации:
# GEN_PER_SEC_BASE_KWH (без VIP)
# GEN_PER_SEC_VIP_KWH  (VIP)
# • Поддерживает два сценария:
# 1) Пакетная генерация для всего пула панелей (фоновый планировщик).
# 2) Точный «догон» генерации пользователя при открытии его экрана.
#
# Принципы и инварианты (канон):
# • Никаких «суточных» значений — только per-second ставки из конфига.
# • Балансы энергии храним раздельно:
# users.available_kwh       — доступно к обмену,
# users.total_generated_kwh — для рейтинга/достижений.
# • Идемпотентность обеспечивается panels.last_generated_at:
# начисляем Δt = min(now, expires_at) - last_generated_at; затем
# last_generated_at := min(now, expires_at). Повтор не даёт дублей.
# • Безопасная конкуренция: выбор панелей под UPDATE ... SKIP LOCKED.
# Это позволяет нескольким воркерам работать параллельно без конфликтов.
# • Округление вниз до 8 знаков — единая утилита deps.d8.
# • Пользовательские денежные балансы не затрагиваем; здесь только kWh.
#
# ИИ-самовосстановление:
# • Пакетная обработка с «мягкими» ретраями и fallback на поштучную.
# • Нештатная ситуация по панели не валит цикл — логируем и идём дальше.
# • Повторный запуск обработает «хвосты» (по last_generated_at).
#
# Таблицы (минимум):
# efhc_core.users(
# global_id,
# is_vip,
# available_kwh,
# total_generated_kwh,
# ...
# )
# efhc_core.panels(
# id,
# global_id, -- канонический владелец панели
# Связь выполняется по users.global_id.
# is_active,
# last_generated_at,
# expires_at,
# base_gen_per_sec,      -- может быть, но ставки берём из конфига
# generated_kwh,
# ...
# )
#
# Публичные функции:
# • generate_energy_tick(db, batch_size=500) -> dict
# • generate_energy_for_user(db, global_id) -> dict
# • backfill_all(db, max_passes=50, batch_size=500) -> dict
# =====================================================================

from __future__ import annotations

import asyncio
import datetime as dt
from decimal import Decimal
from typing import Any, cast

from app.core.config_core import get_settings
from app.core.logging_core import get_logger
from app.core.system_locks import (
    get_rate_base_d8,
    get_rate_vip_d8,
)
from app.deps import d8
from app.lib.time import utcnow
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def _begin_tx(db: AsyncSession) -> None:
    if getattr(db, "in_transaction", None) and db.in_transaction():
        await db.begin_nested()
    else:
        await db.begin()


logger = get_logger(__name__)
settings = get_settings()

# --------------------------------------------------------------------
# ЕДИНЫЙ источник истинных ставок — только из конфигурации
# • никаких «локальных копий» значений в коде;
# • при смене GEN_PER_SEC_* в .env сервис использует новые ставки
# без пересборки (при перезапуске приложения).
# --------------------------------------------------------------------


def _rate_base() -> Decimal:
    """
    Базовая ставка генерации (без VIP), kWh/сек, из настроек.
    """
    return cast(Decimal, get_rate_base_d8())


def _rate_vip() -> Decimal:
    """
    VIP-ставка генерации, kWh/сек, из настроек.
    """
    return cast(Decimal, get_rate_vip_d8())


# --------------------------------------------------------------------
# SQL-фрагменты (намеренно простые и прозрачные)
# --------------------------------------------------------------------

# Выборка пачки активных панелей, у которых есть что догенерировать,
# c блокировкой и пропуском занятых строк (SKIP LOCKED).
_SELECT_PANELS_BATCH_SQL = text(
    """
            SELECT p.id,
           p.global_id,
           p.last_generated_at,
           p.expires_at,
           u.is_vip
      FROM efhc_core.panels AS p
      JOIN efhc_core.users AS u ON u.global_id = p.global_id
     WHERE p.is_active = TRUE
       AND COALESCE(p.meta ->> 'protectively_voided', 'false') <> 'true'
       AND p.last_generated_at < LEAST(NOW(), p.expires_at)
     ORDER BY p.last_generated_at ASC
     FOR UPDATE SKIP LOCKED
     LIMIT :lim
    """
)

# Обновление панели: фиксируем last_generated_at и прирост по панели.
# панели)
_UPDATE_PANEL_ONE_SQL = text(
    """
            UPDATE efhc_core.panels
       SET last_generated_at = :new_ts,
           generated_kwh     = generated_kwh + :add_kwh
     WHERE id = :pid
    """
)

# Пакетное обновление пользовательской энергии (по накопленным суммам)
_UPDATE_USER_ENERGY_SQL = text(
    """
            UPDATE efhc_core.users
       SET total_generated_kwh = COALESCE(total_generated_kwh, 0)
                               + :add_kwh,
           updated_at          = NOW()
     WHERE global_id = :global_id
    """
)

# Выбор всех активных панелей конкретного пользователя под «догон»
_SELECT_USER_PANELS_SQL = text(
    """
            SELECT p.id, p.last_generated_at, p.expires_at, u.is_vip
      FROM efhc_core.panels p
      JOIN efhc_core.users u ON u.global_id = p.global_id
     WHERE p.global_id = :global_id
       AND p.is_active = TRUE
       AND COALESCE(p.meta ->> 'protectively_voided', 'false') <> 'true'
       AND p.last_generated_at < LEAST(NOW(), p.expires_at)
     ORDER BY p.last_generated_at ASC
     FOR UPDATE SKIP LOCKED
    """
)

# Быстрый bulk-догон пользователя (панели + users через CTE).
# Важно:
# • формула строго per-second (rate), без «суточных» значений;
# • округление вниз до 8 знаков: SQL trunc(..., 8).
# • от гонок: блокируем строку пользователя (FOR UPDATE) в CTE u.
_BULK_GENERATE_USER_SQL = text(
    """
    WITH u AS (
        SELECT global_id, is_vip
          FROM efhc_core.users
         WHERE global_id = :global_id
         FOR UPDATE
    ),
    params AS (
        SELECT CAST(:now_ts AS timestamptz) AS now_ts,
               CAST(:rate AS numeric)      AS rate
    ),
    locked AS (
        SELECT
            p.id,
            p.last_generated_at AS old_last_generated_at,
            LEAST(
                (SELECT now_ts FROM params),
                p.expires_at
            ) AS new_last_generated_at,
            TRUNC(
                EXTRACT(
                    EPOCH FROM (
                        LEAST(
                            (SELECT now_ts FROM params),
                            p.expires_at
                        ) - p.last_generated_at
                    )
                )::numeric * (SELECT rate FROM params),
                8
            ) AS add_kwh
          FROM efhc_core.panels AS p
          JOIN u ON u.global_id = p.global_id
         WHERE p.is_active = TRUE
           AND COALESCE(p.meta ->> 'protectively_voided', 'false') <> 'true'
           AND p.last_generated_at < LEAST(
               (SELECT now_ts FROM params),
               p.expires_at
           )
         FOR UPDATE
    ),
    upd AS (
        UPDATE efhc_core.panels AS p
           SET last_generated_at = l.new_last_generated_at,
               generated_kwh = p.generated_kwh + l.add_kwh
          FROM locked AS l
         WHERE p.id = l.id
        RETURNING l.add_kwh
    ),
    s AS (
        SELECT COALESCE(SUM(add_kwh), 0)::numeric(30,8) AS total_add
          FROM upd
    )
    UPDATE efhc_core.users AS us
       SET total_generated_kwh = COALESCE(us.total_generated_kwh, 0)
                               + (SELECT total_add FROM s),
           last_sync_at        = (SELECT now_ts FROM params),
           updated_at          = NOW()
     WHERE us.global_id = :global_id
    RETURNING (SELECT total_add FROM s) AS total_add;
    """
)


# --------------------------------------------------------------------
# Вспомогательные расчёты
# --------------------------------------------------------------------


def _now_utc() -> dt.datetime:
    """UTC now (timestamptz-compatible)."""
    return cast(dt.datetime, utcnow())


def _calc_add_kwh(delta_sec: Decimal, is_vip: bool) -> Decimal:
    """
    Возвращает ΔkWh = delta_sec * rate, округляя вниз до 8 знаков.

    ИИ-защита:
      • Для отрицательных/нулевых интервалов всегда возвращаем 0.
      • Ставка берётся только из конфигурации (_rate_base/_rate_vip).
    """
    if delta_sec <= 0:
        return cast(Decimal, d8(0))
    rate = _rate_vip() if is_vip else _rate_base()
    add = delta_sec * rate
    return d8(add)  # type: ignore[no-any-return]


def _clamp_to_expiry(
    ts_last: dt.datetime,
    ts_expire: dt.datetime,
    ts_now: dt.datetime,
) -> tuple[dt.datetime, Decimal]:
    """
    Считает last_generated_at' = min(now, expires_at) и точные Δ секунд.

    Возвращает (new_last, delta_seconds).
    ИИ-защита:
      • Если end_ts < ts_last → delta=0.
      • Дробные секунды не теряются при продвижении last_generated_at.
    """
    end_ts = ts_now if ts_now <= ts_expire else ts_expire
    elapsed = end_ts - ts_last
    delta = (
        Decimal(elapsed.days * 86400 + elapsed.seconds)
        + Decimal(elapsed.microseconds) / Decimal(1_000_000)
    )
    if delta < 0:
        delta = Decimal(0)
    return (end_ts, delta)


# --------------------------------------------------------------------
# Пакетная генерация (фоновый планировщик)
# --------------------------------------------------------------------


async def generate_energy_tick(
    db: AsyncSession,
    *,
    batch_size: int = 500,
) -> dict[str, Any]:
    """
    Обрабатывает до batch_size панелей, которым есть что догенерировать.

    Стратегия:
      1) В одной транзакции выбираем партию панелей (SKIP LOCKED).
      2) Для каждой панели считаем Δсекунд, ΔkWh и обновляем panel.
      3) После цикла — UPDATE по каждому пользователю.
         (+available_kwh, +total_generated_kwh).

    ИИ-самовосстановление:
      • Если транзакция упала (deadlock/serialize), откатываем её
        и выполняем fallback: поштучная обработка проблемных панелей
        (каждая в своей мини-транзакции, устойчива к конфликтам).

    Возвращает статистику:
      {
        "panels_processed": int,
        "users_updated": int,
        "total_kwh_added": str(Decimal),
        "partial_fallbacks": int,
      }
    """
    stats = {
        "panels_processed": 0,
        "users_updated": 0,
        "total_kwh_added": str(d8(0)),
        "partial_fallbacks": 0,
    }

    if batch_size < 1:
        batch_size = 1

    # 1) Пакетная попытка в одной транзакции (конкуренция с SKIP LOCKED)
    users_acc: dict[int, Decimal] = {}
    total_add = d8(0)
    items: list[tuple[Any, ...]] = []

    try:
        await _begin_tx(db)

        # Выбираем партию под блокировкой
        params = {"lim": int(batch_size)}
        row = await db.execute(_SELECT_PANELS_BATCH_SQL, params)
        items = [tuple(r) for r in row.fetchall()]
        if not items:
            await db.commit()
            return stats

        now_ts = _now_utc()

        # Обрабатываем панели
        for pid, global_id, last_ts, exp_ts, is_vip in items:
            try:
                new_last, delta_sec = _clamp_to_expiry(
                    last_ts,
                    exp_ts,
                    now_ts,
                )
                if delta_sec <= 0:
                    # уже догенерирована до текущего момента / истечения
                    continue

                add_kwh = _calc_add_kwh(delta_sec, bool(is_vip))
                if add_kwh < 0:
                    # защитный «предохранитель» от аномалий
                    logger.warning(
                        "energy.tick: negative add_kwh=%s panel=%s "
                        "user=%s; forcing 0",
                        add_kwh,
                        pid,
                        global_id,
                    )
                    add_kwh = d8(0)

                # Обновляем панель
                await db.execute(
                    _UPDATE_PANEL_ONE_SQL,
                    {
                        "new_ts": new_last,
                        "add_kwh": str(add_kwh),
                        "pid": int(pid),
                    },
                )

                # Накапливаем по пользователю
                if add_kwh > 0:
                    cur = users_acc.get(global_id, d8(0))
                    users_acc[global_id] = d8(cur + add_kwh)
                    total_add = d8(total_add + add_kwh)
                    panels_val = stats.get("panels_processed", 0)
                    panels_processed = (
                        panels_val if isinstance(panels_val, int) else 0
                    )
                    stats["panels_processed"] = panels_processed + 1

            except Exception as pe:
                # Не валим весь пакет — панель будет обработана
                # fallback-логикой
                logger.debug(
                    "energy.tick: panel %s batch - step failed: %s",
                    pid,
                    pe,
                )
                continue

        # Обновляем пользователей суммарно
        updated_users = 0
        for global_id, add_sum in users_acc.items():
            if add_sum <= 0:
                continue
            await db.execute(
                _UPDATE_USER_ENERGY_SQL,
                {
                    "add_kwh": str(add_sum),
                    "global_id": int(global_id),
                },
            )
            updated_users += 1

        await db.commit()
        stats["users_updated"] = updated_users
        stats["total_kwh_added"] = str(total_add)

    except Exception as e:
        # Пакет не удался — откатываем и переходим к поштучной обработке
        # (fallback)
        try:
            await db.rollback()
        except Exception:
            logger.debug(
                "energy.tick: rollback failed (batch)",
                exc_info=True,
            )
        logger.warning("energy.tick: batch failed → fallback: %s", e)
        fallback_val = stats.get("partial_fallbacks", 0)
        partial_fallbacks = (
            fallback_val if isinstance(fallback_val, int) else 0
        )
        stats["partial_fallbacks"] = partial_fallbacks + 1

        # 2) Fallback: по одной панели, каждая в своей транзакции.
        total_add = d8(0)
        stats["panels_processed"] = 0
        stats["users_updated"] = 0

        for pid, _global_id, _last_ts, _exp_ts, _is_vip in items or []:
            try:
                await _begin_tx(db)
                # заново читаем актуальные значения (могли измениться)
                q = text(
                    """
                        SELECT p.id,
                               p.global_id,
                               p.last_generated_at,
                               p.expires_at,
                               u.is_vip
                          FROM efhc_core.panels p
                          JOIN efhc_core.users u
                            ON u.global_id = p.global_id
                         WHERE p.id = :pid
                           AND p.is_active = TRUE
                           AND COALESCE(p.meta ->> 'protectively_voided', 'false') <> 'true'
                           AND p.last_generated_at < LEAST(
                               NOW(),
                               p.expires_at
                           )
                         FOR UPDATE SKIP LOCKED
                    """
                )
                row = await db.execute(q, {"pid": int(pid)})
                one = row.fetchone()
                if not one:
                    await db.rollback()
                    continue

                _, global_id2, last2, exp2, vip2 = one
                now2 = _now_utc()
                new_last2, delta2 = _clamp_to_expiry(last2, exp2, now2)
                if delta2 <= 0:
                    await db.rollback()
                    continue

                add2 = _calc_add_kwh(delta2, bool(vip2))
                if add2 < 0:
                    logger.warning(
                        "energy.tick.fallback: negative add_kwh=%s "
                        "for panel=%s, user=%s; forcing 0",
                        add2,
                        pid,
                        global_id2,
                    )
                    add2 = d8(0)

                await db.execute(
                    _UPDATE_PANEL_ONE_SQL,
                    {
                        "new_ts": new_last2,
                        "add_kwh": str(add2),
                        "pid": int(pid),
                    },
                )
                if add2 > 0:
                    await db.execute(
                        _UPDATE_USER_ENERGY_SQL,
                        {
                            "add_kwh": str(add2),
                            "global_id": int(global_id2),
                        },
                    )
                    total_add = d8(total_add + add2)
                    panels_val = stats.get("panels_processed", 0)
                    panels_processed = (
                        panels_val if isinstance(panels_val, int) else 0
                    )
                    stats["panels_processed"] = panels_processed + 1
                    # users_updated: приблизительный счётчик.
                    # Возможны дубли.
                    # по одному global_id
                    users_val = stats.get("users_updated", 0)
                    users_updated = (
                        users_val if isinstance(users_val, int) else 0
                    )
                    stats["users_updated"] = users_updated + 1
                await db.commit()
            except Exception as e2:
                try:
                    await db.rollback()
                except Exception:
                    logger.debug(
                        "energy.tick: rollback failed (fallback)",
                        exc_info=True,
                    )
                logger.error(
                    "energy.tick: fallback panel %s failed: %s", pid, e2
                )

        stats["total_kwh_added"] = str(total_add)

    return stats


# --------------------------------------------------------------------
# Точный checkpoint при смене BASE/VIP
# --------------------------------------------------------------------


async def checkpoint_energy_before_rate_change(
    db: AsyncSession,
    *,
    global_id: int,
    old_is_vip: bool,
    effective_at: dt.datetime | None = None,
) -> Decimal:
    """Начислить старую ставку точно до подтверждённой границы статуса.

    Транзакцией управляет caller: функция намеренно не делает commit.
    После успешного checkpoint caller может изменить ``users.is_vip`` в той
    же DB transaction, исключая ретроспективное применение новой ставки.
    """

    boundary = effective_at or utcnow()
    rate = _rate_vip() if old_is_vip else _rate_base()
    result = await db.execute(
        _BULK_GENERATE_USER_SQL,
        {
            "global_id": int(global_id),
            "now_ts": boundary,
            "rate": str(rate),
        },
    )
    return cast(Decimal, d8(result.scalar() or 0))


async def set_user_vip_with_energy_checkpoint(
    db: AsyncSession,
    *,
    global_id: int,
    new_is_vip: bool,
    effective_at: dt.datetime | None = None,
) -> bool:
    """Атомарно checkpoint старой ставки и переключить account VIP-state."""

    boundary = effective_at or utcnow()
    row = (
        await db.execute(
            text(
                "SELECT is_vip FROM efhc_core.users "
                "WHERE global_id = :global_id FOR UPDATE"
            ),
            {"global_id": int(global_id)},
        )
    ).first()
    if row is None:
        return False

    old_is_vip = bool(row[0])
    target = bool(new_is_vip)
    if old_is_vip != target:
        await checkpoint_energy_before_rate_change(
            db,
            global_id=int(global_id),
            old_is_vip=old_is_vip,
            effective_at=boundary,
        )

    result = await db.execute(
        text(
            """
            UPDATE efhc_core.users
               SET is_vip = :flag,
                   vip_since = CASE
                       WHEN :flag = TRUE AND :old_flag = FALSE THEN :now
                       WHEN :flag = FALSE THEN NULL
                       ELSE vip_since
                   END,
                   vip_checked_at = :now,
                   updated_at = :now
             WHERE global_id = :global_id
            """
        ),
        {
            "global_id": int(global_id),
            "flag": target,
            "old_flag": old_is_vip,
            "now": boundary,
        },
    )
    return int(getattr(result, "rowcount", 0) or 0) == 1


# --------------------------------------------------------------------
# Догон для одного пользователя (при открытии его экрана)
# --------------------------------------------------------------------


async def checkpoint_user_energy_nocommit(
    db: AsyncSession,
    *,
    global_id: int,
    now_ts: dt.datetime | None = None,
) -> dict[str, Any]:
    """Догнать все живые Панели пользователя без commit/rollback.

    Функция предназначена для финансовых root-транзакций, которым нужен
    актуальный aggregate ``available_kwh`` до mutation. Транзакционной
    границей владеет вызывающий код.
    """
    boundary = now_ts or _now_utc()
    row = (
        await db.execute(
            text(
                "SELECT is_vip FROM efhc_core.users "
                "WHERE global_id = :global_id FOR UPDATE"
            ),
            {"global_id": int(global_id)},
        )
    ).fetchone()
    if row is None:
        raise ValueError("ENERGY_USER_NOT_FOUND")

    rate = _rate_vip() if bool(row[0]) else _rate_base()
    result = await db.execute(
        _BULK_GENERATE_USER_SQL,
        {
            "global_id": int(global_id),
            "now_ts": boundary,
            "rate": str(rate),
        },
    )
    added = result.scalar()
    return {
        "global_id": int(global_id),
        "kwh_added": str(d8(added or 0)),
        "checkpoint_at": boundary.isoformat(),
    }


async def generate_energy_for_user(
    db: AsyncSession,
    *,
    global_id: int,
) -> dict[str, Any]:
    """
    Начисляет энергию по всем активным панелям пользователя.

    Типичный сценарий:
      • вызывается при открытии Dashboard / Panels / Exchange;
      • гарантирует, что available_kwh и total_generated_kwh не отстают
        дольше, чем до ближайшего открытия экрана.

    ИИ-защита:
      • Сначала пробуем пакетно (все панели в одной транзакции).
      • При ошибке — поштучный fallback по панелям пользователя.
    """
    # Быстрый путь по ТЗ v3.1: обновляем ТОЛЬКО активного пользователя
    # одной bulk-операцией, без «миллиона тиков» и десятков round-trip в
    # БД.
    now_ts = _now_utc()

    # VIP-ставка выбирается один раз: VIP общий на панели пользователя.
    # Если пользователя нет, просто вернём 0.
    try:
        q_vip = text(
            "SELECT is_vip FROM efhc_core.users "
            "WHERE global_id = :global_id"
        )
        row_vip = await db.execute(
            q_vip, {"global_id": int(global_id)}
        )
        r = row_vip.fetchone()
        if not r:
            return {
                "global_id": int(global_id),
                "panels_processed": 0,
                "kwh_added": str(d8(0)),
            }
        is_vip = bool(r[0])
    except Exception:
        # Если выборка VIP упала — не валим запрос, просто не начисляем.
        return {
            "global_id": int(global_id),
            "panels_processed": 0,
            "kwh_added": str(d8(0)),
        }

    rate = _rate_vip() if is_vip else _rate_base()

    try:
        await _begin_tx(db)
        # Посчитаем, сколько панелей реально требует обновления (для
        # статистики).
        row_cnt = await db.execute(
            text(
                """
            SELECT COUNT(1)
                  FROM efhc_core.panels p
                 WHERE p.global_id = :global_id
                   AND p.is_active = TRUE
                   AND COALESCE(p.meta ->> 'protectively_voided', 'false') <> 'true'
                   AND p.last_generated_at < LEAST(
                       CAST(:now_ts AS timestamptz),
                       p.expires_at
                   )
                """
            ),
            {"global_id": int(global_id), "now_ts": now_ts},
        )
        panels_to_process = int(row_cnt.scalar() or 0)

        row_add = await db.execute(
            _BULK_GENERATE_USER_SQL,
            {
                "global_id": int(global_id),
                "now_ts": now_ts,
                "rate": str(rate),
            },
        )
        add_total = row_add.scalar()
        await db.commit()

        return {
            "global_id": int(global_id),
            "panels_processed": int(panels_to_process),
            "kwh_added": str(d8(add_total or 0)),
            # Same UTC boundary used by the bulk energy settlement.
            "checkpoint_at": now_ts.isoformat(),
        }
    except Exception as e:
        try:
            await db.rollback()
        except Exception:
            logger.debug(
                "energy.user: rollback failed (bulk)",
                exc_info=True,
            )
        logger.warning(
            "energy.user(%s): bulk failed: %s", global_id, e
        )
        return {
            "global_id": int(global_id),
            "panels_processed": 0,
            "kwh_added": str(d8(0)),
        }


# --------------------------------------------------------------------
# Полная «догонка» всего пула (для запуска после простоев)
# --------------------------------------------------------------------


async def backfill_all(
    db: AsyncSession,
    *,
    max_passes: int = 50,
    batch_size: int = 500,
) -> dict[str, Any]:
    """
    Многократно вызывает generate_energy_tick, пока есть
    необработанные панели
    или не достигнут предел проходов обработки.

    Использование:
      • после длительного простоя,
      • после миграций/обновлений: last_generated_at мог «отстать».

    ИИ-самовосстановление:
      • Каждый проход идемпотентен по last_generated_at/expires_at.
      • Даже при падениях/рестартах суммарная генерация корректна.
    """
    if max_passes < 1:
        max_passes = 1

    total_panels = 0
    total_users_updates = 0
    total_kwh = d8(0)
    passes = 0
    partials = 0

    while passes < max_passes:
        passes += 1
        res = await generate_energy_tick(db, batch_size=batch_size)
        total_panels += int(res.get("panels_processed", 0))
        total_users_updates += int(res.get("users_updated", 0))
        add = Decimal(res.get("total_kwh_added", "0"))
        total_kwh = d8(total_kwh + add)
        partials += int(res.get("partial_fallbacks", 0))

        # Если в этом проходе уже нечего было обрабатывать — выходим
        if int(res.get("panels_processed", 0)) == 0:
            break

        # Короткий не блокирующий «вздох» между проходами
        await asyncio.sleep(0.05)

    return {
        "passes": passes,
        "panels_processed": total_panels,
        "users_updated": total_users_updates,
        "total_kwh_added": str(total_kwh),
        "fallback_passes": partials,
    }


# =====================================================================
# Пояснения «для чайника»:
# • Почему нет «суточных» значений?
# — Канон: единственный источник — ставки в секундах из .env.
# • Почему не считаем «помесячно/по дням»?
# — Потому что это даёт двусмысленность и накопленные ошибки округления.
# last_generated_at + pos/сек — всегда однозначно и идемпотентно.
# • Почему SKIP LOCKED?
# — Чтобы несколько воркеров могли безопасно работать параллельно
# без взаимного блокирования (каждый «забирает» свою порцию панелей).
# • Почему два поля у пользователя?
# — available_kwh для обмена; total_generated_kwh для рейтинга.
# • Что если сервер упал посреди пакета?
# — При новом запуске last_generated_at «скажет», сколько ещё нужно
# догенерировать.
# =====================================================================

__all__ = [
    "generate_energy_tick",
    "generate_energy_for_user",
    "backfill_all",
]
