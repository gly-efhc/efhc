"""Материализованный current ranking в ``users`` по canonical ``global_id``."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from app.core.logging_core import get_logger
from app.deps import d8
from app.identity.nonfinancial_owner import (
    resolve_nonfinancial_read_owner,
)
from app.lib.time import utcnow
from app.utils.cursor_codec import decode_cursor, encode_cursor
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

ADVISORY_LOCK_KEY = 0x45F1_00AB
META_TIME_KEY = "ranks.last_snapshot_at"
META_TOTAL_KEY = "ranks.total_users"
DAILY_CLAIM_KEY = "ranks.last_daily_claim_date"
DAILY_RUN_HOUR_UTC = 2

_SQL_TOP = text(
    """
    SELECT u.global_id, u.username, u.is_vip,
           COALESCE(u.rank_score_kwh, u.total_generated_kwh, 0),
           u.rank_position
      FROM efhc_core.users u
     WHERE COALESCE(u.is_active, true) = true
       AND u.rank_position IS NOT NULL
     ORDER BY u.rank_position ASC, u.global_id ASC
     LIMIT :limit
    """
)

_SQL_PAGE_AFTER = text(
    """
    SELECT u.global_id, u.username, u.is_vip,
           COALESCE(u.rank_score_kwh, u.total_generated_kwh, 0),
           u.rank_position
      FROM efhc_core.users u
     WHERE COALESCE(u.is_active, true) = true
       AND u.rank_position IS NOT NULL
       AND (u.rank_position, u.global_id) > (:pos, :global_id)
     ORDER BY u.rank_position ASC, u.global_id ASC
     LIMIT :limit
    """
)

_SQL_CONTEXT_FOR_OWNER = text(
    """
    WITH owner_rank AS (
        SELECT rank_position
          FROM efhc_core.users
         WHERE global_id = :global_id
           AND COALESCE(is_active, true) = true
           AND rank_position IS NOT NULL
         LIMIT 1
    )
    SELECT u.global_id, u.username, u.is_vip,
           COALESCE(u.rank_score_kwh, u.total_generated_kwh, 0),
           u.rank_position
      FROM efhc_core.users u
     WHERE COALESCE(u.is_active, true) = true
       AND u.rank_position IS NOT NULL
       AND u.rank_position BETWEEN
           GREATEST((SELECT rank_position FROM owner_rank) - :radius, 1)
           AND (SELECT rank_position FROM owner_rank) + :radius
     ORDER BY u.rank_position ASC, u.global_id ASC
    """
)

_SQL_LIVE_TOP = text(
    """
    SELECT ranked.global_id, ranked.username, ranked.is_vip,
           ranked.total_generated_kwh, ranked.rank_position
      FROM (
        SELECT u.global_id, u.username, u.is_vip,
               COALESCE(u.total_generated_kwh, 0) AS total_generated_kwh,
               DENSE_RANK() OVER (
                   ORDER BY COALESCE(u.total_generated_kwh, 0) DESC
               ) AS rank_position
          FROM efhc_core.users u
         WHERE COALESCE(u.is_active, true) = true
      ) ranked
     ORDER BY ranked.rank_position ASC, ranked.global_id ASC
     LIMIT :limit
    """
)

_SQL_LIVE_OWNER = text(
    """
    SELECT ranked.global_id, ranked.username, ranked.is_vip,
           ranked.total_generated_kwh, ranked.rank_position
      FROM (
        SELECT u.global_id, u.username, u.is_vip,
               COALESCE(u.total_generated_kwh, 0) AS total_generated_kwh,
               DENSE_RANK() OVER (
                   ORDER BY COALESCE(u.total_generated_kwh, 0) DESC
               ) AS rank_position
          FROM efhc_core.users u
         WHERE COALESCE(u.is_active, true) = true
      ) ranked
     WHERE ranked.global_id = :global_id
     LIMIT 1
    """
)

_SQL_WRITE_CURRENT = text(
    """
    WITH ranked AS (
        SELECT u.global_id,
               COALESCE(u.total_generated_kwh, 0) AS score_kwh,
               DENSE_RANK() OVER (
                   ORDER BY COALESCE(u.total_generated_kwh, 0) DESC
               ) AS rank_position
          FROM efhc_core.users u
         WHERE COALESCE(u.is_active, true) = true
    )
    UPDATE efhc_core.users AS target
       SET rank_position = ranked.rank_position,
           rank_score_kwh = ranked.score_kwh,
           rank_calculated_at = :snapshot_at
      FROM ranked
     WHERE target.global_id = ranked.global_id
    """
)

_SQL_CLEAR_INACTIVE = text(
    """
    UPDATE efhc_core.users
       SET rank_position = NULL,
           rank_score_kwh = NULL,
           rank_calculated_at = NULL
     WHERE COALESCE(is_active, true) = false
       AND (
           rank_position IS NOT NULL
           OR rank_score_kwh IS NOT NULL
           OR rank_calculated_at IS NOT NULL
       )
    """
)


@dataclass(frozen=True)
class RankRow:
    global_id: int
    username: str | None
    total_kwh: str
    rank: int
    is_vip: bool


@dataclass(frozen=True)
class RankSnapshotMeta:
    """Compatibility DTO: metadata current ranking calculation, не history snapshot."""

    snapshot_at: datetime
    total_users: int


async def rebuild_rank_snapshot(
    db: AsyncSession,
    *,
    force_refresh: bool = False,
    limit_users: int | None = None,
) -> RankSnapshotMeta:
    """Явно пересчитать current ranking fields в ``users``.

    Имя функции сохранено как internal compatibility seam. Исторические
    snapshot/cache tables больше не являются authority и не используются.
    """

    _ = force_refresh
    _ = limit_users
    if not await _try_advisory_xact_lock(db, ADVISORY_LOCK_KEY):
        meta = await _current_meta(db)
        await db.rollback()
        if meta is not None:
            return meta
        return RankSnapshotMeta(utcnow(), 0)
    return await _rebuild_rank_snapshot_locked(
        db,
        snapshot_at=utcnow(),
        daily_claim_date=None,
    )


async def run_daily_rank_update_if_due(
    db: AsyncSession,
    *,
    now: datetime | None = None,
) -> tuple[RankSnapshotMeta, bool, date]:
    """Выполнить не более одного current-rank rebuild на UTC business-day."""

    current_time = (now or utcnow()).astimezone(UTC)
    due_date = _ranking_due_date(current_time)
    if not await _try_advisory_xact_lock(db, ADVISORY_LOCK_KEY):
        meta = await _current_meta(db)
        await db.rollback()
        return meta or RankSnapshotMeta(current_time, 0), False, due_date

    claim_date = await _current_daily_claim(db)
    meta = await _current_meta(db)
    if claim_date is not None and claim_date >= due_date and meta is not None:
        await db.rollback()
        return meta, False, due_date

    rebuilt = await _rebuild_rank_snapshot_locked(
        db,
        snapshot_at=current_time,
        daily_claim_date=due_date,
    )
    return rebuilt, True, due_date


def _ranking_due_date(now: datetime) -> date:
    canonical = now.astimezone(UTC)
    if canonical.hour < DAILY_RUN_HOUR_UTC:
        return canonical.date() - timedelta(days=1)
    return canonical.date()


async def _rebuild_rank_snapshot_locked(
    db: AsyncSession,
    *,
    snapshot_at: datetime,
    daily_claim_date: date | None,
) -> RankSnapshotMeta:
    await db.execute(_SQL_CLEAR_INACTIVE)
    await db.execute(_SQL_WRITE_CURRENT, {"snapshot_at": snapshot_at})
    total_users = int(
        (
            await db.execute(
                text(
                    "SELECT COUNT(*) FROM efhc_core.users "
                    "WHERE COALESCE(is_active, true) = true"
                )
            )
        ).scalar_one()
        or 0
    )
    await _write_meta(
        db,
        snapshot_at=snapshot_at,
        total_users=total_users,
        daily_claim_date=daily_claim_date,
    )
    await db.commit()
    logger.info(
        "ranks current state complete users=%s dense_rank=true daily_claim=%s",
        total_users,
        daily_claim_date.isoformat() if daily_claim_date else "manual",
    )
    return RankSnapshotMeta(snapshot_at, total_users)


async def get_user_rank_and_top(
    db: AsyncSession,
    *,
    global_id: int,
    top_limit: int = 100,
) -> tuple[RankRow | None, list[RankRow], RankSnapshotMeta]:
    owner = await resolve_nonfinancial_read_owner(db, global_id=int(global_id))
    meta = await _current_meta(db)
    if meta is None:
        return await _live_me_and_top(
            db,
            owner_global_id=int(owner.global_id),
            top_limit=top_limit,
        )

    me_result = await db.execute(
        text(
            "SELECT global_id, username, is_vip, "
            "COALESCE(rank_score_kwh, total_generated_kwh, 0), rank_position "
            "FROM efhc_core.users WHERE global_id = :global_id "
            "AND COALESCE(is_active, true) = true "
            "AND rank_position IS NOT NULL LIMIT 1"
        ),
        {"global_id": int(owner.global_id)},
    )
    me = _rank_from_row(me_result.fetchone())
    top_result = await db.execute(_SQL_TOP, {"limit": max(1, int(top_limit))})
    top = [
        item
        for item in (_rank_from_row(row) for row in top_result.fetchall())
        if item is not None and item.global_id != int(owner.global_id)
    ]
    return me, top, meta


async def get_leaderboard_page(
    db: AsyncSession,
    *,
    after_cursor: str | None,
    page_size: int = 100,
    global_read: bool = True,
) -> tuple[list[RankRow], str | None, RankSnapshotMeta]:
    """Вернуть provider-neutral cursor page current ranking."""

    _ = global_read
    meta = await _current_meta(db)
    if meta is None:
        return [], None, RankSnapshotMeta(utcnow(), 0)

    page_limit = max(1, int(page_size))
    params: dict[str, Any] = {"limit": page_limit + 1}
    sql = _SQL_TOP
    if after_cursor:
        try:
            payload = decode_cursor(after_cursor)
            params["pos"] = int(payload.get("pos") or 0)
            params["global_id"] = int(payload.get("global_id") or 0)
            sql = _SQL_PAGE_AFTER
        except Exception as exc:
            logger.warning("invalid ranks cursor: %s", exc)

    result = await db.execute(sql, params)
    fetched = [
        item
        for item in (_rank_from_row(row) for row in result.fetchall())
        if item is not None
    ]
    has_more = len(fetched) > page_limit
    items = fetched[:page_limit]
    next_cursor = None
    if has_more and items:
        last = items[-1]
        next_cursor = encode_cursor({"pos": last.rank, "global_id": last.global_id})
    return items, next_cursor, meta


async def get_user_rank_context(
    db: AsyncSession,
    *,
    global_id: int,
    radius: int = 2,
    force_refresh: bool = False,
    max_age_minutes: int = 10,
) -> tuple[list[RankRow], RankSnapshotMeta]:
    """Вернуть bounded context вокруг сохранённой backend позиции owner."""

    owner = await resolve_nonfinancial_read_owner(db, global_id=int(global_id))
    _ = force_refresh
    _ = max_age_minutes
    meta = await _current_meta(db)
    if meta is None:
        return [], RankSnapshotMeta(utcnow(), 0)
    result = await db.execute(
        _SQL_CONTEXT_FOR_OWNER,
        {"global_id": int(owner.global_id), "radius": max(0, min(int(radius), 20))},
    )
    items = [
        item
        for item in (_rank_from_row(row) for row in result.fetchall())
        if item is not None
    ]
    return items, meta


async def _current_meta(db: AsyncSession) -> RankSnapshotMeta | None:
    result = await db.execute(
        text(
            "SELECT key, value FROM efhc_core.app_settings "
            "WHERE key IN (:time_key, :total_key)"
        ),
        {"time_key": META_TIME_KEY, "total_key": META_TOTAL_KEY},
    )
    values = {str(row[0]): str(row[1]) for row in result.fetchall()}
    raw_time = values.get(META_TIME_KEY, "").strip()
    if not raw_time:
        return None
    try:
        snapshot_at = datetime.fromisoformat(raw_time)
        if snapshot_at.tzinfo is None:
            snapshot_at = snapshot_at.replace(tzinfo=UTC)
        total_users = int(values.get(META_TOTAL_KEY, "0"))
    except (TypeError, ValueError):
        return None
    return RankSnapshotMeta(snapshot_at, max(0, total_users))


async def _current_daily_claim(db: AsyncSession) -> date | None:
    result = await db.execute(
        text("SELECT value FROM efhc_core.app_settings WHERE key = :key LIMIT 1"),
        {"key": DAILY_CLAIM_KEY},
    )
    raw = result.scalar_one_or_none()
    if raw is None or not str(raw).strip():
        return None
    try:
        return date.fromisoformat(str(raw).strip())
    except ValueError:
        logger.warning("invalid persistent ranks daily claim: %r", raw)
        return None


async def _write_meta(
    db: AsyncSession,
    *,
    snapshot_at: datetime,
    total_users: int,
    daily_claim_date: date | None = None,
) -> None:
    sql = text(
        "INSERT INTO efhc_core.app_settings (key, value) VALUES (:key, :value) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()"
    )
    await db.execute(sql, {"key": META_TIME_KEY, "value": snapshot_at.isoformat()})
    await db.execute(sql, {"key": META_TOTAL_KEY, "value": str(total_users)})
    if daily_claim_date is not None:
        await db.execute(
            sql,
            {"key": DAILY_CLAIM_KEY, "value": daily_claim_date.isoformat()},
        )


async def _live_me_and_top(
    db: AsyncSession,
    *,
    owner_global_id: int,
    top_limit: int,
) -> tuple[RankRow | None, list[RankRow], RankSnapshotMeta]:
    top_result = await db.execute(_SQL_LIVE_TOP, {"limit": max(int(top_limit), 1)})
    top_rows = [
        item
        for item in (_rank_from_row(row) for row in top_result.fetchall())
        if item is not None
    ]
    me_result = await db.execute(_SQL_LIVE_OWNER, {"global_id": int(owner_global_id)})
    me = _rank_from_row(me_result.fetchone())
    top = [row for row in top_rows if row.global_id != owner_global_id]
    count_result = await db.execute(
        text("SELECT COUNT(*) FROM efhc_core.users WHERE COALESCE(is_active, true) = true")
    )
    return me, top, RankSnapshotMeta(utcnow(), int(count_result.scalar_one()))


def _rank_from_row(row: Any) -> RankRow | None:
    if row is None or row[0] is None or row[4] is None:
        return None
    return RankRow(
        global_id=int(row[0]),
        username=row[1],
        is_vip=bool(row[2]),
        total_kwh=str(d8(row[3])),
        rank=int(row[4]),
    )


async def _try_advisory_xact_lock(db: AsyncSession, key: int) -> bool:
    result = await db.execute(
        text("SELECT pg_try_advisory_xact_lock(:key)"),
        {"key": int(key)},
    )
    return bool(result.scalar_one_or_none())


async def ensure_ranks_tables(db: AsyncSession) -> None:
    """Compatibility seam: ranking storage is now ``users`` current fields."""

    await ensure_latest_snapshot(db)


async def ensure_latest_snapshot(
    db: AsyncSession,
    *,
    force_refresh: bool = False,
    max_age_minutes: int = 10,
) -> RankSnapshotMeta:
    """Compatibility seam for internal callers; user reads do not call it."""

    meta = await _current_meta(db)
    now = utcnow()
    if meta is None or force_refresh:
        return await rebuild_rank_snapshot(db, force_refresh=True)
    age_seconds = (now - meta.snapshot_at).total_seconds()
    if age_seconds > max(0, int(max_age_minutes)) * 60:
        return await rebuild_rank_snapshot(db, force_refresh=True)
    return meta


async def get_my_plus_top(
    db: AsyncSession,
    *,
    global_id: int,
    limit: int = 100,
    cursor: str | None = None,
    force_refresh: bool = False,
    max_age_minutes: int = 10,
) -> tuple[RankRow | None, list[RankRow], RankSnapshotMeta, str | None]:
    _ = cursor
    _ = force_refresh
    _ = max_age_minutes
    me, top, meta = await get_user_rank_and_top(
        db,
        global_id=int(global_id),
        top_limit=int(limit),
    )
    next_cursor = None
    if top and int(top[-1].rank) < int(meta.total_users):
        last = top[-1]
        next_cursor = encode_cursor({"pos": last.rank, "global_id": last.global_id})
    return me, top, meta, next_cursor


async def list_top_page(
    db: AsyncSession,
    *,
    limit: int = 100,
    cursor: str | None = None,
    force_refresh: bool = False,
    max_age_minutes: int = 10,
    global_read: bool = True,
) -> tuple[list[RankRow], RankSnapshotMeta, str | None]:
    _ = global_read
    _ = force_refresh
    _ = max_age_minutes
    items, next_cursor, meta = await get_leaderboard_page(
        db,
        after_cursor=cursor,
        page_size=int(limit),
        global_read=True,
    )
    return items, meta, next_cursor


__all__ = [
    "RankRow",
    "RankSnapshotMeta",
    "ensure_latest_snapshot",
    "ensure_ranks_tables",
    "get_leaderboard_page",
    "get_my_plus_top",
    "get_user_rank_and_top",
    "get_user_rank_context",
    "list_top_page",
    "rebuild_rank_snapshot",
    "run_daily_rank_update_if_due",
]
