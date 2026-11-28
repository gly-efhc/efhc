"""Rebuild EFHC checked-in OpenAPI snapshot from backend route source.

This script is dependency-light. It does not import FastAPI
or SQLAlchemy runtime. It parses backend route decorators
and writes route SSOT plus the checked-in OpenAPI snapshot
used by architecture guards. Live FastAPI export remains a
separate proof step when runtime dependencies are installed.
"""

from __future__ import annotations

import ast
import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
ROUTE_DIR = ROOT / "backend/app/routes"
SSOT = ROOT / "docs/SSOT/ssot_pack/SSOT_ROUTES.csv"
SSOT_NUMBERED = ROOT / "docs/SSOT/ssot_pack/SSOT_ROUTES_NUMBERED.csv"
INVENTORY = ROOT / "docs/SSOT/ssot_pack/SSOT_ROUTE_INVENTORY_FREEZE.csv"
OPENAPI = ROOT / "backend/openapi/openapi.json"
MANIFEST = ROOT / "backend/openapi/openapi_manifest.json"
REPORT = ROOT / (
    "reports/generated/openapi_contract_snapshot.json"
)
METHODS = {"get", "post", "put", "patch", "delete"}
INTERNAL_PREFIXES = ("/cron", "/tg")


def _const_str(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _const_bool(node: ast.AST | None) -> bool | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, bool):
        return node.value
    return None


def _call_kw(call: ast.Call, name: str) -> ast.AST | None:
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


def _router_prefix_and_tags(tree: ast.Module) -> tuple[str, str]:
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        has_router_target = any(
            isinstance(target, ast.Name) and target.id == "router"
            for target in node.targets
        )
        if not has_router_target:
            continue
        if not isinstance(node.value, ast.Call):
            continue
        func = node.value.func
        if not (
            isinstance(func, ast.Name) and func.id == "APIRouter"
            or (
                isinstance(func, ast.Attribute)
                and func.attr == "APIRouter"
            )
        ):
            continue
        prefix = _const_str(_call_kw(node.value, "prefix")) or ""
        tags_node = _call_kw(node.value, "tags")
        tag = "api"
        if isinstance(tags_node, ast.List) and tags_node.elts:
            tag = _const_str(tags_node.elts[0]) or tag
        return prefix, tag
    return "", "api"


def _join(prefix: str, local: str) -> str:
    if not local:
        path = prefix or "/"
    elif local == "/":
        path = prefix.rstrip("/") + "/"
    else:
        path = prefix.rstrip("/") + "/" + local.lstrip("/")
    while "//" in path:
        path = path.replace("//", "/")
    return path or "/"


def _role(path: str, tag: str) -> str:
    if path.startswith("/admin") or tag.startswith("admin"):
        return "admin"
    if path.startswith("/health") or path.startswith(INTERNAL_PREFIXES):
        return "system"
    return "user"


def _operation_id(handler: str, method: str, path: str) -> str:
    if handler:
        return handler
    suffix = (
        path.strip("/")
        .replace("/", "_")
        .replace("{", "")
        .replace("}", "")
    )
    return f"{method.lower()}_{suffix or 'root'}"


def collect_routes() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for file_path in sorted(ROUTE_DIR.glob("*.py")):
        if file_path.name == "__init__.py":
            continue
        text = file_path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(text)
        prefix, tag = _router_prefix_and_tags(tree)
        module = file_path.stem
        for node in ast.walk(tree):
            if not isinstance(
                node,
                (ast.FunctionDef, ast.AsyncFunctionDef),
            ):
                continue
            for dec in node.decorator_list:
                if not isinstance(dec, ast.Call):
                    continue
                func = dec.func
                if not isinstance(func, ast.Attribute):
                    continue
                method = func.attr.lower()
                if method not in METHODS:
                    continue
                local = _const_str(dec.args[0]) if dec.args else None
                if local is None:
                    continue
                include = _const_bool(
                    _call_kw(dec, "include_in_schema")
                )
                if include is False:
                    continue
                path = _join(prefix, local)
                if path.startswith(INTERNAL_PREFIXES):
                    continue
                rows.append(
                    {
                        "method": method.upper(),
                        "path": path,
                        "handler": node.name,
                        "file": str(file_path.relative_to(ROOT)),
                        "line": str(
                            getattr(dec, "lineno", node.lineno)
                        ),
                        "router_module": module,
                        "role": _role(path, tag),
                        "tags_prefix": tag,
                    }
                )
    # `backend/app/main.py` содержит отдельные app.* routes вне APIRouter.
    main_path = ROOT / "backend/app/main.py"
    main_text = main_path.read_text(encoding="utf-8", errors="replace")
    main_tree = ast.parse(main_text)
    for node in ast.walk(main_tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call):
                continue
            func = dec.func
            if not (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "app"
            ):
                continue
            method = func.attr.lower()
            if method not in METHODS:
                continue
            local = _const_str(dec.args[0]) if dec.args else None
            if local is None:
                continue
            include = _const_bool(_call_kw(dec, "include_in_schema"))
            if include is False:
                continue
            tags_node = _call_kw(dec, "tags")
            tag = "api"
            if isinstance(tags_node, ast.List) and tags_node.elts:
                tag = _const_str(tags_node.elts[0]) or tag
            rows.append(
                {
                    "method": method.upper(),
                    "path": local or "/",
                    "handler": node.name,
                    "file": "backend/app/main.py",
                    "line": str(getattr(dec, "lineno", node.lineno)),
                    "router_module": "main",
                    "role": _role(local or "/", tag),
                    "tags_prefix": tag,
                }
            )

    rows.sort(
        key=lambda r: (
            r["path"],
            r["method"],
            r["file"],
            r["handler"],
        )
    )
    return rows


def write_csv(rows: list[dict[str, str]]) -> None:
    fields = [
        "method",
        "path",
        "handler",
        "file",
        "line",
        "router_module",
        "role",
        "tags_prefix",
    ]
    SSOT.parent.mkdir(parents=True, exist_ok=True)
    with SSOT.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    with SSOT_NUMBERED.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["n", *fields])
        writer.writeheader()
        for i, row in enumerate(rows, 1):
            writer.writerow({"n": i, **row})
    with INVENTORY.open("w", encoding="utf-8", newline="") as fh:
        fields2 = [
            "method",
            "path",
            "file",
            "router_module",
            "prefix",
            "service_refs",
            "auth_type",
        ]
        writer = csv.DictWriter(fh, fieldnames=fields2)
        writer.writeheader()
        for row in rows:
            if row["role"] == "admin":
                auth = "ADMIN_REQUIRED"
            elif row["role"] == "system":
                auth = "SYSTEM"
            else:
                auth = "USER_OR_PUBLIC"
            writer.writerow(
                {
                    "method": row["method"],
                    "path": row["path"],
                    "file": row["file"],
                    "router_module": row["router_module"],
                    "prefix": "ROOT",
                    "service_refs": "ROUTE_ONLY_OR_INLINE",
                    "auth_type": auth,
                }
            )


def _load_components() -> dict[str, Any]:
    if not OPENAPI.exists():
        return {"schemas": {}}
    try:
        raw = OPENAPI.read_text(encoding="utf-8")
        return json.loads(raw).get("components", {"schemas": {}})
    except Exception:
        return {"schemas": {}}


def _path_param_names(path: str) -> list[str]:
    out: list[str] = []
    start = 0
    while True:
        left = path.find("{", start)
        if left < 0:
            break
        right = path.find("}", left)
        if right < 0:
            break
        out.append(path[left + 1 : right])
        start = right + 1
    return out


def _operation(row: dict[str, str]) -> dict[str, Any]:
    params = [
        {
            "name": name,
            "in": "path",
            "required": True,
            "schema": {"type": "string"},
        }
        for name in _path_param_names(row["path"])
    ]
    op: dict[str, Any] = {
        "tags": [row["tags_prefix"]],
        "summary": row["handler"].replace(
            "_",
            " ",
        ).strip().capitalize(),
        "operationId": _operation_id(
            row["handler"],
            row["method"],
            row["path"],
        ),
        "responses": {"200": {"description": "OK"}},
        "x-efhc-ssot-handler": row["handler"],
        "x-efhc-ssot-file": row["file"],
        "x-efhc-ssot-line": row["line"],
        "x-efhc-generated-from": "backend route source static scan",
    }
    if params:
        op["parameters"] = params
    if row["role"] == "admin":
        op["x-efhc-admin-route"] = True
    money_prefixes = (
        "/admin/bank",
        "/withdraw",
        "/exchange",
        "/deposit",
        "/payment-intents",
        "/shopfront",
    )
    if row["path"].startswith(money_prefixes):
        op["x-efhc-money-surface"] = True
    return op


def write_openapi(rows: list[dict[str, str]]) -> None:
    paths: dict[str, dict[str, Any]] = {}
    for row in rows:
        path_ops = paths.setdefault(row["path"], {})
        path_ops[row["method"].lower()] = _operation(row)
    schema = {
        "openapi": "3.0.2",
        "info": {
            "title": "EFHC Bot API",
            "version": "170.18",
            "description": (
                "Checked-in OpenAPI snapshot rebuilt from backend "
                "route source during step 1442. API_PREFIX is "
                "applied by the runtime/API client layer; this "
                "snapshot stores canonical router-local paths."
            ),
            "x-efhc-openapi-mode": (
                "backend-route-source-derived-snapshot"
            ),
            "x-efhc-generated-at": datetime.now(UTC).isoformat(),
            "x-efhc-step": "1442",
        },
        "paths": paths,
        "components": _load_components(),
    }
    OPENAPI.parent.mkdir(parents=True, exist_ok=True)
    OPENAPI.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": "backend-route-source-derived-snapshot",
        "source": "backend/app/routes/*.py static route decorators",
        "ssot": str(SSOT.relative_to(ROOT)),
        "path_count": len(paths),
        "operation_count": sum(len(v) for v in paths.values()),
        "schema_count": len(
            schema.get("components", {}).get("schemas", {})
        ),
        "runtime_live_export": "not_claimed_in_this_environment",
        "note": (
            "Dependency-free static rebuild. Live FastAPI "
            "app.openapi() proof requires runtime dependencies "
            "and remains a separate CI/live gate."
        ),
    }
    MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    report = {"rows": rows, **manifest}
    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    rows = collect_routes()
    write_csv(rows)
    write_openapi(rows)
    print(
        json.dumps(
            {
                "routes": len(rows),
                "paths": len({r["path"] for r in rows}),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
