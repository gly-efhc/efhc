"""Server-authoritative, per-browser Genesis TEST guest slot allocation.

Only the pre-seeded 3001..4000 synthetic profiles are eligible. A random
opaque resume secret is returned once to the browser; Neon stores its SHA-256
digest, never the secret itself. PostgreSQL serializes allocation so different
browsers cannot simultaneously acquire the same unexpired slot.
"""
from __future__ import annotations

import hashlib
import os
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from demo_backend.account_guards import is_safe_synthetic_account
from demo_backend.config import parse_test_admin_ids
from demo_backend.guest_financial_reset import GuestResetUnsafe, reset_guest_economy
from demo_backend.guest_starter_integrity import (
    quarantine_guest_slot, reusable_starter_is_intact,
)

_PROJECT = "fragrant-mountain-35143707"
_BRANCH = "br-winter-rice-zalqeb10"
_POOL_FIRST = 3001
_POOL_LAST = 4000
_LEASE_TTL = timedelta(hours=48)
_LOCK_ID = 4520045
_RESUME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{32,256}$")

_TARGET = text("""
SELECT current_setting('neon.project_id', TRUE) AS project,
       current_setting('neon.branch_id', TRUE) AS branch,
       current_database() AS database,
       (SELECT value FROM efhc_core.app_settings
        WHERE key = 'genesis.seed.status') AS seed
""")
_RESUME = text("""
UPDATE efhc_test.guest_leases
SET last_visit_at = now(), expires_at = now() + INTERVAL '48 hours'
WHERE token_hash = :digest
  AND (expires_at > now() OR global_id = ANY(CAST(:reserved_ids AS bigint[])))
RETURNING global_id, expires_at
""")
_CHOOSE = text("""
SELECT u.global_id
FROM efhc_core.users AS u
JOIN efhc_test.guest_starter_baselines AS b ON b.global_id = u.global_id
LEFT JOIN efhc_test.guest_leases AS l ON l.global_id = u.global_id
LEFT JOIN efhc_test.guest_slot_quarantine AS q ON q.global_id = u.global_id
WHERE u.global_id BETWEEN 3001 AND 4000 AND u.is_active = TRUE
  AND NOT (u.global_id = ANY(CAST(:reserved_ids AS bigint[])))
  AND u.meta ->> 'genesis' = 'true'
  AND u.meta ->> 'test_only' = 'true'
  AND (l.global_id IS NULL OR l.expires_at <= now())
  AND b.version = 'genesis-starter-v1'
  AND q.global_id IS NULL
  AND NOT EXISTS (SELECT 1 FROM efhc_core.user_identities i
                  WHERE i.global_id = u.global_id)
  AND NOT EXISTS (SELECT 1 FROM efhc_admin.admin_whitelist a
                  WHERE a.global_id = u.global_id)
ORDER BY random()
LIMIT 1
""")
_ASSIGN = text("""
INSERT INTO efhc_test.guest_leases
    (global_id, token_hash, issued_at, last_visit_at, expires_at)
VALUES (:gid, :digest, now(), now(), now() + INTERVAL '48 hours')
ON CONFLICT (global_id) DO UPDATE
SET token_hash = EXCLUDED.token_hash,
    issued_at = EXCLUDED.issued_at,
    last_visit_at = EXCLUDED.last_visit_at,
    expires_at = EXCLUDED.expires_at
WHERE efhc_test.guest_leases.expires_at <= now()
RETURNING global_id, expires_at
""")
# Once a TEST Global ID has hosted an on-chain wallet binding, recycling it
# would expose the previous visitor's ownership metadata to the next lease.
# Keep the immutable proof/audit history and quarantine the slot instead.
_HAS_WALLET_BINDING = text("""
SELECT EXISTS(
 SELECT 1 FROM efhc_core.wallet_bindings WHERE global_id=:gid
)
""")
_REVOKE_BOUND_TEST_WALLETS = text("""
UPDATE efhc_core.wallet_bindings
   SET is_active=FALSE, is_primary=FALSE, updated_at=NOW()
 WHERE global_id=:gid AND (is_active=TRUE OR is_primary=TRUE)
""")
_EXPIRED = text("""
SELECT l.global_id FROM efhc_test.guest_leases l
JOIN efhc_test.guest_starter_baselines b ON b.global_id=l.global_id
WHERE l.expires_at<=now()
  AND NOT (l.global_id = ANY(CAST(:reserved_ids AS bigint[])))
ORDER BY l.expires_at
LIMIT 10 FOR UPDATE OF l SKIP LOCKED
""")
_EXPIRED_DELETE = text("""
DELETE FROM efhc_test.guest_leases WHERE global_id=:gid
AND expires_at<=now()
""")
_OWNED = text("""
SELECT global_id FROM efhc_test.guest_leases
WHERE global_id=:gid AND token_hash=:digest
""")
_RELEASE = text("""
DELETE FROM efhc_test.guest_leases
WHERE global_id = :gid AND token_hash = :digest
RETURNING global_id
""")


@dataclass(frozen=True)
class GuestLease:
    global_id: str
    resume_token: str
    expires_at: datetime


class GuestPoolFull(RuntimeError):
    pass


class GuestPoolConfigurationError(RuntimeError):
    pass


def valid_resume_secret(token: str | None) -> bool:
    return isinstance(token, str) and bool(_RESUME_PATTERN.fullmatch(token))


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def _reserved_test_admin_ids() -> list[int]:
    """A reserved Admin TEST slot cannot be randomly reissued or reset."""
    return sorted(int(value) for value in parse_test_admin_ids(
        os.environ.get("EFHC_TEST_ADMIN_GLOBAL_IDS", "")
    ))


async def _assert_target(db: AsyncSession) -> None:
    row = (await db.execute(_TARGET)).mappings().one()
    if (row["project"], row["branch"], row["database"], row["seed"]) != (
        _PROJECT, _BRANCH, "neondb", "COMPLETE"
    ):
        raise GuestPoolConfigurationError("GENESIS_GUEST_TARGET_MISMATCH")


async def _quarantine_bound_guest_wallet(
    db: AsyncSession, global_id: int
) -> bool:
    """Never release a previously proven wallet to a different TEST lease.

    Must run inside the existing Genesis TEST advisory-locked transaction.
    Deactivation is revocation, NOT deletion of the immutable audit/proof.
    """
    gid = int(global_id)
    if not (_POOL_FIRST <= gid <= _POOL_LAST):
        return False
    found = (await db.execute(
        _HAS_WALLET_BINDING, {"gid": gid}
    )).scalar_one()
    if not found:
        return False
    await db.execute(_REVOKE_BOUND_TEST_WALLETS, {"gid": gid})
    await quarantine_guest_slot(
        db, gid, reason="TON_TEST_WALLET_BINDING_PRESERVED"
    )
    return True


async def allocate_guest(
    db: AsyncSession, *, resume_token: str | None = None
) -> GuestLease:
    """Allocate or resume one TEST browser slot. Caller commits the transaction."""
    await _assert_target(db)
    await db.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"),
                     {"lock_id": _LOCK_ID})
    reserved_ids = _reserved_test_admin_ids()

    if valid_resume_secret(resume_token):
        row = (await db.execute(_RESUME, {
            "digest": _digest(resume_token), "reserved_ids": reserved_ids,
        })).first()
        if row is not None:
            gid = int(row.global_id)
            if not _POOL_FIRST <= gid <= _POOL_LAST:
                raise GuestPoolConfigurationError("GENESIS_GUEST_INVALID_SLOT")
            if not await is_safe_synthetic_account(db, gid):
                raise GuestPoolConfigurationError("GENESIS_GUEST_CLAIMED_ACCOUNT")
            return GuestLease(f"{gid:010d}", resume_token, row.expires_at)

    # Reclaim at most ten expired places per real visitor arrival. Under
    # advisory lock, reset before deleting their former owner lease.
    # Any unsupported external changes are quarantined, never inherited.
    expired = (await db.execute(
        _EXPIRED, {"reserved_ids": reserved_ids}
    )).scalars().all()
    for old_gid in expired:
        old_gid = int(old_gid)
        if await _quarantine_bound_guest_wallet(db, old_gid):
            await db.execute(_EXPIRED_DELETE, {"gid":old_gid})
            continue
        try:
            # A failed financial reset must roll back its own partial ledger
            # work before the caller persists a quarantine/release decision.
            async with db.begin_nested():
                if not await reusable_starter_is_intact(db, old_gid):
                    await reset_guest_economy(db, old_gid)
        except GuestResetUnsafe:
            await quarantine_guest_slot(
                db, old_gid, reason="EXPIRED_RESTORE_UNSAFE",
            )
        await db.execute(_EXPIRED_DELETE, {"gid":old_gid})

    # Never reassign an unreset slot. Quarantine changed profiles and keep
    # looking; a single stale slot must not block the other 999.
    gid = (await db.execute(
        _CHOOSE, {"reserved_ids": reserved_ids}
    )).scalar_one_or_none()
    while gid is not None:
        gid = int(gid)
        if await reusable_starter_is_intact(db, gid):
            break
        await quarantine_guest_slot(db, gid)
        gid = (await db.execute(
            _CHOOSE, {"reserved_ids": reserved_ids}
        )).scalar_one_or_none()
    if gid is None:
        raise GuestPoolFull("GENESIS_GUEST_POOL_FULL")
    if not await is_safe_synthetic_account(db, gid):
        raise GuestPoolConfigurationError("GENESIS_GUEST_CLAIMED_ACCOUNT")
    token = secrets.token_urlsafe(48)
    result = (await db.execute(_ASSIGN, {"gid": gid, "digest": _digest(token)})).first()
    if result is None:
        raise GuestPoolConfigurationError("GENESIS_GUEST_CONCURRENT_ASSIGNMENT")
    return GuestLease(f"{gid:010d}", token, result.expires_at)


async def release_guest(
    db: AsyncSession, *, global_id: str, resume_token: str | None
) -> bool:
    """Revoke the browser lease on explicit sign-out, never another user's slot."""
    if not valid_resume_secret(resume_token):
        return False
    await _assert_target(db)
    await db.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"),
                     {"lock_id": _LOCK_ID})
    if not (_POOL_FIRST <= int(global_id) <= _POOL_LAST):
        return False
    params = {"gid": int(global_id), "digest": _digest(resume_token)}
    # Check the owner before modifying quarantine: a guessed GID or wrong
    # resume token must never quarantine or release somebody else's slot.
    owned = (await db.execute(_OWNED, params)).scalar_one_or_none()
    if owned is None:
        return False
    if int(global_id) in _reserved_test_admin_ids():
        # Explicit logout ends the active bearer, not the OWNER's TEST profile
        # or exact lease; reservation survives restarts and guest pool cleanup.
        return True
    if await _quarantine_bound_guest_wallet(db, int(global_id)):
        # Wallet history is retained, active bindings are revoked, and this
        # leased ID permanently leaves the reusable guest pool.
        result = await db.execute(_RELEASE, params)
        return result is not None
    if not await reusable_starter_is_intact(db, int(global_id)):
        try:
            # Keep all compensating BANK/user ledger writes in a SAVEPOINT,
            # so an invalid reset cannot leak partially committed entries.
            async with db.begin_nested():
                await reset_guest_economy(db, int(global_id))
        except GuestResetUnsafe:
            await quarantine_guest_slot(
                db, int(global_id), reason="LOGOUT_RESTORE_UNSAFE",
            )
            # Revoke the exact lease; the quarantined slot stays unavailable,
            # and the irreversible audit history is not rewritten.
            result = await db.execute(_RELEASE, params)
            return result is not None
    if not await reusable_starter_is_intact(db, int(global_id)):
        await quarantine_guest_slot(
            db, int(global_id), reason="RESTORE_POSTCHECK_FAILED",
        )
        result = await db.execute(_RELEASE, params)
        return result is not None
    result = (await db.execute(_RELEASE, params)).scalar_one_or_none()
    return result is not None
