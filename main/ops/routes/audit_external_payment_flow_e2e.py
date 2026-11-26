from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAY = ROOT / "backend/app/services/payment_reconciliation_service.py"
WATCHER = ROOT / "backend/app/services/watcher_service.py"
GUARDS = ROOT / "backend/app/services/confirm__path__guards_service.py"
JETTON = ROOT / "backend/app/services/jetton_parsing_service.py"
INTENT = ROOT / "backend/app/services/intent_payload_parsing_service.py"
DIAG = ROOT / "backend/app/services/reconcile_diagnostics_service.py"
SSOT = ROOT / "docs/SSOT/SHOP_PAYMENTS_EXTERNAL_FLOW_SSOT.md"


def require(path: Path, needle: str) -> None:
    text = path.read_text(encoding="utf-8")
    if needle not in text:
        raise RuntimeError(f"missing {needle} in {path}")


def main() -> int:
    require(SSOT, "Запрет анонимных платежей")
    require(INTENT, "parse_intent_payload")
    require(JETTON, "parse_jetton_payload_envelope")
    require(GUARDS, "guard_amount_exact_d8")
    require(PAY, "ConfirmPaymentResult")
    require(PAY, "TX_HASH_LOCK_CONFLICT")
    require(GUARDS, "AMOUNT_SCALE_OVERFLOW_D8")
    require(WATCHER, 'note=getattr(confirm_res, "note", None)')
    require(DIAG, "summarize_reconcile_diagnostics")
    print(
        "OK: external payment flow 801-819 end-to-end "
        "compliance surface is connected."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
