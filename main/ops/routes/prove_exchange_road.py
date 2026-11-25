"""Static road proof helper for exchange economic road."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports/generated/exchange_road_proof.json"
CHECKS = [
    (
        "preview_route",
        "backend/app/routes/exchange_routes.py",
        "preview",
    ),
    (
        "convert_route",
        "backend/app/routes/exchange_routes.py",
        "convert",
    ),
    (
        "history_route",
        "backend/app/routes/exchange_routes.py",
        "history",
    ),
    (
        "request_exchange",
        "backend/app/services/exchange_service.py",
        "request_exchange",
    ),
    (
        "exchange_main",
        "backend/app/services/exchange_service.py",
        "exchange_kwh_to_efhc",
    ),
    (
        "available_snapshot",
        "backend/app/services/exchange_service.py",
        "_user_energy_snapshot",
    ),
    (
        "audit_attach",
        "backend/app/services/exchange_service.py",
        "_attach_exchange_audit",
    ),
    (
        "bank_exchange_all",
        "backend/app/services/transactions_service.py",
        "exchange__all__available_kwh_to_main",
    ),
    (
        "bank_exchange_partial",
        "backend/app/services/transactions_service.py",
        "exchange_partial_available_kwh_to_main",
    ),
    (
        "user_model",
        "backend/app/models/user_models.py",
        "total_generated_kwh",
    ),
    (
        "migration_users",
        "backend/migrations/versions/0001_initial_release_schema.py",
        "efhc_core.users",
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
        "cycle": 1192,
        "road": "exchange economic road",
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
