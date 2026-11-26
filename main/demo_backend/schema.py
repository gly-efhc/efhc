"""Read-only compatibility inventory of existing Neon TEST objects."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Baseline read directly from existing Neon TEST branch (2026-11-05).
# Do not create new tables or views here. Report exactly which objects are absent.
REQUIRED_TABLES = {
    "efhc_admin": {
        "admin_action_log", "admin_nft_whitelist", "admin_notifications",
        "admin_role", "admin_whitelist", "efhc_sale_packages", "idempotency_key",
    },
    "efhc_core": {
        "achievements", "ad_admin_audit_log", "ad_daily_counters", "ad_events",
        "ad_provider_claims", "ad_provider_configs", "ad_provider_daily_metrics",
        "ad_sessions", "ads", "alembic_version", "app_settings", "auth_challenges",
        "auth_sessions", "bank_balance", "bank_metrics_snapshot", "efhc_transfers_log",
        "hub_links", "outcome_fallback_promos", "panels", "payment_intents",
        "processed_external_events", "referral_bonus_ledger", "referral_codes",
        "referral_links", "scheduler_task_log", "shop_items", "shop_orders",
        "system_templates", "task_bonus_log", "task_complete_lock", "task_submissions",
        "tasks", "ton_inbox_logs", "tx_hash_locks", "unmatched_incoming",
        "user_cosmetics", "user_identities", "user_roles", "user_skins",
        "user_tasks_status", "users", "wallet_bindings", "wallet_connect_idempotency",
        "wallet_proof_token_uses", "withdraw_outcome_events", "withdraw_requests",
        "withdrawals",
    },
}
REQUIRED_VIEWS = {
    "accounts", "bank_overview", "bootstrap_snapshot", "catalog_rows",
    "economic_events", "ledger", "panels", "payment_intents", "table_counts", "transfers_all",
}


async def inspect_schema(
    db: AsyncSession, *, require_demo_views: bool = True,
) -> dict:
    sql = text("""SELECT table_schema, table_name, table_type FROM information_schema.tables
        WHERE table_schema IN ('efhc_core','efhc_admin','efhc_demo_public')
        ORDER BY table_schema, table_name""")
    result = (await db.execute(sql)).mappings().all()
    objects = [{"schema": str(r["table_schema"]), "name": str(r["table_name"]),
                "type": str(r["table_type"])} for r in result]
    physical = {(r["schema"], r["name"]) for r in objects if r["type"] == "BASE TABLE"}
    views = {(r["schema"], r["name"]) for r in objects if r["type"] == "VIEW"}
    missing = sorted(
        [f"{schema}.{table}" for schema, names in REQUIRED_TABLES.items()
         for table in names if (schema, table) not in physical]
        + ([f"efhc_demo_public.{view}" for view in REQUIRED_VIEWS
            if ("efhc_demo_public", view) not in views]
           if require_demo_views else [])
    )
    return {"ok": not missing, "total": len(objects), "tables": objects,
            "physical_tables": len(physical),
            "views": sum(r["type"] == "VIEW" for r in objects), "missing": missing,
            "legacy_demo_views_required": require_demo_views}


async def check_user(db: AsyncSession, global_id: str) -> bool:
    if not isinstance(global_id, str) or len(global_id) != 10 or not global_id.isascii() or not global_id.isdigit() or global_id == "0000000000":
        return False
    result = await db.execute(text("SELECT 1 FROM efhc_core.users WHERE global_id=:gid AND is_active IS TRUE LIMIT 1"), {"gid": int(global_id)})
    return result.scalar_one_or_none() == 1


async def assert_completed_genesis(db: AsyncSession) -> None:
    """Exact Genesis branch and immutable financial invariants; no DDL/writes.

    The legacy demo_public compatibility views are NOT a requirement for the
    new Genesis dataset; its canonical source remains the 54 core/admin tables.
    """
    row = (await db.execute(text("""
      SELECT
        current_setting('neon.project_id', true) AS project_id,
        current_setting('neon.branch_id', true) AS branch_id,
        current_database() AS database_name,
        (SELECT value FROM efhc_core.app_settings
          WHERE key='genesis.seed.status') AS marker,
        (SELECT COUNT(*) FROM efhc_core.users) AS users,
        (SELECT COUNT(*) FROM efhc_core.panels) AS panels,
        (SELECT COUNT(*) FROM efhc_core.referral_links) AS referrals,
        (SELECT COUNT(*) FROM efhc_core.referral_links
          WHERE activated_at IS NOT NULL) AS activated,
        (SELECT COUNT(*) FROM efhc_core.users
          WHERE rank_position IS NOT NULL) AS ranked,
        (SELECT balance FROM efhc_core.bank_balance
          WHERE key='EFHC_MAIN') AS bank,
        (SELECT COALESCE(SUM(main_balance+bonus_balance),0)
          FROM efhc_core.users) AS user_balances,
        (SELECT COUNT(*) FROM efhc_core.users WHERE global_id=88)
         +(SELECT COUNT(*) FROM efhc_core.panels WHERE global_id=88)
         +(SELECT COUNT(*) FROM efhc_core.efhc_transfers_log WHERE global_id=88)
         +(SELECT COUNT(*) FROM efhc_core.referral_links
           WHERE inviter_global_id=88 OR invitee_global_id=88)
         AS reserved_identity_records
    """))).mappings().one()
    checks = {
        "project_id": "fragrant-mountain-35143707",
        "branch_id": "br-winter-rice-zalqeb10",
        "database_name": "neondb",
        "marker": "COMPLETE",
        "users": 16000,
        "referrals": 12000,
        "activated": 10000,
        "ranked": 16000,
        "reserved_identity_records": 0,
    }
    for key, expected in checks.items():
        if str(row[key]) != str(expected):
            raise RuntimeError("GENESIS_TEST_STARTUP_INVARIANT:" + key)
    # Genesis is now an interactive TEST economy. A canonical purchase
    # creates a new globally numbered panel; a reset leaves a physical
    # tombstone so that PNL numbers are never reused. Reject lost seed
    # panels, but never require the mutable panel count to equal its seed.
    if int(row["panels"]) < 36999:
        raise RuntimeError("GENESIS_TEST_STARTUP_INVARIANT:panels")

    from decimal import Decimal
    bank = Decimal(str(row["bank"]))
    supply = bank + Decimal(str(row["user_balances"]))
    if supply != Decimal("5000000.00000000"):
        raise RuntimeError("GENESIS_TEST_STARTUP_BANK_SUPPLY_MISMATCH")
