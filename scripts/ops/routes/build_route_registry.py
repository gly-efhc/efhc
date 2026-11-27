from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "main"
ROUTES = ROOT / "backend" / "app" / "routes"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _prefix(text: str) -> str:
    match = re.search(r"APIRouter\s*\((.*?)\)", text, re.S)
    if not match:
        return ""
    pattern = r"prefix\s*=\s*['\"]([^'\"]*)['\"]"
    prefix = re.search(pattern, match.group(1))
    return prefix.group(1) if prefix else ""


def _full(prefix: str, path: str) -> str:
    if not path:
        return prefix or "/"
    value = prefix.rstrip("/") + "/" + path.lstrip("/")
    value = value.replace("//", "/")
    return value[:-1] if value != "/" and value.endswith("/") else value


def build() -> dict[str, object]:
    records: list[dict[str, object]] = []
    for file_path in sorted(ROUTES.glob("*.py")):
        text = _read(file_path)
        prefix = _prefix(text)
        pattern = r"@(?:\w+\.)?router\.(get|post|put|patch|delete)"
        pattern += r"\(\s*['\"]([^'\"]*)['\"]"
        for match in re.finditer(pattern, text, re.S):
            rest = text[match.end() : match.end() + 900]
            handler = re.search(r"(?:async\s+def|def)\s+(\w+)", rest)
            records.append(
                {
                    "method": match.group(1).upper(),
                    "path": _full(prefix, match.group(2)),
                    "router_file": str(file_path.relative_to(ROOT)),
                    "handler": handler.group(1) if handler else None,
                }
            )
    keys: defaultdict[str, int] = defaultdict(int)
    for item in records:
        keys[f"{item['method']} {item['path']}"] += 1
    duplicates = {
        key: count for key, count in keys.items() if count > 1
    }
    return {
        "route_count": len(records),
        "methods": dict(Counter(item["method"] for item in records)),
        "duplicate_method_paths": duplicates,
        "routes": records,
    }


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))
