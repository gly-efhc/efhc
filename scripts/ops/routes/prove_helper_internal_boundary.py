"""Static road proof helper for helper internal boundary."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "reports/generated/helper_internal_boundary.json"
CHECKS = [
    (
        "sync_routes_present",
        "backend/app/routes/sync_routes.py",
        "APIRouter",
    ),
    (
        "system_routes_present",
        "backend/app/routes/system_routes.py",
        "APIRouter",
    ),
    (
        "admin_sale_packages",
        "backend/app/routes/admin_sale_packages_routes.py",
        "APIRouter",
    ),
    (
        "diagnostics_docs_matrix",
        "docs/NORM/DATABASE_MIGRATION_INVARIANTS_NORM.md",
        "Helper",
    ),
    (
        "helper_route_policy",
        "docs/audits/ROAD_INTEGRITY_AUDIT_OF_AUDIT.md",
        "helper/internal",
    ),
    (
        "rbac_admin_deps",
        "backend/app/routes/admin_routes.py",
        "require_admin",
    ),
    (
        "internal_scheduler",
        "backend/app/scheduler/check_ton_inbox.py",
        "Оркестратор",
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
        "cycle": 1195,
        "road": "helper internal boundary",
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
