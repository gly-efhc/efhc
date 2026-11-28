from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SHOP_ROUTES = ROOT / "backend/app/routes/shop_routes.py"
HUB_ROUTES = ROOT / "backend/app/routes/hub_routes.py"
WATCHER = ROOT / "backend/app/services/watcher_service.py"
REQUIRED_KEYS = [
    "intent_payload",
    "intent_id",
    "payment_owner_tg_id",
    "payment_intent_kind",
]


def assert_route_snapshot(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for key in REQUIRED_KEYS:
        if key not in text:
            raise RuntimeError(f"missing snapshot key {key} in {path}")


def assert_watcher_checks() -> None:
    text = WATCHER.read_text(encoding="utf-8")
    for needle in [
        "extra_intent_payload",
        "extra_owner_tg",
        "intent payload snapshot mismatch",
        "payment owner mismatch",
    ]:
        if needle not in text:
            raise RuntimeError(f"missing watcher guard {needle}")


def main() -> int:
    assert_route_snapshot(SHOP_ROUTES)
    assert_route_snapshot(HUB_ROUTES)
    assert_watcher_checks()
    print(
        "OK: shop payment linkage snapshot + watcher "
        "guards are present."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
