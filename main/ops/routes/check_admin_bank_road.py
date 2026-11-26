"""Guard for admin bank action repair work pass."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADMIN_ROUTE = ROOT / "backend/app/routes/admin_routes.py"
BANK_SERVICE = ROOT / "backend/app/services/admin/admin_bank_service.py"
TX_SERVICE = ROOT / "backend/app/services/transactions_service.py"
API = ROOT / "docs/NORM/API_CONTRACTS.md"
OUT = ROOT / "reports/generated/admin_bank_road.json"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def build() -> dict[str, object]:
    route = _read(ADMIN_ROUTE)
    bank = _read(BANK_SERVICE)
    tx = _read(TX_SERVICE)
    api = _read(API)
    checks = {
        "admin_route_imports_rbac": (
            "from app.services.admin.admin_rbac import RBAC" in route
        ),
        "mint_resolves_admin_by_tg_id": (
            "admin = await RBAC.resolve_admin" in route
        ),
        "mint_passes_admin_object": (
            "AdminBankService.mint_efhc" in route
            and "admin=admin" in route
        ),
        "burn_passes_admin_object": (
            "AdminBankService.burn_efhc" in route
            and "admin=admin" in route
        ),
        "no_admin_tg_id_kwarg": "admin_tg_id=" not in route,
        "no_efhc_balance_attr_return": "res.efhc_balance" not in route,
        "mint_burn_commit": route.count("await db.commit()") >= 2,
        "mint_burn_current_balance_return": (
            'res.get("current_balance")' in route
        ),
        "transfer_reports_bank__main__balance": (
            'getattr(res, "bank__main__balance", None)' in route
        ),
        "admin_transfer_uses_tg_id": "tg_id: int" in route,
        "admin_transfer_no_legacy_id_field": (
            "legacy_id" not in route[:2200]
        ),
        "idempotency_header_required": (
            "require_idempotency_key_header_only" in route
        ),
        "bank_service_no_legacy_mint_burn_table": (
            "efhc_mint_burn" not in bank
        ),
        "bank_service_uses_canonical_tx_mint_burn": (
            "mint_bank_efhc" in bank and "burn_bank_efhc" in bank
        ),
        "bank_service_admin_logs": "AdminLogger.write" in bank,
        "tx_service_has_mirror_logs": "mirror:{idempotency_key}" in tx,
        "tx_service_uses_canonical_owner_functions": (
            "async def credit_user_from_bank(" in tx
            and "async def debit_user_to_bank(" in tx
            and "credit_user__main__from_bank_by_tg_id" not in tx
            and "debit_user__main__to_bank_by_tg_id" not in tx
        ),
        "api_contract_mentions_admin_transfer": (
            "POST /admin/transfer" in api
        ),
    }
    ok = all(checks.values())
    return {
        "status": "ok" if ok else "drift",
        "cycle": 1192,
        "road": "admin bank action road",
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
