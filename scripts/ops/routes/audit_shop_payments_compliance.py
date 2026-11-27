from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "main"
WATCHER = ROOT / "backend/app/services/watcher_service.py"
JETTON = ROOT / "backend/app/services/jetton_parsing_service.py"
RECON = ROOT / "backend/app/services/payment_reconciliation_service.py"
SSOT = ROOT / "docs/SSOT/SHOP_PAYMENTS_EXTERNAL_FLOW_SSOT.md"
TABLES = ROOT / "docs/SSOT/ssot_pack/SSOT_TABLES_ORM.csv"
TABLES_MIG = ROOT / "docs/SSOT/ssot_pack/SSOT_TABLES_MIGRATIONS.csv"
ROUTE_MAP = ROOT / "docs/SSOT/ssot_pack/SSOT_ROUTE_TABLE_MAP.csv"
ROUTES_TABLES = (
    ROOT / "docs/SSOT/ssot_pack/SSOT_ROUTES_TABLES_MIGRATIONS.csv"
)
ADMIN_ROUTES = ROOT / "backend/app/routes/admin_routes.py"


def require(path: Path, needle: str) -> None:
    text = path.read_text(encoding="utf-8")
    if needle not in text:
        raise RuntimeError(f"missing {needle} in {path}")


def main() -> int:
    require(SSOT, "Запрет анонимных платежей")
    require(JETTON, "parse_payment_intent_transport_from_tx")
    require(JETTON, "USDT_JETTON_MASTER_ADDRESS")
    require(WATCHER, "parse_payment_intent_transport_from_tx")
    require(RECON, "acquire_tx_hash_lock")
    require(TABLES, "tx_hash_locks")
    require(TABLES_MIG, "tx_hash_locks")
    require(ROUTE_MAP, "/admin/ton/reconcile")
    require(ROUTE_MAP, "tx_hash_locks")
    require(ROUTES_TABLES, "/shop/order-external")
    require(ROUTES_TABLES, "tx_hash_locks")
    require(ADMIN_ROUTES, "def ton_reconcile")
    print(
        "OK: shop payment SSOT compliance surface "
        "809-810 is synchronized."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
