"""Guard for panels-summary self-route canon."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "main"
ROUTE_FILE = ROOT / "backend/app/routes/user_routes.py"
OUT = ROOT / "reports/generated/panels_summary_canon.json"
FRONTEND = ROOT / "frontend/src"
API_CONTRACTS = ROOT / "docs/NORM/API_CONTRACTS.md"
CANON = '"/me/panels-summary"'
LEGACY = '"/{tg_id}/panels-summary"'
LEGACY_LITERAL = "/user/{tg_id}/panels-summary"
CANON_LITERAL = "/user/me/panels-summary"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _frontend_hits(value: str) -> list[str]:
    hits: list[str] = []
    for path in sorted(FRONTEND.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix not in {".ts", ".tsx", ".js", ".jsx"}:
            continue
        if value in _read(path):
            hits.append(str(path.relative_to(ROOT)))
    return hits


def build() -> dict[str, object]:
    text = _read(ROUTE_FILE)
    has_canon = CANON in text
    has_legacy = LEGACY in text
    uses_auth = "Depends(get_nonfinancial_read_owner)" in text
    service_call = (
        "svc_panels_summary(db, global_id=owner.global_id)" in text
    )
    legacy_frontend_hits = _frontend_hits(LEGACY_LITERAL)
    canon_frontend_hits = _frontend_hits(CANON_LITERAL)
    api_contracts = _read(API_CONTRACTS)
    legacy_heading = f"### GET {LEGACY_LITERAL}"
    legacy_contract_section = legacy_heading in api_contracts
    ok = all(
        [
            has_canon,
            not has_legacy,
            uses_auth,
            service_call,
            not legacy_frontend_hits,
            not legacy_contract_section,
        ]
    )
    return {
        "status": "ok" if ok else "drift",
        "canonical_route": CANON_LITERAL,
        "removed_alias": LEGACY_LITERAL,
        "has_canonical_route": has_canon,
        "has_legacy_route": has_legacy,
        "uses_auth_dependency": uses_auth,
        "uses_provider_neutral_service_call": service_call,
        "canonical_frontend_hits": canon_frontend_hits,
        "legacy_frontend_hits": legacy_frontend_hits,
        "legacy_contract_section": legacy_contract_section,
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
