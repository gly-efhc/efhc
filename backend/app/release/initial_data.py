"""Idempotent creation of required EFHC system data."""

from __future__ import annotations

from decimal import Decimal

from app.release.database_connection import connect

BANK_BALANCE = Decimal("5000000.00000000")
BANK_SYSTEM_ENTITY = "BANK_EFHC"

SYSTEM_MANAGED_HUB_LINKS: dict[str, dict[str, object]] = {
    "efhc_buy": {
        "title": "Hub EFHC",
        "subtitle": "External buy-flow handoff for EFHC.",
        "url": "/hub/efhc-handoff",
        "target_kind": "backend_handoff",
        "open_mode": "same_app",
        "sort_order": 10,
        "is_active": True,
        "icon_key": "efhc",
    },
    "vip_getgems": {
        "title": "Hub VIP",
        "subtitle": "Open VIP NFT collection on GetGems.",
        "url": "https://getgems.io/efhc-nft",
        "target_kind": "external_url",
        "open_mode": "external_browser",
        "sort_order": 20,
        "is_active": True,
        "icon_key": "vip",
    },
}
# Every code not listed above is user-managed.
# Seed never changes it.
USER_MANAGED_HUB_LINK_CODES: frozenset[str] = frozenset()



def seed_initial_data() -> dict[str, object]:
    """Insert only missing system rows; never reset user data."""
    scheduler_defaults = {
        "scheduler.enabled": "true",
        "scheduler.ton_reconcile_tick_counter": "0",
        "scheduler.ton_reconcile_last_success_at": "",
        "ranks.last_snapshot_at": "",
        "ranks.total_users": "0",
        "ranks.last_daily_claim_date": "",
    }
    templates = {
        "task_reject_fallback": (
            "Выполнение не подтверждено.",
            "Автоответ при отклонении задания",
        ),
        "task_approve_fallback": (
            None,
            "Автоответ при одобрении задания",
        ),
    }
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO efhc_core.bank_balance "
            "(key, balance) VALUES (%s, %s) "
            "ON CONFLICT (key) DO NOTHING",
            ("EFHC_MAIN", BANK_BALANCE),
        )
        for key, value in scheduler_defaults.items():
            cur.execute(
                "INSERT INTO efhc_core.app_settings "
                "(key, value) VALUES (%s, %s) "
                "ON CONFLICT (key) DO NOTHING",
                (key, value),
            )
        for key, (content, description) in templates.items():
            cur.execute(
                "INSERT INTO efhc_core.system_templates "
                "(key, content, description) "
                "VALUES (%s, %s, %s) "
                "ON CONFLICT (key) DO NOTHING",
                (key, content, description),
            )
        for code, row in SYSTEM_MANAGED_HUB_LINKS.items():
            cur.execute(
                "INSERT INTO efhc_core.hub_links "
                "(code, title, subtitle, url, target_kind, open_mode, "
                "is_active, sort_order, icon_key) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (code) DO UPDATE SET "
                "title = EXCLUDED.title, "
                "subtitle = EXCLUDED.subtitle, "
                "url = EXCLUDED.url, "
                "target_kind = EXCLUDED.target_kind, "
                "open_mode = EXCLUDED.open_mode, "
                "is_active = EXCLUDED.is_active, "
                "sort_order = EXCLUDED.sort_order, "
                "icon_key = EXCLUDED.icon_key",
                (
                    code,
                    row["title"],
                    row["subtitle"],
                    row["url"],
                    row["target_kind"],
                    row["open_mode"],
                    row["is_active"],
                    row["sort_order"],
                    row["icon_key"],
                ),
            )
        conn.commit()

    return {
        "bank_efhc": BANK_SYSTEM_ENTITY,
        "settings": len(scheduler_defaults),
        "templates": len(templates),
        "hub_links": len(SYSTEM_MANAGED_HUB_LINKS),
        "status": "ok",
    }


def validate_initial_data() -> dict[str, object]:
    """Ensure required rows exist after idempotent seeding."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM efhc_core.bank_balance "
            "WHERE key = 'EFHC_MAIN'"
        )
        if int(cur.fetchone()[0]) != 1:
            raise RuntimeError("EFHC_MAIN bank balance is missing")
    return {"status": "ok", "bank_efhc": BANK_SYSTEM_ENTITY}
