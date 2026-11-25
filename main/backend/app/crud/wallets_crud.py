# backend/app/crud/wallets_crud.py
# ======================================================================
# CRUD для привязанных TON-кошельков (идентификатор для верификации).
# Привязка не является хранением средств.
# ======================================================================

from __future__ import annotations

from app.identity.types import global_id_to_database, parse_global_id
from app.models.wallets_models import WalletBinding
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def get_wallet_binding(
    db: AsyncSession,
    *,
    global_id: str,
) -> WalletBinding | None:
    """Вернуть привязку кошелька по global_id или None."""

    stmt = select(WalletBinding).where(
        WalletBinding.global_id == global_id_to_database(parse_global_id(global_id))
    )
    res = await db.execute(stmt)
    return res.scalar_one_or_none()
