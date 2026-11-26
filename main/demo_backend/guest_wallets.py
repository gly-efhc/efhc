from __future__ import annotations

import hashlib

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

PROJECT_WALLET_SOURCE = "GENESIS_PROJECT_WALLET"


def project_wallet_addresses(global_id: int) -> tuple[str, str, str]:
    gid = int(global_id)
    if not 3001 <= gid <= 4000:
        raise ValueError("GENESIS_GUEST_GID_REQUIRED")
    return tuple(
        "0:" + hashlib.sha256(
            f"EFHC/Genesis/ProjectWallet/{gid}/{slot}".encode("ascii")
        ).hexdigest()
        for slot in (1, 2, 3)
    )


async def restore_project_wallets(db: AsyncSession, global_id: int) -> None:
    gid = int(global_id)
    addresses = project_wallet_addresses(gid)
    target = (await db.execute(text("""
        SELECT current_setting('neon.project_id',TRUE)='fragrant-mountain-35143707'
          AND current_setting('neon.branch_id',TRUE)='br-winter-rice-zalqeb10'
          AND current_database()='neondb'
          AND EXISTS(SELECT 1 FROM efhc_core.app_settings
              WHERE key='genesis.seed.status' AND value='COMPLETE')
          AND EXISTS(SELECT 1 FROM efhc_core.users u WHERE global_id=:gid
              AND u.is_active AND u.meta->>'genesis'='true'
              AND u.meta->>'test_only'='true')
          AND NOT EXISTS(SELECT 1 FROM efhc_core.user_identities
              WHERE global_id=:gid)
          AND NOT EXISTS(SELECT 1 FROM efhc_admin.admin_whitelist
              WHERE global_id=:gid)
    """), {"gid": gid})).scalar_one()
    if not target:
        raise ValueError("GENESIS_PROJECT_WALLET_TARGET_REQUIRED")
    rows = (await db.execute(text("""
        SELECT wallet_address, proof_source, proof_verified, proof_verified_at,
               proof_payload_hash, tg_id
        FROM efhc_core.wallet_bindings WHERE global_id=:gid FOR UPDATE
    """), {"gid": gid})).mappings().all()
    if any(
        r["proof_source"] != PROJECT_WALLET_SOURCE
        or r["proof_verified"] is not False
        or r["proof_verified_at"] is not None
        or r["proof_payload_hash"] is not None
        or r["tg_id"] is not None
        or r["wallet_address"] not in addresses
        for r in rows
    ):
        raise ValueError("GENESIS_EXTERNAL_WALLET_PRESENT")
    for slot, address in enumerate(addresses, 1):
        result = await db.execute(text("""
            INSERT INTO efhc_core.wallet_bindings
                (global_id,wallet_address,is_active,is_primary,proof_verified,
                 proof_source,updated_at)
            VALUES (:gid,:address,TRUE,:primary,FALSE,:source,now())
            ON CONFLICT(wallet_address) DO UPDATE SET
                is_active=TRUE,is_primary=EXCLUDED.is_primary,updated_at=now()
            WHERE efhc_core.wallet_bindings.global_id=EXCLUDED.global_id
              AND efhc_core.wallet_bindings.proof_source=EXCLUDED.proof_source
              AND efhc_core.wallet_bindings.proof_verified IS FALSE
              AND efhc_core.wallet_bindings.proof_verified_at IS NULL
              AND efhc_core.wallet_bindings.proof_payload_hash IS NULL
              AND efhc_core.wallet_bindings.tg_id IS NULL
            RETURNING id
        """), {"gid":gid,"address":address,"primary":slot==1,
                "source":PROJECT_WALLET_SOURCE})
        if result.scalar_one_or_none() is None:
            raise ValueError("GENESIS_PROJECT_WALLET_CONFLICT")
