from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WATCHER = ROOT / "backend/app/services/watcher_service.py"
PIS = ROOT / "backend/app/services/payment_intents_service.py"
SHOP_ROUTES = ROOT / "backend/app/routes/shop_routes.py"
ADMIN_ROUTES = ROOT / "backend/app/routes/admin_routes.py"
SSOT = ROOT / "docs/SSOT/SHOP_PAYMENTS_EXTERNAL_FLOW_SSOT.md"


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise RuntimeError(f"missing {label}: {needle}")


def main() -> int:
    ssot = SSOT.read_text(encoding="utf-8")
    watcher = WATCHER.read_text(encoding="utf-8")
    pis = PIS.read_text(encoding="utf-8")
    shop = SHOP_ROUTES.read_text(encoding="utf-8")
    admin = ADMIN_ROUTES.read_text(encoding="utf-8")
    require(ssot, "абсолютное равенство", "ssot exact equality clause")
    require(shop, "/order-external", "shop external route")
    require(admin, "/ton/reconcile", "admin ton reconcile route")
    require(
        watcher,
        "if d8(amount_asset) != amt_expected:",
        "exact amount comparison guard",
    )
    require(watcher, "intent_payload", "linkage snapshot guard")
    require(
        pis,
        'STATUS_PENDING = "PENDING"',
        "payment intent pending status symbol",
    )
    print(
        "OK: core SSOT audit anchors are present for "
        "external shop payment flow."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
