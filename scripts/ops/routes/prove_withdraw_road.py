"""Static proof helper for withdraw route -> service -> table road."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ROUTE = ROOT / "backend" / "app" / "routes" / "withdraw_routes.py"
SERVICE = ROOT / "backend" / "app" / "services" / "withdraw_service.py"
MODEL = ROOT / "backend" / "app" / "models" / "withdraw_models.py"
MIG = ROOT / "backend" / "migrations" / "versions" / "0001_init.py"
OUT = ROOT / "reports" / "generated" / "withdraw_road_proof.json"

CHECKS = {
    "route_create": (ROUTE, "post_withdraw_request"),
    "route_cancel": (ROUTE, "post_withdraw_cancel"),
    "route_list": (ROUTE, "get_withdraw_list"),
    "service_request": (SERVICE, "request_withdraw"),
    "service_cancel": (SERVICE, "cancel_withdraw"),
    "service_approve": (SERVICE, "approve_withdraw_request"),
    "service_reject": (SERVICE, "reject_withdraw_request"),
    "service_admin_paid": (SERVICE, "admin_mark_paid"),
    "bank_debit": (SERVICE, "debit_user_to_bank"),
    "bank_credit": (SERVICE, "credit_user_from_bank"),
    "event_log": (SERVICE, "_insert_log"),
    "model_table": (MODEL, "withdraw_requests"),
    "migration_anchor": (MIG, "withdraw_requests"),
    "status_pending": (SERVICE, "PENDING"),
    "status_paid": (SERVICE, "PAID"),
    "status_rejected": (SERVICE, "REJECTED"),
    "status_canceled": (SERVICE, "CANCELED"),
}

STATUS_RE = re.compile(r"WITHDRAW_REQ_\w+\s*=\s*[\"']([^\"']+)")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def main() -> None:
    file_cache: dict[Path, str] = {}
    results = []
    for name, (path, needle) in CHECKS.items():
        text = file_cache.setdefault(path, read(path))
        results.append(
            {
                "check": name,
                "file": str(path.relative_to(ROOT)),
                "needle": needle,
                "present": needle in text,
            }
        )
    service_text = file_cache.setdefault(SERVICE, read(SERVICE))
    statuses = sorted(set(STATUS_RE.findall(service_text)))
    data = {
        "checks": results,
        "statuses": statuses,
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
                "checks": len(results),
                "all_required_present": data["all_required_present"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
