"""Strict static OpenAPI/backend/frontend contract gate for EFHC Bot.

Dependency-light guard for cycle 1442. It checks the
checked-in OpenAPI snapshot against backend route decorators,
generated frontend seams and direct frontend apiRequest calls
without importing the runtime app.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3] / "main"
OPENAPI = ROOT / "backend/openapi/openapi.json"
SSOT = ROOT / "docs/SSOT/ssot_pack/SSOT_ROUTES.csv"
FRONTEND = ROOT / "frontend/src"
REPORT = ROOT / (
    "reports/generated/"
    "openapi_strict_contract_gate.json"
)
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}

EXPECTED_SEAM_METHODS = {
    "EXCHANGE_PREVIEW_PATH": "GET",
    "EXCHANGE_CONVERT_PATH": "POST",
    "WITHDRAW_LIST_PATH": "GET",
    "WITHDRAW_REQUEST_PATH": "POST",
    "WITHDRAW_DETAIL_PATH": "GET",
    "WITHDRAW_CANCEL_PATH": "POST",
    "SHOPFRONT_ACCESS_KEY_PATH": "POST",
    "HUB_SHOP_TRUTH_PATH": "GET",
    "SHOPFRONT_PROFILE_PATH": "GET",
    "SHOPFRONT_BOOTSTRAP_PATH": "GET",
    "SHOPFRONT_CATALOG_PATH": "GET",
    "SHOPFRONT_CREATE_INTENT_PATH": "POST",
    "SHOPFRONT_INTENT_STATUS_PATH": "GET",
    "ADMIN_BANK_BALANCE_PATH": "GET",
    "ADMIN_BANK_MINT_PATH": "POST",
    "ADMIN_BANK_BURN_PATH": "POST",
    "ADMIN_WITHDRAWALS_PATH": "GET",
    "ADMIN_WITHDRAW_APPROVE_PATH": "POST",
    "ADMIN_WITHDRAW_REJECT_PATH": "POST",
    "ADMIN_WITHDRAW_OUTCOME_PREVIEW_PATH": "GET",
    "ADMIN_HUB_LINKS_PATH": "GET",
    "ADMIN_HUB_LINK_CREATE_PATH": "POST",
    "ADMIN_HUB_LINK_UPDATE_PATH": "PUT",
    "ADMIN_HUB_LINK_TOGGLE_PATH": "POST",
    "ADMIN_HUB_LINK_REORDER_PATH": "POST",
    "ADMIN_REFERRAL_SUMMARY_PATH": "GET",
}

APIREQUEST_RE = re.compile(
    r"(?:apiRequest|adminApiRequest)(?:<[^>]+>)?\("
    r"\s*([`\"'])(?P<path>.*?)(?<!\\)\1"
    r"\s*,\s*([`\"'])"
    r"(?P<method>GET|POST|PUT|PATCH|DELETE)(?<!\\)\3",
    re.S,
)
CONST_PATH_RE = re.compile(
    r"export\s+const\s+"
    r"(?P<name>[A-Z0-9_]+_PATH)"
    r"\s*=\s*(?:\n\s*)?"
    r"[\"'](?P<path>[^\"']+)[\"']"
)


def _norm(path: str) -> str:
    path = path.strip()
    if not path:
        return "/"
    path = path.split("?", 1)[0]
    if path.startswith("${"):
        return path
    if not path.startswith("/"):
        path = "/" + path
    path = re.sub(r"\$\{[^}]+\}", "{param}", path)
    while "//" in path:
        path = path.replace("//", "/")
    return path


def _without_api(path: str) -> str:
    return path[4:] if path.startswith("/api/") else path


def _slash_variants(path: str) -> set[str]:
    base = _without_api(path)
    variants = {base}
    if base != "/":
        variants.add(base.rstrip("/"))
        variants.add(base.rstrip("/") + "/")
    return variants


def _route_pattern(path: str) -> re.Pattern[str]:
    path = _without_api(path).rstrip("/") or "/"
    body = re.escape(path)
    body = re.sub(r"\\\{[^/]+\\\}", r"[^/]+", body)
    return re.compile("^" + body + "/?$")


def load_openapi_ops() -> set[tuple[str, str]]:
    data = json.loads(OPENAPI.read_text(encoding="utf-8"))
    ops: set[tuple[str, str]] = set()
    for path, methods in data.get("paths", {}).items():
        for method in methods:
            if method.lower() in HTTP_METHODS:
                ops.add((method.upper(), path))
    return ops


def load_ssot_ops() -> set[tuple[str, str]]:
    with SSOT.open(encoding="utf-8", newline="") as fh:
        return {
            (row["method"].upper(), row["path"])
            for row in csv.DictReader(fh)
        }


def load_frontend_constants() -> dict[str, str]:
    constants: dict[str, str] = {}
    for path in sorted(FRONTEND.rglob("*.ts*")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in CONST_PATH_RE.finditer(text):
            constants[match.group("name")] = match.group("path")
    return constants


def load_generated_seam_constants() -> list[dict[str, str]]:
    constants = load_frontend_constants()
    openapi_ops = load_openapi_ops()
    rows: list[dict[str, str]] = []
    for name, path in sorted(constants.items()):
        norm_path = _norm(path)
        if name in EXPECTED_SEAM_METHODS:
            rows.append(
                {
                    "name": name,
                    "method": EXPECTED_SEAM_METHODS[name],
                    "path": norm_path,
                }
            )
            continue
        if (
            not name.startswith("ADMIN_")
            or not norm_path.startswith("/admin")
        ):
            continue
        methods = sorted(
            method
            for method, op_path in openapi_ops
            if _route_pattern(op_path).match(
                norm_path.rstrip("/") or "/"
            )
        )
        for method in methods:
            rows.append(
                {"name": name, "method": method, "path": norm_path}
            )
    return rows


def collect_frontend_calls() -> list[dict[str, str]]:
    constants = load_frontend_constants()
    rows: list[dict[str, str]] = []
    for path in sorted(FRONTEND.rglob("*.ts*")):
        rel = str(path.relative_to(ROOT))
        if rel.startswith("frontend/src/pages/api/"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in APIREQUEST_RE.finditer(text):
            raw_path = match.group("path")
            method = match.group("method")
            resolved = raw_path
            # A trailing computed suffix is query-string state, not route
            # identity (for example `/profile/history${suffix}` where
            # suffix is either "" or `?cursor=...`).  Do not turn it into
            # a fake path parameter during static linkage checks.
            resolved = re.sub(
                r"\$\{(?:suffix|query|queryString)\}$",
                "",
                resolved,
            )
            const_match = re.fullmatch(
                r"\$\{([A-Z0-9_]+_PATH)\}(.*)",
                raw_path,
            )
            if const_match and const_match.group(1) in constants:
                tail = const_match.group(2)
                # Computed suffixes are not route identity.
                # They must not create fake paths.
                if tail.startswith("${"):
                    tail = ""
                resolved = constants[const_match.group(1)] + tail
            rows.append(
                {
                    "method": method,
                    "raw_path": raw_path,
                    "path": _norm(resolved),
                    "file": rel,
                }
            )
    # Cycle 1514: admin pages are intentionally migrated away from
    # direct apiRequest calls into generated adminSeams.  The seam
    # constants are frontend API contract surface and must remain part
    # of this static linkage count/check.
    for seam in load_generated_seam_constants():
        rows.append(
            {
                "method": seam["method"],
                "raw_path": seam["path"],
                "path": seam["path"],
                "file": (
                    "frontend/src/lib/api/generated/adminSeams.ts"
                ),
            }
        )
    return rows


def _op_matches(
    method: str,
    path: str,
    ops: set[tuple[str, str]],
) -> bool:
    if path.startswith("${"):
        # Generic hook/variable path; covered by caller-specific code,
        # not by this static path identity check.
        return True
    candidate = _without_api(path).rstrip("/") or "/"
    for op_method, op_path in ops:
        if op_method != method:
            continue
        if _route_pattern(op_path).match(candidate):
            return True
    return False


def _path_matches_backend(
    method: str,
    frontend_path: str,
    backend_ops: set[tuple[str, str]],
) -> bool:
    if frontend_path.startswith("${"):
        return True
    candidate = _without_api(frontend_path)
    for op_method, op_path in backend_ops:
        if op_method != method:
            continue
        if _route_pattern(op_path).match(candidate.rstrip("/") or "/"):
            return True
    return False


def build_report() -> dict[str, Any]:
    openapi_ops = load_openapi_ops()
    ssot_ops = load_ssot_ops()
    frontend_calls = collect_frontend_calls()
    seam_constants = load_generated_seam_constants()
    openapi_norm = {
        (m, _without_api(p).rstrip("/") or "/")
        for m, p in openapi_ops
    }
    ssot_norm = {
        (m, _without_api(p).rstrip("/") or "/")
        for m, p in ssot_ops
    }

    missing_openapi = sorted(ssot_norm - openapi_norm)
    dead_openapi = sorted(openapi_norm - ssot_norm)
    missing_frontend_backend = [
        call
        for call in frontend_calls
        if not _path_matches_backend(
            call["method"],
            call["path"],
            ssot_ops,
        )
    ]
    missing_frontend_openapi = [
        call
        for call in frontend_calls
        if call not in missing_frontend_backend
        and not _op_matches(call["method"], call["path"], openapi_ops)
    ]
    missing_seam_openapi = [
        seam
        for seam in seam_constants
        if not _op_matches(seam["method"], seam["path"], openapi_ops)
    ]

    admin_unmarked: list[str] = []
    data = json.loads(OPENAPI.read_text(encoding="utf-8"))
    for path, methods in data.get("paths", {}).items():
        if not _without_api(path).startswith("/admin"):
            continue
        for method, op in methods.items():
            if method.lower() not in HTTP_METHODS:
                continue
            if op.get("x-efhc-admin-route") is not True:
                admin_unmarked.append(f"{method.upper()} {path}")

    money_internal_leaks: list[str] = []
    leak_markers = (
        "internal_tx",
        "efhc_mint_burn",
        "efhc_admin.bank_balances",
    )
    openapi_text = OPENAPI.read_text(encoding="utf-8", errors="replace")
    for marker in leak_markers:
        if marker in openapi_text:
            money_internal_leaks.append(marker)

    status = "ok"
    has_drift = any(
        (
            missing_openapi,
            dead_openapi,
            missing_frontend_backend,
            missing_frontend_openapi,
            missing_seam_openapi,
            admin_unmarked,
            money_internal_leaks,
        )
    )
    if has_drift:
        status = "drift"

    return {
        "status": status,
        "cycle": "1442",
        "openapi_operation_count": len(openapi_ops),
        "ssot_operation_count": len(ssot_ops),
        "frontend_api_call_count": len(frontend_calls),
        "generated_seam_constant_count": len(seam_constants),
        "missing_openapi": missing_openapi,
        "dead_openapi": dead_openapi,
        "missing_frontend_backend": missing_frontend_backend,
        "missing_frontend_openapi": missing_frontend_openapi,
        "missing_seam_openapi": missing_seam_openapi,
        "admin_unmarked": admin_unmarked,
        "money_internal_leaks": money_internal_leaks,
        "note": (
            "Static dependency-light gate; live app.openapi proof "
            "is separate."
        ),
    }


def main() -> int:
    report = build_report()
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
