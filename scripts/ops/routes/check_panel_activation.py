"""Guard for panel activation economic road repair work pass."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ROUTE = ROOT / "backend/app/routes/panels_routes.py"
SERVICE = ROOT / "backend/app/services/panels_service.py"
TX_SERVICE = ROOT / "backend/app/services/transactions_service.py"
PANELS_PAGE = ROOT / "frontend/src/pages/panels.tsx"
OPENAPI = ROOT / "backend/openapi/openapi.json"
API = ROOT / "docs/NORM/API_CONTRACTS.md"
SSOT_ROUTES = ROOT / "docs/SSOT/ssot_pack/SSOT_ROUTES.csv"
OUT = ROOT / "reports/generated/panel_activation.json"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _openapi_paths() -> set[str]:
    data = json.loads(_read(OPENAPI))
    return set(data.get("paths", {}).keys())


def build() -> dict[str, object]:
    route = _read(ROUTE)
    service = _read(SERVICE)
    tx_service = _read(TX_SERVICE)
    page = _read(PANELS_PAGE)
    api = _read(API)
    ssot = _read(SSOT_ROUTES)
    paths = _openapi_paths()
    checks = {
        "activate_self_route": (
            '@router.post(\n    "/activate"' in route
        ),
        "activate_uses_owner": (
            "Depends(get_nonfinancial_read_owner)" in route
        ),
        "old_activate__path__removed": "/activate/{tg_id}" not in route,
        "buy_alias_removed": '"/buy/{tg_id}"' not in route,
        "frontend_uses_self_route": '"/panels/activate"' in page,
        "frontend_no__path__tg_id_activation": (
            "/panels/activate/${tg_id}" not in page
        ),
        "openapi_self_route": "/panels/activate" in paths,
        "openapi_old_aliases_removed": (
            "/panels/activate/{tg_id}" not in paths
            and "/panels/buy/{tg_id}" not in paths
        ),
        "ssot_self_route": "/panels/activate" in ssot,
        "ssot_buy_removed": "/panels/buy/{tg_id}" not in ssot,
        "service_bonus_first": "bonus_first" in service,
        "service_spent_bonus": "spent_bonus" in service,
        "service_spent_main": "spent_main" in service,
        "service_price_100": "PANEL_PRICE" in service,
        "service_bank_call": (
            "spend_user_to_bank_bonus_then__main__nocommit"
            in service
            or "spend_user_to_bank_bonus_then_main" in service
        ),
        "transactions_bonus_then_main": (
            "split_bonus_then_main" in tx_service
        ),
        "api_contract_updated": "POST /panels/activate" in api,
    }
    ok = all(checks.values())
    return {
        "status": "ok" if ok else "drift",
        "cycle": 1190,
        "road": "panel activation economic road",
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
