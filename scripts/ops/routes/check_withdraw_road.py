"""Guard for withdraw economic road repair."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ROUTE = ROOT / "backend/app/routes/withdraw_routes.py"
ADMIN = ROOT / "backend/app/services/admin/admin_withdrawals_service.py"
USER = ROOT / "backend/app/services/withdraw_service.py"
OUTCOME = ROOT / "backend/app/services/outcome_service.py"
API = ROOT / "docs/NORM/API_CONTRACTS.md"
OUT = ROOT / "reports/generated/withdraw_road.json"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def build() -> dict[str, object]:
    route = _read(ROUTE)
    admin = _read(ADMIN)
    user = _read(USER)
    outcome = _read(OUTCOME)
    api = _read(API)

    checks = {
        "список_использует_financial_owner": (
            "FinancialReadOwner" in route
            and "Depends(get_financial_read_owner)" in route
        ),
        "есть_global_read_branch": "global_id=owner.global_id" in route,
        "нет_route_legacy_owner_branch": (
            "tg_id=owner.require_legacy_tg_id()" not in route
        ),
        "request_требует_idempotency": (
            "require_idempotency_key" in route
        ),
        "request_вызывает_service": "request_withdraw(" in route,
        "cancel_вызывает_service": "cancel_withdraw(" in route,
        "approve_paid_replay_проверен": (
            "row.status == WithdrawalStatus.PAID" in admin
        ),
        "approve_same_key_replay_проверен": (
            "processing_ik == req.idempotency_key" in admin
        ),
        "approve_делает_commit": (
            "await db.commit()\n\n        return {" in admin
        ),
        "reject_делает_commit": (
            "await db.commit()\n        return {" in admin
        ),
        "hold_списывает_в_bank": (
            "debit_user_to_bank_nocommit(" in user
            or "debit_user_to_bank(" in user
        ),
        "refund_возвращает_из_bank": "credit_user_from_bank(" in user,
        "admin_refund_возвращает": "credit_user_from_bank(" in admin,
        "outcome_сохраняется": "save_withdraw_outcome_event(" in admin,
        "outcome_bundle_создаётся": (
            "build_withdraw_outcome_bundle(" in admin
        ),
        "outcome_table_присутствует": (
            "withdraw_outcome_events" in outcome
        ),
        "api_contract_обновлён": "POST /withdraw/request" in api,
    }
    ok = all(checks.values())
    data = {
        "статус": "ok" if ok else "drift",
        "цикл": 1187,
        "контур": "экономический контур withdrawals",
        "проверки": checks,
        "все_обязательные_условия": ok,
    }
    return data


def main() -> int:
    data = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(data, ensure_ascii=False))
    return 0 if data["статус"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
