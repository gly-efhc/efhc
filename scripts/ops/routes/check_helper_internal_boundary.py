"""Guard for work pass helper/internal boundary repair."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "main"


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> int:
    system_routes = read("backend/app/routes/system_routes.py")
    internal_routes = read(
        "docs/SSOT/ssot_pack/SSOT_INTERNAL_ROUTES.csv"
    )
    openapi = json.loads(read("backend/openapi/openapi.json"))
    paths = set(openapi.get("paths", {}))

    checks = {
        "cron_hidden_from_schema": (
            '@router.get("/cron/tick", include_in_schema=False)'
            in system_routes
        ),
        "webhook_hidden_from_schema": (
            '@router.post("/tg/webhook", include_in_schema=False)'
            in system_routes
        ),
        "cron_secret_check_present": "CRON_SECRET" in system_routes,
        "webhook_secret_check_present": (
            "TELEGRAM_WEBHOOK_SECRET" in system_routes
        ),
        "openapi_hides_cron": "/cron/tick" not in paths,
        "openapi_hides_webhook": "/tg/webhook" not in paths,
        "internal_registry_marks_cron": (
            "/cron/tick,cron_tick" in internal_routes
            and "INTERNAL_SECRET,false" in internal_routes
        ),
        "internal_registry_marks_webhook": (
            "/tg/webhook,telegram_webhook" in internal_routes
            and "INTERNAL_WEBHOOK,false" in internal_routes
        ),
    }
    missing = sorted(k for k, v in checks.items() if not v)
    out = {
        "cycle": 1194,
        "status": "ok" if not missing else "failed",
        "road": "helper/internal boundary",
        "checks": checks,
        "missing": missing,
    }
    out_path = ROOT / "reports/generated/helper_internal.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(out, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
