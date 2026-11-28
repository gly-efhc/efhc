"""Mandatory TEST auth boundaries; public identifiers never prove account ownership.

Only explicitly synthetic, unclaimed, non-admin Neon TEST accounts can be
entered by a DEMO guest or by the separate operator's test credential.
A native Telegram/TON session is always resolved by the canonical verifier,
not by an operator-supplied Global ID.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_SAFE_SYNTHETIC_ACCOUNT = text("""
SELECT EXISTS (
  SELECT 1
  FROM efhc_core.users u
  WHERE u.global_id = :gid
    AND u.is_active = TRUE
    AND u.global_id <> 88
    AND (
      (COALESCE(u.meta ->> 'demo','false') = 'true'
       AND COALESCE(u.meta ->> 'simulation_only','false') = 'true')
      OR
      (COALESCE(u.meta ->> 'genesis','false') = 'true'
       AND COALESCE(u.meta ->> 'test_only','false') = 'true')
    )
    AND NOT EXISTS (
      SELECT 1 FROM efhc_admin.admin_whitelist a WHERE a.global_id = u.global_id
    )
    AND NOT EXISTS (
      SELECT 1 FROM efhc_core.user_identities i WHERE i.global_id = u.global_id
    )
) AS allowed
""")


async def is_safe_synthetic_account(db: AsyncSession, global_id: str | int) -> bool:
    """Fail closed if a TEST account has any privileged or claimed identity."""
    try:
        gid = int(global_id)
    except (TypeError, ValueError):
        return False
    if gid <= 0 or gid > 9_999_999_999:
        return False
    return bool((await db.execute(_SAFE_SYNTHETIC_ACCOUNT, {"gid": gid})).scalar_one())


__all__ = ["is_safe_synthetic_account"]
