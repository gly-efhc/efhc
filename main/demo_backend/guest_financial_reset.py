"""Account-scoped, ledger-preserving Genesis TEST reset.

APPEND compensating user/BANK entries; NEVER delete monetary history,
reissue PNL numbers, reset the shared bank, or touch other owners.
All actions execute within one caller-owned PostgreSQL transaction.
Fail closed on an unknown monetary or external payment transaction.
"""
from __future__ import annotations

import json
from decimal import Decimal
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from demo_backend.guest_starter_integrity import (
    quarantine_guest_slot, reusable_starter_is_intact,
)

ZERO = Decimal("0.00000000")
Q = Decimal("0.00000001")
SUPPORTED = frozenset({
    "panel_activation", "exchange_all", "exchange_partial",
    "demo_simulated_external_deposit",
})


class GuestResetUnsafe(RuntimeError):
    """A slot cannot be restored without risking financial history."""


def _d(value: object) -> Decimal:
    return Decimal(str(value)).quantize(Q)


def _utc_timestamp(value: object) -> datetime | None:
    """Convert JSONB baseline timestamps before asyncpg binds timestamptz.

    PostgreSQL's asyncpg driver requires datetime instances, not ISO strings,
    even when the SQL expression wraps the bind in CAST(... AS timestamptz).
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise GuestResetUnsafe("INVALID_STARTER_TIMESTAMP")
    if parsed.tzinfo is None:
        raise GuestResetUnsafe("NAIVE_STARTER_TIMESTAMP")
    return parsed.astimezone(timezone.utc)


async def _require_target(db: AsyncSession) -> None:
    result = (await db.execute(text("""
        SELECT current_setting('neon.project_id',TRUE) AS p,
               current_setting('neon.branch_id',TRUE) AS b,
               current_database() AS d,
               (SELECT value FROM efhc_core.app_settings
                WHERE key='genesis.seed.status') AS seed
    """))).mappings().one()
    if (result["p"], result["b"], result["d"], result["seed"]) != (
        "fragrant-mountain-35143707","br-winter-rice-zalqeb10",
        "neondb","COMPLETE",
    ):
        raise GuestResetUnsafe("GENESIS_TEST_TARGET_REQUIRED")


async def _locked_baseline(db: AsyncSession, gid: int) -> dict:
    # Lock the account before the bank, matching canonical payment lock order.
    owner = (await db.execute(text("""
        SELECT u.* FROM efhc_core.users u WHERE global_id=:gid
        AND is_active IS TRUE AND u.meta->>'genesis'='true'
        AND u.meta->>'test_only'='true'
        AND NOT EXISTS(SELECT 1 FROM efhc_core.user_identities x
                       WHERE x.global_id=u.global_id)
        AND NOT EXISTS(SELECT 1 FROM efhc_admin.admin_whitelist a
                       WHERE a.global_id=u.global_id)
        FOR UPDATE OF u
    """), {"gid":gid})).mappings().one_or_none()
    if owner is None:
        raise GuestResetUnsafe("TEST_OWNER_NOT_SAFE")
    baseline = (await db.execute(text("""
        SELECT user_row,panel_rows,referral_rows,user_ledger_rows
        FROM efhc_test.guest_starter_baselines
        WHERE global_id=:gid AND version='genesis-starter-v1'
    """), {"gid":gid})).mappings().one_or_none()
    if not baseline:
        raise GuestResetUnsafe("GENESIS_STARTER_NOT_AVAILABLE")
    return {"owner":owner,"user":baseline["user_row"],
            "panels":baseline["panel_rows"],"refs":baseline["referral_rows"],
            "initial_ledger":baseline["user_ledger_rows"]}


async def reset_guest_economy(db: AsyncSession, gid: int) -> bool:
    """Reset TEST economy atomically; caller must own and commit the transaction.

    Caller MUST verify and lock the originating lease before calling this
    function. No public API may accept a bare Global ID for resetting.
    """
    if not (3001 <= int(gid) <= 4000):
        raise GuestResetUnsafe("TEST_GUEST_GID_REQUIRED")
    await _require_target(db)
    snap = await _locked_baseline(db, int(gid))
    old = snap["user"]
    current = snap["owner"]
    baseline_ids = {int(p["id"]) for p in snap["panels"]}
    if len(baseline_ids) != 15 or len(snap["refs"]) != 12:
        raise GuestResetUnsafe("STARTER_SHAPE_INVALID")

    # If another owner modified linked referrals, never revert their activity.
    refs = (await db.execute(text("""
        SELECT id,activated_at FROM efhc_core.referral_links
        WHERE inviter_global_id=:gid ORDER BY id
    """), {"gid":gid})).mappings().all()
    old_refs = {int(x["id"]):x for x in snap["refs"]}
    def _normalize_ts(value: object) -> str | None:
        if value is None:
            return None
        from datetime import datetime, timezone
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc).isoformat()
        return datetime.fromisoformat(str(value).replace("Z","+00:00")).astimezone(
            timezone.utc
        ).isoformat()

    if (len(refs)!=12 or
        any(int(r["id"]) not in old_refs or
            _normalize_ts(r["activated_at"]) !=
            _normalize_ts(old_refs[int(r["id"])]["activated_at"])
            for r in refs)):
        raise GuestResetUnsafe("EXTERNAL_REFERRAL_CHANGE_UNSUPPORTED")

    all_panels = (await db.execute(text("""
        SELECT id,public_id FROM efhc_core.panels WHERE global_id=:gid
        FOR UPDATE
    """), {"gid":gid})).mappings().all()
    if not baseline_ids.issubset({int(p["id"]) for p in all_panels}):
        raise GuestResetUnsafe("ORIGINAL_PANEL_MISSING")

    checkpoint = (await db.execute(text("""
        SELECT last_user_log_id,reset_count FROM
        efhc_test.guest_reset_checkpoints WHERE global_id=:gid FOR UPDATE
    """), {"gid":gid})).mappings().one_or_none()
    base_high = max(int(x["id"]) for x in snap["initial_ledger"])
    watermark = int(checkpoint["last_user_log_id"]) if checkpoint else base_high
    if watermark < base_high:
        raise GuestResetUnsafe("RESET_LEDGER_WATERMARK_INVALID")
    new_events = (await db.execute(text("""
        SELECT id,amount,direction,balance_type,reason,idempotency_key
        FROM efhc_core.efhc_transfers_log
        WHERE global_id=:gid AND id>:watermark
        ORDER BY id FOR UPDATE
    """), {"gid":gid,"watermark":watermark})).mappings().all()
    if any(row["reason"] not in SUPPORTED for row in new_events):
        raise GuestResetUnsafe("UNSUPPORTED_GUEST_MONEY_EVENT")

    deltas = {"main":ZERO,"bonus":ZERO}
    for row in new_events:
        typ = str(row["balance_type"])
        direction = str(row["direction"])
        amount = _d(row["amount"])
        if typ not in deltas or direction not in {"credit","debit"} or amount < 0:
            raise GuestResetUnsafe("LEDGER_EVENT_INVALID")
        key = str(row["idempotency_key"])
        mirror = (await db.execute(text("""
            SELECT amount,direction,balance_type,system_entity
            FROM efhc_core.efhc_transfers_log
            WHERE idempotency_key=:key
        """), {"key":"mirror:"+key})).mappings().one_or_none()
        opposite = "debit" if direction=="credit" else "credit"
        if not mirror or (_d(mirror["amount"])!=amount or
                mirror["direction"]!=opposite or
                mirror["system_entity"]!="BANK_EFHC" or
                mirror["balance_type"]!="main"):
            raise GuestResetUnsafe("BANK_MIRROR_NOT_BALANCED")
        deltas[typ] += amount if direction=="credit" else -amount

    expected_main=_d(old["main_balance"])+deltas["main"]
    expected_bonus=_d(old["bonus_balance"])+deltas["bonus"]
    if (expected_main!=_d(current["main_balance"]) or
        expected_bonus!=_d(current["bonus_balance"])):
        raise GuestResetUnsafe("UNLEDGERED_BALANCE_CHANGE")

    # A bank lock serializes this reset against all other monetary writes.
    bank = (await db.execute(text("""
        SELECT balance FROM efhc_core.bank_balance
        WHERE key='EFHC_MAIN' FOR UPDATE
    """))).scalar_one()
    bank_balance = _d(bank)
    # Canon permits the BANK to carry debt; only money-mass conservation,
    # mirrored directions and replay-proof ledger history are mandatory.

    for row in new_events:
        orig_direction=str(row["direction"])
        reversal="debit" if orig_direction=="credit" else "credit"
        bank_direction="credit" if reversal=="debit" else "debit"
        key=f"demo-reset:G{gid:010d}:T{int(row['id'])}"
        meta=json.dumps({
            "test_only":True,"original_transfer_id":int(row["id"]),
            "kind":"guest_financial_compensation",
        },separators=(",",":"))
        await db.execute(text("""
            INSERT INTO efhc_core.efhc_transfers_log
            (global_id,system_entity,amount,direction,balance_type,
             reason,idempotency_key,meta)
            VALUES (:gid,NULL,:amount,:dir,:typ,'demo_reset',:key,:meta)
        """),{"gid":gid,"amount":row["amount"],"dir":reversal,
               "typ":row["balance_type"],"key":key,"meta":meta})
        await db.execute(text("""
            INSERT INTO efhc_core.efhc_transfers_log
            (global_id,system_entity,amount,direction,balance_type,
             reason,idempotency_key,meta)
            VALUES (NULL,'BANK_EFHC',:amount,:dir,'main',
                    'mirror:demo_reset',:key,:meta)
        """),{"amount":row["amount"],"dir":bank_direction,
               "key":"mirror:"+key,"meta":meta})

    # Monetary history is immutable; bank changes are mirrored by the new
    # compensating entries above and committed together with restored balances.
    delta_bank = deltas["main"] + deltas["bonus"]
    if delta_bank:
        await db.execute(text("""
            UPDATE efhc_core.bank_balance SET
            balance=:value,updated_at=now() WHERE key='EFHC_MAIN'
        """),{"value":bank_balance+delta_bank})

    panels_json=json.dumps(snap["panels"],default=str)
    await db.execute(text("""
        UPDATE efhc_core.panels p
        SET is_active=(x.j->>'is_active')::boolean,
            is_archived=(x.j->>'is_archived')::boolean,
            generated_kwh=(x.j->>'generated_kwh')::numeric,
            activated_at=(x.j->>'activated_at')::timestamptz,
            expires_at=(x.j->>'expires_at')::timestamptz,
            archived_at=(x.j->>'archived_at')::timestamptz,
            last_generated_at=(x.j->>'last_generated_at')::timestamptz,
            base_gen_per_sec=(x.j->>'base_gen_per_sec')::numeric,
            meta=x.j->'meta',updated_at=now()
        FROM (SELECT value j FROM jsonb_array_elements(
              CAST(:panels AS jsonb))) x
        WHERE p.id=(x.j->>'id')::bigint AND p.global_id=:gid
    """), {"panels":panels_json,"gid":gid})

    # Preserve the globally issued PNL IDs as voided physical tombstones,
    # so canonical sequence validation never reuses an issued PNL number.
    await db.execute(text("""
        UPDATE efhc_core.panels p SET
          is_active=FALSE,is_archived=FALSE,generated_kwh=0,
          last_generated_at=NULL,
          meta=COALESCE(p.meta,'{}'::jsonb)||
              jsonb_build_object('demo_reset_void',TRUE),
          updated_at=now()
        WHERE p.global_id=:gid
          AND NOT EXISTS (
            SELECT 1 FROM jsonb_array_elements(CAST(:panels AS jsonb)) x
            WHERE (x->>'id')::bigint=p.id)
    """),{"gid":gid,"panels":panels_json})

    await db.execute(text("""
        UPDATE efhc_core.users SET
          main_balance=:main,bonus_balance=:bonus,
          total_generated_kwh=:total,
          exchanged_kwh_total=:exchanged,
          is_vip=:vip,vip_since=CAST(:vip_since AS timestamptz),
          vip_checked_at=CAST(:vip_checked_at AS timestamptz),
          rank_position=:rank_position,rank_score_kwh=:rank_score,
          rank_calculated_at=CAST(:rank_at AS timestamptz),
          last_sync_at=CAST(:last_sync AS timestamptz),updated_at=now()
        WHERE global_id=:gid
    """),{
        "gid":gid,"main":_d(old["main_balance"]),
        "bonus":_d(old["bonus_balance"]),
        "total":_d(old["total_generated_kwh"]),
        "exchanged":_d(old["exchanged_kwh_total"]),
        "vip":old["is_vip"],"vip_since":_utc_timestamp(old["vip_since"]),
        "vip_checked_at":_utc_timestamp(old["vip_checked_at"]),
        "rank_position":old["rank_position"],
        "rank_score":old["rank_score_kwh"],
        "rank_at":_utc_timestamp(old["rank_calculated_at"]),
        "last_sync":_utc_timestamp(old["last_sync_at"]),
    })

    # Check exact zero-delta mass in the same transaction. No mint or burn.
    mass = (await db.execute(text("""
      SELECT (SELECT balance FROM efhc_core.bank_balance
              WHERE key='EFHC_MAIN') +
             (SELECT SUM(main_balance+bonus_balance)
              FROM efhc_core.users) AS mass
    """))).scalar_one()
    if _d(mass)!=_d("5000000.00000000"):
        raise GuestResetUnsafe("BANK_MASS_INTEGRITY_VIOLATION")

    ledger = (await db.execute(text("""
       SELECT COUNT(*) cnt,COALESCE(MAX(id),0) high
       FROM efhc_core.efhc_transfers_log
       WHERE global_id=:gid
    """),{"gid":gid})).mappings().one()
    await db.execute(text("""
        INSERT INTO efhc_test.guest_reset_checkpoints
        (global_id,reset_count,last_user_log_id,user_ledger_count,last_reset_at)
        VALUES (:gid,1,:high,:cnt,now())
        ON CONFLICT(global_id) DO UPDATE SET
        reset_count=efhc_test.guest_reset_checkpoints.reset_count+1,
        last_user_log_id=EXCLUDED.last_user_log_id,
        user_ledger_count=EXCLUDED.user_ledger_count,
        last_reset_at=now()
    """),{"gid":gid,"high":int(ledger["high"]),"cnt":int(ledger["cnt"])})
    await db.execute(text("""
        DELETE FROM efhc_test.guest_slot_quarantine WHERE global_id=:gid
    """),{"gid":gid})
    # Caller must commit together with the lease deletion and revocation.
    return bool(new_events)
