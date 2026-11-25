# backend/app/crud/user_crud.py
# ======================================================================
# CRUD-слой для таблицы users: создание/чтение/обновление и выборки.
# Денежных операций здесь нет: любые движения EFHC только через сервисы.
# Все списки используют курсор по (global_id ASC), без OFFSET.
# ======================================================================

from __future__ import annotations

from app.core.logging_core import get_logger
from app.deps import decode_cursor, encode_cursor
from app.identity.auth_provider import AuthProvider
from app.identity.user_identities_storage_contract import (
    USER_IDENTITY_DEFAULT_TENANT,
)
from app.models.identity_models import UserIdentity
from app.models.user_models import User
from app.models.wallets_models import WalletBinding
from sqlalchemy import Select, and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)


# ======================================================================
# ВНУТРЕННИЕ ПОМОЩНИКИ
# ======================================================================


def _apply_user_filters(
    stmt: Select,
    *,
    is_active: bool | None = None,
    is_vip: bool | None = None,
    qtext: str | None = None,
) -> Select:
    """Применить is_active/is_vip/qtext к выборке пользователей."""

    conds = []

    if is_active is not None:
        conds.append(User.is_active.is_(bool(is_active)))

    if is_vip is not None:
        conds.append(User.is_vip.is_(bool(is_vip)))

    if qtext:
        q = qtext.strip()
        if q.isdigit():
            like_expr = func.lower(User.username).like(
                func.lower(f"%{q}%")
            )
            conds.append(or_(like_expr, User.global_id == int(q)))
        else:
            conds.append(
                func.lower(User.username).like(func.lower(f"%{q}%"))
            )

    if conds:
        stmt = stmt.where(and_(*conds))

    return stmt


# ======================================================================
# СОЗДАНИЕ / ЧТЕНИЕ
# ======================================================================


async def get_user_by_telegram_subject(
    db: AsyncSession,
    *,
    tg_id: int,
) -> User | None:
    """Разрешить проверенный Telegram subject в canonical аккаунт."""

    res = await db.execute(
        select(User)
        .join(UserIdentity, UserIdentity.global_id == User.global_id)
        .where(
            UserIdentity.provider == AuthProvider.TELEGRAM.value,
            UserIdentity.provider_tenant == USER_IDENTITY_DEFAULT_TENANT,
            UserIdentity.provider_subject == str(int(tg_id)),
            UserIdentity.status == "active",
            UserIdentity.is_verified.is_(True),
            UserIdentity.verified_at.is_not(None),
        )
        .limit(2)
    )
    rows = list(res.scalars().all())
    return rows[0] if len(rows) == 1 else None


# ======================================================================
# ОБНОВЛЕНИЕ (без денег)
# ======================================================================


# ======================================================================
# СПИСОК — курсорная пагинация (global_id ASC)
# ======================================================================


async def list_users_cursor(
    db: AsyncSession,
    *,
    is_active: bool | None = None,
    is_vip: bool | None = None,
    qtext: str | None = None,
    limit: int = 50,
    next_cursor: str | None = None,
) -> tuple[list[User], str | None]:
    """Вернуть пользователей курсором по (global_id ASC)."""

    limit = max(1, min(int(limit), 200))

    after_global_id: int | None = None
    if next_cursor:
        payload = decode_cursor(next_cursor)
        after_raw = payload.get("after_global_id", payload.get("after_id"))
        if after_raw is not None:
            after_global_id = int(after_raw or 0)

    stmt: Select = select(User)
    stmt = _apply_user_filters(
        stmt,
        is_active=is_active,
        is_vip=is_vip,
        qtext=qtext,
    )

    if after_global_id is not None:
        stmt = stmt.where(User.global_id > after_global_id)

    stmt = stmt.order_by(User.global_id.asc()).limit(limit)

    rows = (await db.execute(stmt)).scalars().all()

    nxt = None
    if rows and len(rows) == limit:
        nxt = encode_cursor({"after_id": int(rows[-1].global_id)})

    return list(rows), nxt


# ======================================================================
# ВЫБОРКИ ДЛЯ ПЛАНИРОВЩИКА / ИНТЕГРАЦИЙ
# ======================================================================


async def list_users_with_wallet_cursor(
    db: AsyncSession,
    *,
    limit: int = 500,
    next_cursor: str | None = None,
) -> tuple[list[User], str | None]:
    """Пользователи с active verified wallet binding, курсор global_id ASC."""

    limit = max(1, min(int(limit), 1000))

    after_global_id: int | None = None
    if next_cursor:
        payload = decode_cursor(next_cursor)
        after_raw = payload.get("after_global_id", payload.get("after_id"))
        if after_raw is not None:
            after_global_id = int(after_raw or 0)

    stmt: Select = select(User).where(
        exists(
            select(WalletBinding.id).where(
                WalletBinding.global_id == User.global_id,
                WalletBinding.is_active.is_(True),
                WalletBinding.proof_verified.is_(True),
            )
        )
    )

    if after_global_id is not None:
        stmt = stmt.where(User.global_id > after_global_id)

    stmt = stmt.order_by(User.global_id.asc()).limit(limit)

    rows = (await db.execute(stmt)).scalars().all()

    nxt = None
    if rows and len(rows) == limit:
        nxt = encode_cursor({"after_id": int(rows[-1].global_id)})

    return list(rows), nxt


async def count_users(db: AsyncSession) -> int:
    """Счётчик пользователей (метрики/админка)."""

    res = await db.execute(select(func.count(User.global_id)))
    val = res.scalar_one() or 0
    return int(val)


async def count_users_vip(db: AsyncSession) -> int:
    """Счётчик пользователей с is_vip=true."""

    val = (
        await db.execute(
            select(func.count(User.global_id)).where(User.is_vip.is_(True))
        )
    ).scalar_one() or 0
    return int(val)
