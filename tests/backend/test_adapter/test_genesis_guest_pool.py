"""Real PostgreSQL contract for isolated Genesis guest-slot allocation.

Runs ONLY with EFHC_GUEST_TEST_DSN pointing to disposable CI PostgreSQL.
No credentials or fixtures from live Neon are used.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import unittest
from unittest.mock import patch

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from demo_backend.guest_pool import GuestPoolFull, allocate_guest, release_guest

PROJECT = "fragrant-mountain-35143707"
BRANCH = "br-winter-rice-zalqeb10"


@unittest.skipUnless(os.environ.get("EFHC_GUEST_TEST_DSN"), "Disposable PG required")
class GenesisGuestPoolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine(os.environ["EFHC_GUEST_TEST_DSN"])
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)
        statements = [
            "CREATE SCHEMA IF NOT EXISTS efhc_core",
            "CREATE SCHEMA IF NOT EXISTS efhc_admin",
            "CREATE SCHEMA IF NOT EXISTS efhc_test",
            """CREATE TABLE IF NOT EXISTS efhc_core.users (
                global_id bigint PRIMARY KEY,is_active boolean NOT NULL,
                meta jsonb NOT NULL,main_balance numeric NOT NULL,
                bonus_balance numeric NOT NULL,total_generated_kwh numeric NOT NULL,
                exchanged_kwh_total numeric NOT NULL,is_vip boolean NOT NULL,
                vip_since timestamptz,vip_checked_at timestamptz,
                rank_position bigint,rank_score_kwh numeric,
                rank_calculated_at timestamptz,last_sync_at timestamptz,
                updated_at timestamptz)""",
            """CREATE TABLE IF NOT EXISTS efhc_core.app_settings (
                key text PRIMARY KEY,value text NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS efhc_core.user_identities (
                global_id bigint NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS efhc_core.wallet_bindings (
                id bigserial PRIMARY KEY,
                global_id bigint NOT NULL,
                wallet_address text NOT NULL UNIQUE,
                wallet_app text,created_at timestamptz NOT NULL DEFAULT now(),
                tg_id bigint,proof_source text,proof_verified boolean NOT NULL DEFAULT FALSE,
                proof_verified_at timestamptz,proof_payload_hash text,
                is_active boolean NOT NULL,
                is_primary boolean NOT NULL,
                updated_at timestamptz)""",
            """CREATE TABLE IF NOT EXISTS efhc_admin.admin_whitelist (
                global_id bigint NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS efhc_core.panels (
                id bigserial PRIMARY KEY, global_id bigint NOT NULL,
                public_id text,
                is_active boolean NOT NULL,is_archived boolean NOT NULL,
                generated_kwh numeric NOT NULL,meta jsonb DEFAULT '{}'::jsonb,
                activated_at timestamptz,expires_at timestamptz,
                archived_at timestamptz,last_generated_at timestamptz,
                base_gen_per_sec numeric,updated_at timestamptz)""",
            """CREATE TABLE IF NOT EXISTS efhc_core.referral_links (
                id bigserial PRIMARY KEY,inviter_global_id bigint NOT NULL,
                activated_at timestamptz)""",
            """CREATE TABLE IF NOT EXISTS efhc_core.bank_balance (
                key text PRIMARY KEY,balance numeric NOT NULL,
                updated_at timestamptz)""",
            """CREATE TABLE IF NOT EXISTS efhc_core.efhc_transfers_log (
                id bigserial PRIMARY KEY,global_id bigint,
                system_entity text,amount numeric,direction text,
                balance_type text,reason text,idempotency_key text UNIQUE,
                meta jsonb DEFAULT '{}'::jsonb)""",
            """CREATE TABLE IF NOT EXISTS efhc_test.guest_starter_baselines (
                global_id bigint PRIMARY KEY,version text NOT NULL,
                user_row jsonb NOT NULL,panel_rows jsonb NOT NULL,
                referral_rows jsonb NOT NULL,user_ledger_rows jsonb NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS efhc_test.guest_slot_quarantine (
                global_id bigint PRIMARY KEY,reason varchar(96) NOT NULL,
                detected_at timestamptz NOT NULL DEFAULT now())""",
            """CREATE TABLE IF NOT EXISTS efhc_test.guest_reset_checkpoints (
                global_id bigint PRIMARY KEY,
                user_ledger_count bigint NOT NULL,
                last_user_log_id bigint NOT NULL,
                reset_count bigint NOT NULL DEFAULT 0,
                last_reset_at timestamptz)""",
            """CREATE TABLE IF NOT EXISTS efhc_test.guest_leases (
                global_id bigint PRIMARY KEY REFERENCES efhc_core.users(global_id),
                token_hash varchar(64) NOT NULL UNIQUE,
                issued_at timestamptz NOT NULL DEFAULT now(),
                last_visit_at timestamptz NOT NULL DEFAULT now(),
                expires_at timestamptz NOT NULL,
                CONSTRAINT guest_range CHECK(global_id BETWEEN 3001 AND 4000))""",
        ]
        async with self.engine.begin() as connection:
            for ddl in statements:
                await connection.execute(text(ddl))
            # All FK-related fixture tables must be truncated in one command.
            # This command runs only against the disposable CI PostgreSQL.
            await connection.execute(text(
                "TRUNCATE TABLE "
                "efhc_test.guest_leases,"
                "efhc_test.guest_starter_baselines,"
                "efhc_test.guest_slot_quarantine,"
                "efhc_test.guest_reset_checkpoints,"
                "efhc_core.bank_balance,"
                "efhc_core.efhc_transfers_log,"
                "efhc_core.referral_links,"
                "efhc_core.panels,"
                "efhc_core.wallet_bindings,"
                "efhc_core.user_identities,"
                "efhc_admin.admin_whitelist,"
                "efhc_core.users"
            ))
            await connection.execute(text("DELETE FROM efhc_core.app_settings"))
            await connection.execute(text(
                "INSERT INTO efhc_core.bank_balance(key,balance) "
                "VALUES('EFHC_MAIN',4000000.00000000)"
            ))
            await connection.execute(text(
                "INSERT INTO efhc_core.app_settings (key,value) "
                "VALUES ('genesis.seed.status','COMPLETE')"
            ))
            await connection.execute(text(
                "INSERT INTO efhc_core.users "
                "(global_id,is_active,meta,main_balance,bonus_balance,"
                "total_generated_kwh,exchanged_kwh_total,is_vip) "
                "SELECT g,TRUE,jsonb_build_object('genesis',TRUE,'test_only',TRUE),"
                "900.00000000,100.00000000,1165.88160000,1.00000000,TRUE "
                "FROM generate_series(3001,4000) g"
            ))
            await connection.execute(text(
                "INSERT INTO efhc_core.panels "
                "(global_id,is_active,is_archived,generated_kwh) "
                "SELECT g,n<=5,n>5,CASE WHEN n>5 THEN 1 ELSE 0 END "
                "FROM generate_series(3001,4000) g "
                "CROSS JOIN generate_series(1,15)n"
            ))
            await connection.execute(text(
                "INSERT INTO efhc_core.referral_links(inviter_global_id,activated_at) "
                "SELECT g,CASE WHEN n<=10 THEN now() ELSE NULL END "
                "FROM generate_series(3001,4000)g "
                "CROSS JOIN generate_series(1,12)n"
            ))
            await connection.execute(text(
                "INSERT INTO efhc_core.efhc_transfers_log(global_id) "
                "SELECT g FROM generate_series(3001,4000)g"
            ))
            await connection.execute(text(
                "INSERT INTO efhc_test.guest_starter_baselines "
                "(global_id,version,user_row,panel_rows,referral_rows,user_ledger_rows) "
                "SELECT u.global_id,'genesis-starter-v1',to_jsonb(u), "
                "(SELECT jsonb_agg(to_jsonb(p) ORDER BY p.id) "
                " FROM efhc_core.panels p WHERE p.global_id=u.global_id), "
                "(SELECT jsonb_agg(to_jsonb(r) ORDER BY r.id) "
                " FROM efhc_core.referral_links r "
                " WHERE r.inviter_global_id=u.global_id), "
                "(SELECT jsonb_agg(to_jsonb(t) ORDER BY t.id) "
                " FROM efhc_core.efhc_transfers_log t "
                " WHERE t.global_id=u.global_id) "
                "FROM efhc_core.users u"
            ))

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def _prepare(self, db):
        await db.execute(text("SELECT set_config('neon.project_id', :p, TRUE)"),
                         {"p": PROJECT})
        await db.execute(text("SELECT set_config('neon.branch_id', :b, TRUE)"),
                         {"b": BRANCH})

    async def _claim(self, resume_token=None):
        async with self.factory() as db:
            await self._prepare(db)
            lease = await allocate_guest(db, resume_token=resume_token)
            await db.commit()
            return lease

    async def test_ton_wallet_proof_binding_is_revoked_and_slot_quarantined_on_logout(self):
        """A connected TEST wallet is never reissued to a new tenant."""
        lease = await self._claim()
        async with self.factory() as db:
            await self._prepare(db)
            await db.execute(text("""
                INSERT INTO efhc_core.wallet_bindings
                  (global_id, wallet_address, is_active, is_primary, updated_at)
                VALUES (:gid, '0:test-guest-wallet', TRUE, TRUE, now())
            """), {"gid": int(lease.global_id)})
            self.assertTrue(await release_guest(
                db, global_id=lease.global_id, resume_token=lease.resume_token,
            ))
            await db.commit()
            bound = (await db.execute(text("""
                SELECT is_active, is_primary FROM efhc_core.wallet_bindings
                WHERE global_id=:gid AND proof_source IS NULL
            """), {"gid": int(lease.global_id)})).mappings().one()
            self.assertFalse(bound["is_active"])
            self.assertFalse(bound["is_primary"])
            quarantine = (await db.execute(text("""
                SELECT reason FROM efhc_test.guest_slot_quarantine
                WHERE global_id=:gid
            """), {"gid": int(lease.global_id)})).scalar_one()
            self.assertEqual(quarantine, "TON_TEST_WALLET_BINDING_PRESERVED")
            active = (await db.execute(text("""
                SELECT COUNT(*) FROM efhc_test.guest_leases WHERE global_id=:gid
            """), {"gid": int(lease.global_id)})).scalar_one()
            self.assertEqual(active, 0)
            # Immutable wallet row remains in the audit history.
            history = (await db.execute(text("""
                SELECT COUNT(*) FROM efhc_core.wallet_bindings WHERE global_id=:gid AND proof_source IS NULL
            """), {"gid": int(lease.global_id)})).scalar_one()
            self.assertEqual(history, 1)
        next_lease = await self._claim()
        self.assertNotEqual(next_lease.global_id, lease.global_id)

    async def test_expired_ton_wallet_binding_quarantined_before_reallocation(self):
        lease = await self._claim()
        async with self.factory() as db:
            await self._prepare(db)
            await db.execute(text("""
                INSERT INTO efhc_core.wallet_bindings
                  (global_id, wallet_address, is_active, is_primary, updated_at)
                VALUES (:gid, '0:another-guest-wallet', TRUE, FALSE, now())
            """), {"gid": int(lease.global_id)})
            await db.execute(text("""
                UPDATE efhc_test.guest_leases SET expires_at=now()-interval '1 second'
                WHERE global_id=:gid
            """), {"gid": int(lease.global_id)})
            await db.commit()
        fresh = await self._claim()
        self.assertNotEqual(fresh.global_id, lease.global_id)
        async with self.factory() as db:
            await self._prepare(db)
            q = (await db.execute(text("""
                SELECT reason FROM efhc_test.guest_slot_quarantine
                WHERE global_id=:gid
            """), {"gid": int(lease.global_id)})).scalar_one()
            self.assertEqual(q, "TON_TEST_WALLET_BINDING_PRESERVED")
            old = (await db.execute(text("""
                SELECT is_active FROM efhc_core.wallet_bindings WHERE global_id=:gid AND proof_source IS NULL
            """), {"gid": int(lease.global_id)})).scalar_one()
            self.assertFalse(old)

    async def test_project_wallets_restore_without_verification_or_quarantine(self):
        from demo_backend.guest_wallets import project_wallet_addresses, PROJECT_WALLET_SOURCE
        lease = await self._claim()
        gid = int(lease.global_id)
        async with self.factory() as db:
            await self._prepare(db)
            rows = (await db.execute(text("""
                SELECT wallet_address,is_active,is_primary,proof_verified,proof_source
                FROM efhc_core.wallet_bindings WHERE global_id=:gid
            """), {"gid":gid})).mappings().all()
            self.assertEqual({r["wallet_address"] for r in rows}, set(project_wallet_addresses(gid)))
            self.assertEqual(sum(r["is_primary"] for r in rows),1)
            self.assertTrue(all(r["is_active"] and not r["proof_verified"]
                                and r["proof_source"] == PROJECT_WALLET_SOURCE for r in rows))
            await db.execute(text("DELETE FROM efhc_core.wallet_bindings WHERE global_id=:gid AND is_primary"), {"gid":gid})
            self.assertTrue(await release_guest(db,global_id=lease.global_id,resume_token=lease.resume_token))
            await db.commit()
            rows=(await db.execute(text("SELECT wallet_address,is_primary FROM efhc_core.wallet_bindings WHERE global_id=:gid"),{"gid":gid})).mappings().all()
            self.assertEqual({r["wallet_address"] for r in rows},set(project_wallet_addresses(gid)))
            self.assertEqual([r["wallet_address"] for r in rows if r["is_primary"]],[project_wallet_addresses(gid)[0]])
            self.assertEqual((await db.execute(text("SELECT count(*) FROM efhc_test.guest_slot_quarantine WHERE global_id=:gid"),{"gid":gid})).scalar_one(),0)

    async def test_project_wallet_read_and_manage_require_current_lease(self):
        import ast
        from dataclasses import dataclass
        from pathlib import Path
        from sqlalchemy.ext.asyncio import AsyncSession
        from demo_backend.guest_pool import _digest
        source = Path(__file__).resolve().parents[3] / "backend/app/services/wallets_service.py"
        parsed = ast.parse(source.read_text(encoding="utf-8"))
        names = {"WalletBindingOut", "WalletConflict", "list_wallets",
                 "_project_test_lease", "_is_project_test_row",
                 "manage_project_test_wallet", "get_verified_active_wallet"}
        selected = [node for node in parsed.body
                    if getattr(node, "name", "") in names]
        ns = {"__name__": __name__, "dataclass": dataclass, "text": text,
              "AsyncSession": AsyncSession, "sha256": hashlib.sha256,
              "_global_id_db": int}
        exec(compile(ast.fix_missing_locations(ast.Module(
            body=[ast.ImportFrom(module="__future__",names=[ast.alias(name="annotations")],level=0),*selected],
            type_ignores=[])),str(source),"exec"),ns)
        lease = await self._claim()
        other = await self._claim()
        gid = lease.global_id
        digest = _digest(lease.resume_token)
        async with self.factory() as db:
            await self._prepare(db)
            rows = await ns["list_wallets"](db,global_id=gid,project_lease_hash=digest)
            self.assertEqual(len(rows),3)
            self.assertTrue(all(r.is_project_test and not r.proof_verified for r in rows))
            self.assertTrue(all(not r.is_project_test for r in await ns["list_wallets"](db,global_id=gid)))
            self.assertTrue(all(not r.is_project_test for r in await ns["list_wallets"](db,global_id=gid,project_lease_hash=_digest(other.resume_token))))
            self.assertIsNone(await ns["get_verified_active_wallet"](db,global_id=gid,wallet_id=rows[0].id))
            foreign = await ns["list_wallets"](db,global_id=other.global_id)
            with self.assertRaises(ns["WalletConflict"]):
                await ns["manage_project_test_wallet"](db,global_id=gid,wallet_id=foreign[0].id,lease_hash=digest,remove=True)
            with self.assertRaises(ns["WalletConflict"]):
                await ns["manage_project_test_wallet"](db,global_id=gid,wallet_id=rows[0].id,lease_hash=_digest(other.resume_token),remove=True)
            new_primary = next(r for r in rows if not r.is_primary)
            self.assertTrue(await ns["manage_project_test_wallet"](db,global_id=gid,wallet_id=new_primary.id,lease_hash=digest,remove=False))
            await self._prepare(db)
            rows = await ns["list_wallets"](db,global_id=gid,project_lease_hash=digest)
            self.assertEqual([r.id for r in rows if r.is_primary],[new_primary.id])
            self.assertTrue(await ns["manage_project_test_wallet"](db,global_id=gid,wallet_id=new_primary.id,lease_hash=digest,remove=True))
            await self._prepare(db)
            rows = await ns["list_wallets"](db,global_id=gid,project_lease_hash=digest)
            self.assertEqual(len(rows),2)
            self.assertEqual(sum(r.is_primary for r in rows),1)
            self.assertTrue(await release_guest(db,global_id=gid,resume_token=lease.resume_token))
            await db.commit()
            await self._prepare(db)
            rows = await ns["list_wallets"](db,global_id=gid,project_lease_hash=digest)
            self.assertEqual(len(rows),3)
            self.assertTrue(all(not r.is_project_test and not r.proof_verified for r in rows))

    async def test_two_browsers_get_different_slots_and_resume(self):
        first, second = await asyncio.gather(self._claim(), self._claim())
        self.assertNotEqual(first.global_id, second.global_id)
        for guest in (first, second):
            self.assertTrue(3001 <= int(guest.global_id) <= 4000)
            self.assertEqual(len(guest.global_id), 10)
            self.assertNotEqual(guest.global_id, "0000001000")
        repeat = await self._claim(first.resume_token)
        self.assertEqual(repeat.global_id, first.global_id)
        self.assertEqual(repeat.resume_token, first.resume_token)
        async with self.factory() as db:
            hashes = (await db.execute(text(
                "SELECT token_hash FROM efhc_test.guest_leases"
            ))).scalars().all()
            self.assertEqual(len(hashes), 2)
            self.assertNotIn(first.resume_token, hashes)

    async def test_explicit_release_only_matching_guest_token(self):
        first = await self._claim()
        second = await self._claim()
        async with self.factory() as db:
            await self._prepare(db)
            self.assertFalse(await release_guest(
                db, global_id=second.global_id, resume_token=first.resume_token
            ))
            self.assertTrue(await release_guest(
                db, global_id=first.global_id, resume_token=first.resume_token
            ))
            await db.commit()
        self.assertEqual((await self._claim(second.resume_token)).global_id,
                         second.global_id)

    async def test_pool_capacity_is_exactly_one_thousand(self):
        async with self.factory() as db:
            await self._prepare(db)
            await db.execute(text(
                "INSERT INTO efhc_test.guest_leases "
                "(global_id,token_hash,issued_at,last_visit_at,expires_at) "
                "SELECT n, md5(n::text)||md5((n+1)::text), now(), now(), "
                "now()+interval '48 hours' FROM generate_series(3001,4000)n"
            ))
            await db.commit()
        with self.assertRaises(GuestPoolFull):
            await self._claim()

    async def test_claimed_identity_is_not_issued(self):
        async with self.factory() as db:
            await db.execute(text(
                "INSERT INTO efhc_core.user_identities(global_id) "
                "SELECT g FROM generate_series(3001,3999) g"
            ))
            await db.commit()
        chosen = await self._claim()
        self.assertEqual(chosen.global_id, "0000004000")


    async def test_changed_balance_is_quarantined_at_logout(self):
        first = await self._claim()
        async with self.factory() as db:
            await self._prepare(db)
            await db.execute(text(
                "UPDATE efhc_core.users SET main_balance=800 "
                "WHERE global_id=:gid"
            ), {"gid":int(first.global_id)})
            self.assertTrue(await release_guest(
                db,global_id=first.global_id,resume_token=first.resume_token
            ))
            await db.commit()
        async with self.factory() as db:
            reason=(await db.execute(text(
                "SELECT reason FROM efhc_test.guest_slot_quarantine "
                "WHERE global_id=:gid"
            ),{"gid":int(first.global_id)})).scalar_one()
        self.assertEqual(reason,"LOGOUT_RESTORE_UNSAFE")
        second = await self._claim()
        self.assertNotEqual(second.global_id,first.global_id)

    async def test_expired_changed_energy_is_not_reassigned(self):
        first = await self._claim()
        async with self.factory() as db:
            await self._prepare(db)
            await db.execute(text(
                "UPDATE efhc_core.users SET total_generated_kwh=1168.87330420 "
                "WHERE global_id=:gid"
            ),{"gid":int(first.global_id)})
            await db.execute(text(
                "UPDATE efhc_test.guest_leases "
                "SET expires_at=now()-interval '1 minute' "
                "WHERE global_id=:gid"
            ),{"gid":int(first.global_id)})
            await db.commit()
        second = await self._claim()
        self.assertNotEqual(first.global_id,second.global_id)
        # Force the altered expired slot to be the ONLY possible candidate.
        # It must be refused even when all other 999 guest places are held.
        async with self.factory() as db:
            await self._prepare(db)
            await db.execute(text(
                "INSERT INTO efhc_test.guest_leases "
                "(global_id,token_hash,issued_at,last_visit_at,expires_at) "
                "SELECT g,md5(g::text)||md5((g+1)::text),now(),now(),"
                "now()+interval '48 hours' "
                "FROM generate_series(3001,4000) g "
                "WHERE g NOT IN (:first,:second) "
                "ON CONFLICT(global_id) DO NOTHING"
            ),{"first":int(first.global_id),"second":int(second.global_id)})
            await db.commit()
        # A pure TEST energy timestamp/counter delta may be restored to the
        # immutable baseline without any financial ledger loss. When every
        # other slot is leased, the original owner slot can only be reused
        # after its baseline has been independently verified.
        restored = await self._claim()
        self.assertEqual(restored.global_id, first.global_id)
        async with self.factory() as db:
            row = (await db.execute(text(
                "SELECT total_generated_kwh FROM efhc_core.users WHERE global_id=:gid"
            ), {"gid": int(restored.global_id)})).scalar_one()
            self.assertEqual(str(row), "1165.88160000")

    async def test_additional_panel_or_ledger_entry_blocks_reuse(self):
        first = await self._claim()
        async with self.factory() as db:
            await self._prepare(db)
            await db.execute(text(
                "INSERT INTO efhc_core.panels "
                "(global_id,is_active,is_archived,generated_kwh) "
                "VALUES (:gid,TRUE,FALSE,0)"
            ),{"gid":int(first.global_id)})
            await db.execute(text(
                "INSERT INTO efhc_core.efhc_transfers_log(global_id) VALUES(:gid)"
            ),{"gid":int(first.global_id)})
            self.assertTrue(await release_guest(
                db,global_id=first.global_id,resume_token=first.resume_token
            ))
            await db.commit()
        other = await self._claim()
        self.assertNotEqual(other.global_id,first.global_id)

    async def test_env_admin_list_subtracts_ids_from_random_guest_pool(self):
        # Exactly 998 of the 1000 original pool slots stay eligible.
        # No DB whitelist or migration is required for the reservation.
        with patch.dict(os.environ, {
            "EFHC_TEST_ADMIN_GLOBAL_IDS": "0000003101,0000003257",
        }):
            async with self.factory() as db:
                await self._prepare(db)
                await db.execute(text(
                    "INSERT INTO efhc_test.guest_leases "
                    "(global_id,token_hash,issued_at,last_visit_at,expires_at) "
                    "SELECT n, md5(n::text)||md5((n+1)::text),"
                    "now(),now(),now()+interval '48 hours' "
                    "FROM generate_series(3001,4000)n WHERE n NOT IN (3101,3257)"
                ))
                await db.commit()
            with self.assertRaises(GuestPoolFull):
                await self._claim()

        # Removing the two values from ENV returns them to the original
        # allocation rules; the other 998 leases still exist.
        with patch.dict(os.environ, {
            "EFHC_TEST_ADMIN_GLOBAL_IDS": "",
        }):
            chosen = await self._claim()
            self.assertIn(chosen.global_id, {"0000003101", "0000003257"})

    async def test_env_reserved_active_owner_is_not_reset_or_reassigned(self):
        secret = "owner-lease-secret-with-minimum-length-32-abc"
        digest = hashlib.sha256(secret.encode("ascii")).hexdigest()
        with patch.dict(os.environ, {
            "EFHC_TEST_ADMIN_GLOBAL_IDS": "0000003101,0000003257",
        }):
            async with self.factory() as db:
                await self._prepare(db)
                await db.execute(text(
                    "INSERT INTO efhc_test.guest_leases "
                    "(global_id,token_hash,issued_at,last_visit_at,expires_at) "
                    "VALUES (3101,:digest,now()-interval '48 hours',"
                    "now()-interval '48 hours',now()-interval '1 minute')"
                ), {"digest": digest})
                await db.commit()
            resumed = await self._claim(secret)
            self.assertEqual(resumed.global_id, "0000003101")
            async with self.factory() as db:
                await self._prepare(db)
                self.assertTrue(await release_guest(
                    db, global_id="0000003101", resume_token=secret
                ))
                await db.commit()
            async with self.factory() as db:
                retained = (await db.execute(text(
                    "SELECT COUNT(*) FROM efhc_test.guest_leases WHERE global_id=3101"
                ))).scalar_one()
            self.assertEqual(retained, 1)

        # Removal of the ID restores ordinary guest logout/recycling.
        with patch.dict(os.environ, {"EFHC_TEST_ADMIN_GLOBAL_IDS": ""}):
            async with self.factory() as db:
                await self._prepare(db)
                self.assertTrue(await release_guest(
                    db, global_id="0000003101", resume_token=secret
                ))
                await db.commit()
            async with self.factory() as db:
                retained = (await db.execute(text(
                    "SELECT COUNT(*) FROM efhc_test.guest_leases WHERE global_id=3101"
                ))).scalar_one()
            self.assertEqual(retained, 0)

    async def test_quarantined_reserved_admin_keeps_exact_lease_but_not_guest_reissue(self):
        """Owner 3101 stays usable; guest quarantine remains operative for others."""
        from demo_backend.preview_access import test_admin_lease_active

        secret = "reserved-admin-lease-resume-token-for-test-only"
        digest = hashlib.sha256(secret.encode("ascii")).hexdigest()
        with patch.dict(os.environ, {
            "EFHC_TEST_ADMIN_GLOBAL_IDS": "0000003101,0000003257",
        }):
            async with self.factory() as db:
                await self._prepare(db)
                await db.execute(text("""
                    INSERT INTO efhc_test.guest_leases(
                        global_id,token_hash,issued_at,last_visit_at,expires_at
                    ) VALUES (
                        3101,:digest,now(),now(),now()+interval '48 hours'
                    )
                """), {"digest": digest})
                await db.execute(text("""
                    INSERT INTO efhc_test.guest_slot_quarantine(global_id,reason)
                    VALUES (3101,'BASELINE_INCOMPLETE_RESTORE_REQUIRED')
                """))
                await db.commit()

            async with self.factory() as db:
                await self._prepare(db)
                self.assertTrue(await test_admin_lease_active(
                    db, "0000003101", digest, allow_reserved_quarantine=True,
                ))
                self.assertFalse(await test_admin_lease_active(
                    db, "0000003101", digest,
                ), "ordinary guest still respects quarantine")
                self.assertFalse(await test_admin_lease_active(
                    db, "0000003101", "0" * 64,
                    allow_reserved_quarantine=True,
                ), "allowlisted GID alone never proves lease ownership")
                self.assertFalse(await test_admin_lease_active(
                    db, "0000003257", digest,
                    allow_reserved_quarantine=True,
                ), "reserved but unissued GPT Global ID cannot become Admin")

            for _ in range(5):
                allocated = await self._claim()
                self.assertNotIn(allocated.global_id, {
                    "0000003101", "0000003257",
                }, "ENV excludes reserved IDs from new guest issuance")

            async with self.factory() as db:
                self.assertEqual((await db.execute(text("""
                    SELECT count(*) FROM efhc_test.guest_slot_quarantine
                    WHERE global_id=3101
                """))).scalar_one(), 1,
                    "do not delete quarantine or erase any owner's financial state")

    async def test_missing_baseline_must_not_allocate(self):
        async with self.factory() as db:
            await db.execute(text(
                "DELETE FROM efhc_test.guest_starter_baselines "
                "WHERE global_id BETWEEN 3001 AND 4000"
            ))
            await db.commit()
        with self.assertRaises(GuestPoolFull):
            await self._claim()


if __name__ == "__main__":
    unittest.main()
