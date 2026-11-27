"""Guard for deposit and watcher truth repair."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "main"
DEPOSIT_ROUTE = ROOT / "backend/app/routes/deposit_routes.py"
PAYMENT_ROUTE = ROOT / "backend/app/routes/payment_intents_routes.py"
INTENTS = ROOT / "backend/app/services/payment_intents_service.py"
RECONCILE = (
    ROOT / "backend/app/services/payment_reconciliation_service.py"
)
WATCHER = ROOT / "backend/app/services/watcher_service.py"
LOCKS = (
    ROOT / "backend/app/services/shop_payment_tx_hash_lock_service.py"
)
API = ROOT / "docs/SSOT/APPLICATION_FUNCTION_SURFACE.md"
OUT = ROOT / "reports/generated/deposit_watcher.json"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def build() -> dict[str, object]:
    deposit_route = _read(DEPOSIT_ROUTE)
    payment_route = _read(PAYMENT_ROUTE)
    intents = _read(INTENTS)
    reconcile = _read(RECONCILE)
    watcher = _read(WATCHER)
    locks = _read(LOCKS)
    api = _read(API)

    checks = {
        "deposit_requires_auth": (
            "get_financial_read_owner" in deposit_route
        ),
        "deposit_requires_wallet": (
            "require_wallet_connected" in deposit_route
        ),
        "deposit_requires_idempotency": (
            "require_idempotency_key" in deposit_route
        ),
        "intent_payload_carries_owner": (
            "def build_payload(" in intents
            and 'owner_token = f"G{global_id}"' in intents
            and "owner_token = str(int(tg_id))" not in intents
        ),
        "intent_status_owner_only": (
            "WHERE id = :iid AND global_id = :global_id" in intents
        ),
        "historical_telegram_payload_read_through": (
            'memo_tg_id = ip.get("tg_id")' in watcher
            and "_find_user_by_tg_id" in watcher
        ),
        "status_route_checks_ok_flag": (
            'row.get("ok") is not True' in payment_route
        ),
        "status_route_strips_ok_flag": (
            'row.pop("ok", None)' in payment_route
        ),
        "watcher_uses_intent_parser": (
            "parse_intent_payload" in watcher
        ),
        "watcher_blocks_bad_transport": (
            "Intent transport blocked" in watcher
        ),
        "watcher_records_unmatched": (
            "_record_unmatched_incoming" in watcher
        ),
        "watcher_updates_inbox_status": ("_ton_log_upsert" in watcher),
        "watcher_enforces_180d_time_barrier": (
            "validate_external_financial_execution" in watcher
            and "STATUS_EXPIRED_NO_CREDIT" in watcher
            and "trusted_operation_at" in watcher
        ),
        "reconcile_enforces_180d_time_barrier": (
            "validate_external_financial_execution" in reconcile
            and "trusted_operation_at" in reconcile
            and "server_first_seen_at" in reconcile
        ),
        "tx_hash_claim_rechecks_time_before_replay": (
            "require_external_financial_execution" in locks
            and "trusted_operation_at" in locks
            and "server_first_seen_at" in locks
        ),
        "reconcile_locks_tx_hash": (
            "acquire_tx_hash_lock" in reconcile
        ),
        "reconcile_rejects_reused_hash": (
            "TX_HASH_ALREADY_USED" in reconcile
        ),
        "reconcile_exact_amount": (
            "guard_amount_exact_d8" in reconcile
        ),
        "reconcile_exact_asset": ("guard_asset_exact" in reconcile),
        "reconcile_exact_destination": (
            "guard_destination_exact" in reconcile
        ),
        "reconcile_confirms_status": (
            "status = 'CONFIRMED'" in reconcile
        ),
        "reconcile_commits_confirm": ("await db.commit()" in reconcile),
        "tx_hash_lock_table": "tx_hash_locks" in locks,
        "api_contract_mentions_status": (
            "/payment-intents/{intent_id}" in api
            and "get_payment_intent_status" in api
        ),
    }
    ok = all(checks.values())
    data = {
        "status": "ok" if ok else "drift",
        "cycle": 1188,
        "road": "deposit and watcher truth road",
        "checks": checks,
        "all_required_present": ok,
    }
    return data


def main() -> int:
    data = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(data, ensure_ascii=False))
    return 0 if data["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
