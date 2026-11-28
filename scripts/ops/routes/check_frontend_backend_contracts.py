"""Check generated frontend seam paths against backend routes."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
ROUTES = ROOT / "backend" / "app" / "routes"
OUT = ROOT / "reports" / "generated" / "frontend_backend_contracts.json"
SEAM_DIR = ROOT / "frontend" / "src" / "lib" / "api" / "generated"
SEAM_FILES = [
    SEAM_DIR / "economicUserSeams.ts",
    SEAM_DIR / "adminSeams.ts",
]
EXPECTED_METHODS = {
    "EXCHANGE_PREVIEW": "GET",
    "EXCHANGE_CONVERT": "POST",
    "WITHDRAW_LIST": "GET",
    "WITHDRAW_REQUEST": "POST",
    "WITHDRAW_DETAIL": "GET",
    "WITHDRAW_CANCEL": "POST",
    "SHOPFRONT_ACCESS_KEY": "POST",
    "HUB_SHOP_TRUTH": "GET",
    "SHOPFRONT_PROFILE": "GET",
    "SHOPFRONT_BOOTSTRAP": "GET",
    "SHOPFRONT_CATALOG": "GET",
    "SHOPFRONT_CREATE_INTENT": "POST",
    "SHOPFRONT_INTENT_STATUS": "GET",
    "ADMIN_BANK_BALANCE": "GET",
    "ADMIN_BANK_MINT": "POST",
    "ADMIN_BANK_BURN": "POST",
    "ADMIN_WITHDRAWALS": "GET",
    "ADMIN_WITHDRAW_APPROVE": "POST",
    "ADMIN_WITHDRAW_REJECT": "POST",
    "ADMIN_WITHDRAW_OUTCOME_PREVIEW": "GET",
    "ADMIN_REFERRAL_SUMMARY": "GET",
}
PREFIX_RE = re.compile(r"router\s*=\s*APIRouter\((.*?)\)", re.S)
ROUTE_RE = re.compile(
    r"@router\.(get|post|put|patch|delete)" r"\(\s*[\"']([^\"']*)"
)
CONST_RE = re.compile(
    r"export const ([A-Z0-9_]+)_PATH\s*=\s*"
    r"(?:\n\s*)?[\"']([^\"']+)[\"']"
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _norm(path: str) -> str:
    if not path.startswith("/"):
        path = "/" + path
    while "//" in path:
        path = path.replace("//", "/")
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    return path


def _prefix(text: str) -> str:
    match = PREFIX_RE.search(text)
    if not match:
        return ""
    value = re.search(
        r"prefix\s*=\s*[\"']([^\"']*)",
        match.group(1),
    )
    return value.group(1) if value else ""


def collect_routes() -> dict[str, list[dict[str, str]]]:
    routes: dict[str, list[dict[str, str]]] = {}
    for file_path in sorted(ROUTES.glob("*.py")):
        text = _text(file_path)
        prefix = _prefix(text)
        for method, local in ROUTE_RE.findall(text):
            full = _norm(prefix.rstrip("/") + "/" + local.lstrip("/"))
            row = {
                "method": method.upper(),
                "path": full,
                "file": str(file_path.relative_to(ROOT)),
            }
            routes.setdefault(full, []).append(row)
    return routes


def collect_seams() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for file_path in SEAM_FILES:
        text = _text(file_path)
        for name, path in CONST_RE.findall(text):
            method = EXPECTED_METHODS.get(name)
            if method:
                rows.append(
                    {
                        "name": name,
                        "path": _norm(path),
                        "method": method,
                        "file": str(file_path.relative_to(ROOT)),
                    }
                )
    return rows


def build() -> dict[str, Any]:
    routes = collect_routes()
    seams = collect_seams()
    checks: list[dict[str, Any]] = []
    missing: list[dict[str, str]] = []
    method_drift: list[dict[str, Any]] = []
    for seam in seams:
        candidates = routes.get(seam["path"], [])
        methods = sorted({row["method"] for row in candidates})
        ok = seam["method"] in methods
        row = {"seam": seam, "backend_methods": methods, "ok": ok}
        checks.append(row)
        if not candidates:
            missing.append(seam)
        elif not ok:
            method_drift.append(row)
    return {
        "status": "ok" if not missing and not method_drift else "drift",
        "seam_count": len(seams),
        "missing_count": len(missing),
        "method_drift_count": len(method_drift),
        "missing": missing,
        "method_drift": method_drift,
        "checks": checks,
        "boundary": "static guard; runtime OpenAPI is separate",
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
