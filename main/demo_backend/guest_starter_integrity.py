"""Fail-closed verification of reusable Genesis TEST starter slots.

This module deliberately does not reset financial history or user balances.
It only proves that reissuing a slot cannot inherit user mutations. When the
starter state differs from the immutable TEST baseline, quarantine the slot
until the separately audited bank-preserving reset transaction is available.
Production and TON integrations must never import or call this module.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_STARTER_UNCHANGED = text("""
SELECT EXISTS (
 SELECT 1
 FROM efhc_core.users u
 JOIN efhc_test.guest_starter_baselines b ON b.global_id=u.global_id
 WHERE u.global_id=:gid
   AND u.is_active IS TRUE
   AND b.version='genesis-starter-v1'
   AND NOT EXISTS(
       SELECT 1 FROM efhc_test.guest_slot_quarantine q
       WHERE q.global_id=u.global_id
   )
   -- A reused synthetic Global ID must never inherit a former visitor's
   -- TON wallet, even when its balance/panel snapshot still matches baseline.
   AND NOT EXISTS(
       SELECT 1 FROM efhc_core.wallet_bindings wb
       WHERE wb.global_id=u.global_id AND (wb.proof_source IS DISTINCT FROM 'GENESIS_PROJECT_WALLET'
           OR wb.proof_verified IS DISTINCT FROM FALSE
           OR wb.proof_verified_at IS NOT NULL
           OR wb.proof_payload_hash IS NOT NULL
           OR wb.tg_id IS NOT NULL
           OR wb.wallet_address NOT IN (
               SELECT '0:' || encode(sha256(convert_to(
                   'EFHC/Genesis/ProjectWallet/' || wb.global_id::text
                   || '/' || slot::text, 'UTF8')), 'hex')
               FROM generate_series(1,3) slot
           ))
   )
   AND u.main_balance=(b.user_row->>'main_balance')::numeric
   AND u.bonus_balance=(b.user_row->>'bonus_balance')::numeric
   AND u.total_generated_kwh=(b.user_row->>'total_generated_kwh')::numeric
   AND u.exchanged_kwh_total=(b.user_row->>'exchanged_kwh_total')::numeric
   AND u.is_vip=(b.user_row->>'is_vip')::boolean
   AND (SELECT COUNT(*) FROM efhc_core.panels p
        WHERE p.global_id=u.global_id
        AND COALESCE(p.meta->>'demo_reset_void','false')<>'true'
        )=jsonb_array_length(b.panel_rows)
   AND (SELECT COUNT(*) FROM efhc_core.panels p
        WHERE p.global_id=u.global_id AND p.is_active AND NOT p.is_archived)=5
   AND (SELECT COUNT(*) FROM efhc_core.panels p
        WHERE p.global_id=u.global_id AND p.is_archived)=10
   AND COALESCE((SELECT SUM(p.generated_kwh) FROM efhc_core.panels p
         WHERE p.global_id=u.global_id),0)=
       COALESCE((SELECT SUM((j.value->>'generated_kwh')::numeric)
         FROM jsonb_array_elements(b.panel_rows) j),0)
   AND (SELECT COUNT(*) FROM efhc_core.referral_links r
        WHERE r.inviter_global_id=u.global_id)=jsonb_array_length(b.referral_rows)
   AND (SELECT COUNT(*) FROM efhc_core.referral_links r
        WHERE r.inviter_global_id=u.global_id AND r.activated_at IS NOT NULL)=10
   AND (
      (NOT EXISTS (SELECT 1 FROM efhc_test.guest_reset_checkpoints cp
                   WHERE cp.global_id=u.global_id)
       AND (SELECT COUNT(*) FROM efhc_core.efhc_transfers_log t
            WHERE t.global_id=u.global_id)=jsonb_array_length(b.user_ledger_rows))
      OR
      EXISTS (SELECT 1 FROM efhc_test.guest_reset_checkpoints cp
              WHERE cp.global_id=u.global_id
              AND cp.user_ledger_count=(SELECT COUNT(*)
                   FROM efhc_core.efhc_transfers_log t
                   WHERE t.global_id=u.global_id)
              AND cp.last_user_log_id=COALESCE((SELECT MAX(t.id)
                   FROM efhc_core.efhc_transfers_log t
                   WHERE t.global_id=u.global_id),0))
   )
) AS reusable
""")

_QUARANTINE = text("""
INSERT INTO efhc_test.guest_slot_quarantine(global_id,reason,detected_at)
VALUES (:gid,:reason,now())
ON CONFLICT(global_id) DO UPDATE
SET reason=EXCLUDED.reason,detected_at=EXCLUDED.detected_at
""")


async def reusable_starter_is_intact(db: AsyncSession, global_id: int) -> bool:
    """Confirm baseline, panels, energy, referrals, balances and user ledger."""
    gid = int(global_id)
    if gid < 3001 or gid > 4000:
        return False
    return bool((await db.execute(_STARTER_UNCHANGED, {"gid": gid})).scalar_one())


async def quarantine_guest_slot(
    db: AsyncSession, global_id: int, *, reason: str = "STARTER_STATE_MISMATCH"
) -> None:
    """Keep an altered slot out of the pool; caller commits atomically."""
    gid = int(global_id)
    if not (3001 <= gid <= 4000):
        raise ValueError("Only canonical Genesis guest slots may be quarantined")
    if len(reason) > 96 or not reason:
        raise ValueError("Invalid quarantine reason")
    await db.execute(_QUARANTINE, {"gid":gid, "reason":reason})
