"""Offline route/table coverage inventory; never accesses GitHub or Neon."""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from demo_backend.schema import REQUIRED_TABLES, REQUIRED_VIEWS
from demo_backend.security import is_external_blocked


def _literal_string(value: ast.AST) -> str | None:
    return value.value if isinstance(value, ast.Constant) and isinstance(value.value, str) else None


def build_route_inventory(root: Path) -> dict:
    path = root / "backend" / "app" / "routes"
    rows = []
    for file in sorted(path.glob("*_routes.py")):
        module = ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
        prefix = ""
        for item in module.body:
            if isinstance(item, ast.Assign) and isinstance(item.value, ast.Call):
                for target in item.targets:
                    if isinstance(target, ast.Name) and target.id == "router":
                        for keyword in item.value.keywords:
                            if keyword.arg == "prefix":
                                prefix = _literal_string(keyword.value) or ""
        for item in ast.walk(module):
            if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in item.decorator_list:
                if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                    continue
                method = decorator.func.attr.upper()
                if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                    continue
                first = _literal_string(decorator.args[0]) if decorator.args else None
                if first is None:
                    continue
                full = "/api" + prefix + first
                full = re.sub(r"/+(?=/)", "", full)
                rows.append({"method": method, "path": full, "source": str(file.relative_to(root)),
                             "handler": item.name, "demo_external_blocked": is_external_blocked(method, full)})
    rows.sort(key=lambda r: (r["path"], r["method"], r["source"]))
    table_names = sorted(f"{schema}.{table}" for schema, names in REQUIRED_TABLES.items() for table in names)
    return {"schema": "efhc.demo.route-inventory", "route_total": len(rows),
            "routes": rows, "neon_required_tables": table_names,
            "neon_required_views": [f"efhc_demo_public.{v}" for v in sorted(REQUIRED_VIEWS)],
            "external_blocked_count": sum(1 for r in rows if r["demo_external_blocked"]) }


def main() -> None:
    from demo_backend.config import backend_root
    root = backend_root().parent
    inventory = build_route_inventory(root)
    print(json.dumps(inventory, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
