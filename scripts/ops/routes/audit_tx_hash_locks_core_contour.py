from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MODEL = ROOT / "backend/app/models/shop_payment_tx_hash_lock_models.py"
LOCK_SERVICE = (
    ROOT / "backend/app/services/shop_payment_tx_hash_lock_service.py"
)
RECON_SERVICE = (
    ROOT / "backend/app/services/payment_reconciliation_service.py"
)
WATCHER = ROOT / "backend/app/services/watcher_service.py"
INIT_MIGRATION = (
    ROOT
    / "backend/migrations/versions/0001_initial_release_schema.py"
)


def require(path: Path, needle: str) -> None:
    text = path.read_text(encoding="utf-8")
    if needle not in text:
        raise RuntimeError(f"missing {needle} in {path}")


def main() -> int:
    require(MODEL, "class TxHashLock")
    require(MODEL, "uq_tx_hash_locks_tx_hash")
    require(MODEL, "trusted_operation_at")
    require(MODEL, "server_first_seen_at")
    require(LOCK_SERVICE, "require_external_financial_execution")
    require(LOCK_SERVICE, "acquire_tx_hash_lock")
    require(RECON_SERVICE, "confirm_payment_intent")
    require(RECON_SERVICE, "acquire_tx_hash_lock")
    require(WATCHER, "payment_reconciliation_service")
    require(
        WATCHER,
        "compatibility/dependency seam над canonical reconciliation",
    )
    require(INIT_MIGRATION, "revision = \"0001\"")
    versions = sorted(
        path.name
        for path in INIT_MIGRATION.parent.glob("*.py")
    )
    if versions != ["0001_initial_release_schema.py"]:
        raise RuntimeError(f"unexpected migration set: {versions}")
    print(
        "OK: core-side tx_hash_locks contour and shared "
        "reconciliation service are present; stray 0002 "
        "migration is absent."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
