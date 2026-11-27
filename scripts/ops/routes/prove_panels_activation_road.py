"""Static road proof helper for panels activation road."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "main"
OUT = ROOT / "reports/generated/panels_activation_road_proof.json"
CHECKS = [
    (
        "summary_route",
        "backend/app/routes/panels_routes.py",
        "get_panels_summary",
    ),
    (
        "active_route",
        "backend/app/routes/panels_routes.py",
        "list_active_panels",
    ),
    (
        "archive_route",
        "backend/app/routes/panels_routes.py",
        "list_archived_panels",
    ),
    (
        "activation_route",
        "backend/app/routes/panels_routes.py",
        "activate_panel_route",
    ),
    (
        "legacy_buy_route",
        "backend/app/routes/panels_routes.py",
        "buy_panel",
    ),
    (
        "service_activate",
        "backend/app/services/panels_service.py",
        "activate_panel",
    ),
    (
        "panel_price",
        "backend/app/services/panels_service.py",
        "PANEL_PRICE",
    ),
    (
        "bonus_first",
        "backend/app/services/panels_service.py",
        "bonus",
    ),
    (
        "create_record",
        "backend/app/services/panels_service.py",
        "_create_panel_record",
    ),
    (
        "panel_model",
        "backend/app/models/panels_models.py",
        "panels",
    ),
    (
        "migration_metadata_strategy",
        "backend/migrations/versions/0001_initial_release_schema.py",
        "RELEASE_METADATA.create_all",
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
        "cycle": 1193,
        "road": "panels activation road",
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
