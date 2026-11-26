from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROUTE = ROOT / "backend/app/routes/withdraw_routes.py"
SERVICE = ROOT / "backend/app/services/withdraw_service.py"


def _must(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(f"missing:{label}")


def _must_not(text: str, needle: str, label: str) -> None:
    if needle in text:
        raise SystemExit(f"forbidden:{label}")


def main() -> None:
    route_text = ROUTE.read_text(encoding="utf-8")
    svc_text = SERVICE.read_text(encoding="utf-8")

    _must(route_text, '"/request"', "withdraw_request_route")
    _must(
        route_text,
        "dto = await request_withdraw(",
        "route_calls_service",
    )
    _must(svc_text, "status, idempotency_key)", "insert_columns")
    _must(svc_text, '"st": WITHDRAW_REQ_PENDING', "pending_insert")
    _must(svc_text, 'reason="withdraw_hold"', "hold_reason")
    _must(svc_text, "hold_done = TRUE", "hold_done_update")
    _must_not(svc_text, "tonconnect", "no_tonconnect_calls")
    _must_not(svc_text, "sendTransaction", "no_front_blockchain_calls")
    print("ok: withdraw blitz compatibility audit passed")


if __name__ == "__main__":
    main()
