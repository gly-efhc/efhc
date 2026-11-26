"""Static road proof helper for deposit and watcher truth road."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports/generated/deposit_watcher_road_proof.json"
CHECKS = [
    (
        "deposit_packages_route",
        "backend/app/routes/deposit_routes.py",
        "list_deposit_packages",
    ),
    (
        "deposit_create_route",
        "backend/app/routes/deposit_routes.py",
        "deposit_efhc",
    ),
    (
        "intent_create_service",
        "backend/app/services/payment_intents_service.py",
        "create_intent_deposit_by_package",
    ),
    (
        "tonconnect_builder",
        "backend/app/services/payment_intents_service.py",
        "build_tonconnect_tx",
    ),
    (
        "watcher_process_tx",
        "backend/app/services/watcher_service.py",
        "process_incoming_tx",
    ),
    (
        "watcher_confirm_intent",
        "backend/app/services/watcher_service.py",
        "_confirm_payment_intent",
    ),
    (
        "ton_log_upsert",
        "backend/app/services/watcher_service.py",
        "_ton_log_upsert",
    ),
    (
        "deposit_credit_service",
        "backend/app/services/efhc_deposits_service.py",
        "process_efhc_deposit",
    ),
    (
        "bank_credit_anchor",
        "backend/app/services/efhc_deposits_service.py",
        "credit_user_from_bank",
    ),
    (
        "payment_intent_model",
        "backend/app/models/payment_intents_models.py",
        "payment_intents",
    ),
    (
        "ton_log_model",
        "backend/app/models/ton_logs_models.py",
        "ton_logs",
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
        "cycle": 1191,
        "road": "deposit and watcher truth road",
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
