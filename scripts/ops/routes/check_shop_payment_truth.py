"""Guard for shop and payment truth repair work pass."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SHOP_ROUTE = ROOT / "backend/app/routes/shop_routes.py"
HUB_ROUTE = ROOT / "backend/app/routes/hub_routes.py"
SHOPFRONT_ROUTE = ROOT / "backend/app/routes/shopfront_routes.py"
PAYMENT_INTENTS = (
    ROOT / "backend/app/services/payment_intents_service.py"
)
RECONCILE = (
    ROOT / "backend/app/services/payment_reconciliation_service.py"
)
SHOP_SERVICE = ROOT / "backend/app/services/shop_service.py"
API = ROOT / "docs/NORM/API_CONTRACTS.md"
OUT = ROOT / "reports/generated/shop_payment_truth.json"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def build() -> dict[str, object]:
    shop_route = _read(SHOP_ROUTE)
    hub_route = _read(HUB_ROUTE)
    shopfront = _read(SHOPFRONT_ROUTE)
    intents = _read(PAYMENT_INTENTS)
    reconcile = _read(RECONCILE)
    shop_service = _read(SHOP_SERVICE)
    api = _read(API)
    checks = {
        "shop_route_rejects_incomplete_payload": (
            "External order payload is incomplete" in shop_route
        ),
        "shop_route_requires_order_id": (
            "External order id is missing" in shop_route
        ),
        "shop_route_links_intent_payload": (
            "'intent_payload', :m" in shop_route
            and "'intent_id', :iid" in shop_route
        ),
        "shop_route_links_owner": (
            "'payment_owner_global_id', :global_id" in shop_route
        ),
        "hub_route_requires_order_id": (
            "External order id is missing" in hub_route
        ),
        "hub_status_handles_ok_false": (
            'row.get("ok") is not True' in hub_route
        ),
        "hub_status_strips_internal_ok": (
            'row.pop("ok", None)' in hub_route
        ),
        "shopfront_status_uses_hub_status": (
            "get_browser_shop_intent_status" in shopfront
        ),
        "intent_status_order_link_by_intent_id": (
            "extra ->> 'intent_id'" in intents
        ),
        "intent_status_builds_flow_truth": (
            "_build_intent_flow_truth" in intents
        ),
        "reconcile_handles_shop_external": (
            'purpose == "shop_external"' in reconcile
        ),
        "reconcile_has_tx_hash_lock": (
            "acquire_tx_hash_lock" in reconcile
        ),
        "reconcile_updates_paid_auto": (
            "SET status = 'PAID_AUTO'" in reconcile
        ),
        "reconcile_commits": "await db.commit()" in reconcile,
        "shop_service_canonical_memo": (
            "canonical_memo" in shop_service
        ),
        "api_contract_mentions_shop_order_external": (
            "POST /shop/order-external" in api
        ),
    }
    ok = all(checks.values())
    return {
        "status": "ok" if ok else "drift",
        "cycle": 1191,
        "road": "shop and payment truth road",
        "checks": checks,
        "all_required_present": ok,
    }


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
