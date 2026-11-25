"""Static road proof helper for shop payment truth road."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports/generated/shop_payment_truth_road_proof.json"
CHECKS = [
    (
        "shop_catalog_route",
        "backend/app/routes/shop_routes.py",
        "get_shop_catalog",
    ),
    (
        "shop_external_order_route",
        "backend/app/routes/shop_routes.py",
        "create_order_external",
    ),
    (
        "shopfront_bootstrap",
        "backend/app/routes/shopfront_routes.py",
        "shopfront_bootstrap",
    ),
    (
        "shopfront_create_intent",
        "backend/app/routes/shopfront_routes.py",
        "shopfront_create_intent",
    ),
    (
        "intent_status_route",
        "backend/app/routes/payment_intents_routes.py",
        "get_payment_intent_status",
    ),
    (
        "create_shop_intent",
        "backend/app/services/payment_intents_service.py",
        "create_intent_shop_external",
    ),
    (
        "intent_status_service",
        "backend/app/services/payment_intents_service.py",
        "get_intent_status_for_user",
    ),
    (
        "confirm_payment",
        "backend/app/services/payment_reconciliation_service.py",
        "confirm_payment_intent",
    ),
    (
        "finalize_order",
        "backend/app/services/orders_service.py",
        "finalize_order_by_payment",
    ),
    (
        "shop_order_model",
        "backend/app/models/order_models.py",
        "orders",
    ),
    (
        "payment_intent_model",
        "backend/app/models/payment_intents_models.py",
        "payment_intents",
    ),
    (
        "migration_payment_intents",
        "backend/migrations/versions/0001_initial_release_schema.py",
        "payment_intents",
    ),
]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def main() -> None:
    cache: dict[Path, str] = {}
    results = []
    for name, rel_path, needle in CHECKS:
        path = ROOT / rel_path
        exists = path.exists()
        text = cache.setdefault(path, read(path)) if exists else ""
        results.append(
            {
                "check": name,
                "file": rel_path,
                "needle": needle,
                "present": bool(exists and needle in text),
            }
        )
    data = {
        "cycle": 1194,
        "road": "shop payment truth road",
        "checks": results,
        "all_required_present": all(r["present"] for r in results),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "cycle": data["cycle"],
                "checks": len(results),
                "all_required_present": data["all_required_present"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
