"""Совместимые entrypoints обслуживания VIP/Admin NFT.

Модуль сохраняет исторические maintenance-импорты, которые безопасно
делегируют действующему ``nft_check_service``. Legacy manual claim через
``tg_id`` сюда намеренно не возвращается: business owner после cutover —
только ``global_id``. Historical ``submit_manual_vip_nft_claim`` имеет статус
``REPLACED_BY_CANON / DO_NOT_RESTORE``: оплаченный Shop NFT order уже является
единственной заявкой на ручную выдачу.
"""

from __future__ import annotations

from typing import Any, cast

from app.services import nft_check_service


async def refresh_vip_status_due_batch(
    db,
    *,
    limit: int = 1000,
    force: bool = False,
) -> dict[str, Any]:
    """Обновить VIP/Admin NFT через действующий единый NFT-контур."""
    _ = limit, force
    result = await nft_check_service.check__all__users_once(db)
    return cast(dict[str, Any], result)


async def refresh_vip_status_for_due_users(
    db,
    *,
    limit: int = 1000,
    force: bool = False,
) -> dict[str, Any]:
    """Совместимое имя пакетного обновления VIP/Admin NFT."""
    return await refresh_vip_status_due_batch(
        db,
        limit=limit,
        force=force,
    )


async def check_vip_nft_due_batch(
    db,
    *,
    limit: int = 1000,
    force: bool = False,
) -> dict[str, Any]:
    """Совместимое имя проверки VIP/Admin NFT."""
    return await refresh_vip_status_due_batch(
        db,
        limit=limit,
        force=force,
    )


__all__ = [
    "refresh_vip_status_due_batch",
    "refresh_vip_status_for_due_users",
    "check_vip_nft_due_batch",
]
