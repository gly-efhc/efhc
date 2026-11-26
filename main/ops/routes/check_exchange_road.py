"""Guard for exchange economic road repair work pass."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXCHANGE_ROUTE = ROOT / "backend/app/routes/exchange_routes.py"
USER_ROUTE = ROOT / "backend/app/routes/user_routes.py"
EXCHANGE_SERVICE = ROOT / "backend/app/services/exchange_service.py"
TX_SERVICE = ROOT / "backend/app/services/transactions_service.py"
SEAMS = ROOT / "frontend/src/lib/api/generated/economicUserSeams.ts"
EXCHANGE_PAGE = ROOT / "frontend/src/pages/exchange.tsx"
OPENAPI = ROOT / "backend/openapi/openapi.json"
API = ROOT / "docs/NORM/API_CONTRACTS.md"
OUT = ROOT / "reports/generated/exchange_road.json"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _openapi_paths() -> set[str]:
    data = json.loads(_read(OPENAPI))
    return set(data.get("paths", {}).keys())


def build() -> dict[str, object]:
    route = _read(EXCHANGE_ROUTE)
    user_route = _read(USER_ROUTE)
    service = _read(EXCHANGE_SERVICE)
    tx_service = _read(TX_SERVICE)
    seams = _read(SEAMS)
    page = _read(EXCHANGE_PAGE)
    api = _read(API)
    paths = _openapi_paths()
    old_paths = [
        "/exchange/preview/{tg_id}",
        "/exchange/convert/{tg_id}",
        "/exchange/history/{tg_id}",
        "/user/{tg_id}/exchange/preview",
    ]
    checks = {
        "preview_self_route": '@router.get(\n    "/preview"' in route,
        "convert_self_route": '@router.post(\n    "/convert"' in route,
        "history_self_route": '@router.get(\n    "/history"' in route,
        "route_uses_canonical_owner": (
            "Depends(get_financial_read_owner)" in route
        ),
        "no_exchange_tg_id_paths": (
            not any(p in route for p in old_paths)
        ),
        "no_user_exchange_alias": "/exchange/preview" not in user_route,
        "frontend_preview_self": (
            '"/exchange/preview" as const' in seams
        ),
        "frontend_convert_self": (
            '"/exchange/convert" as const' in seams
        ),
        "frontend_no_replace_tg_id": (
            'EXCHANGE_CONVERT_PATH.replace("{tg_id}"' not in page
            and 'EXCHANGE_PREVIEW_PATH.replace("{tg_id}"' not in page
        ),
        "openapi_self_paths": all(
            p in paths
            for p in [
                "/exchange/preview",
                "/exchange/convert",
                "/exchange/history",
            ]
        ),
        "openapi_old_paths_removed": (
            not any(p in paths for p in old_paths)
        ),
        "idempotency_required": "require_idempotency_key" in route,
        "service_total_generated_guard": (
            "total_after != total_before" in service
        ),
        "partial_exchange_audit": "EXCHANGE_PARTIAL" in tx_service,
        "exchange__all__audit": "EXCHANGE_ALL" in tx_service,
        "mirror_bank_debit": "mirror:{idempotency_key}" in tx_service,
        "api_contract_updated": "POST /exchange/convert" in api,
    }
    ok = all(checks.values())
    return {
        "status": "ok" if ok else "drift",
        "cycle": 1189,
        "road": "exchange economic road",
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
