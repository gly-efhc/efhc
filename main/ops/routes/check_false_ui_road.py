"""Guard for work pass false UI road repair."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> int:
    frontend_panels = read("frontend/src/pages/panels.tsx")
    panels_service_ts = read("frontend/src/services/panels.service.ts")
    panels_seams_ts = read(
        "frontend/src/lib/api/generated/economicUserSeams.ts"
    )
    panels_routes = read("backend/app/routes/panels_routes.py")
    user_routes = read("backend/app/routes/user_routes.py")
    api_contracts = read("docs/NORM/API_CONTRACTS.md")
    openapi = json.loads(read("backend/openapi/openapi.json"))
    paths = set(openapi.get("paths", {}))

    checks = {
        "frontend_uses_self_panels_summary": (
            "PANELS_SUMMARY_PATH" in panels_service_ts
            and '"/user/me/panels-summary"' in panels_seams_ts
        ),
        "frontend_does_not__call__tg_summary": (
            "/panels/${tg_id}/summary" not in frontend_panels
        ),
        "backend_removed_tg_summary_route": (
            '"/{tg_id}/summary"' not in panels_routes
        ),
        "backend_keeps_self_summary_route": (
            '"/me/panels-summary"' in user_routes
        ),
        "openapi_removed_tg_summary": (
            "/panels/{tg_id}/summary" not in paths
        ),
        "openapi_keeps_self_summary": (
            "/user/me/panels-summary" in paths
        ),
        "contracts__name__self_summary": (
            "GET /user/me/panels-summary" in api_contracts
        ),
        "contracts_do_not__name__tg_summary_active": (
            "### GET /panels/{tg_id}/summary" not in api_contracts
        ),
    }
    missing = sorted(k for k, v in checks.items() if not v)
    out = {
        "cycle": 1193,
        "status": "ok" if not missing else "failed",
        "road": "false UI panels-summary road",
        "checks": checks,
        "missing": missing,
    }
    out_path = ROOT / "reports/generated/false_ui_road.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(out, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
