"""Build a static frontend-to-backend route matrix.

The script does not import EFHC runtime dependencies. It parses route
files, router prefixes and frontend string paths to classify caller
coverage without touching frontend sources.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "main"
ROUTE_DIR = ROOT / "backend" / "app" / "routes"
FRONTEND_DIR = ROOT / "frontend"
OUT = ROOT / "reports" / "generated" / "frontend_backend_matrix.json"

PREFIX_RE = re.compile(
    r"router\s*=\s*APIRouter\([^\)]*prefix\s*=\s*[\"']([^\"']*)"
)
ROUTE_RE = re.compile(
    r"@(?P<router>\w+)\.(?P<method>get|post|put|patch|delete)"
    r"\(\s*[\"'](?P<path>[^\"']+)[\"']"
)
API_RE = re.compile(r"[\"'](/[^\"'\s<>`{}]+)[\"']")
API_PREFIX = "/api"


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="ignore")


def norm(path: str) -> str:
    if not path.startswith("/"):
        path = "/" + path
    while "//" in path:
        path = path.replace("//", "/")
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    return path


def route_regex(path: str) -> str:
    body = re.escape(path)
    body = re.sub(r"\\\{[^/]+\\\}", r"[^/]+", body)
    return "^" + body + "$"


def collect_backend() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for file in sorted(ROUTE_DIR.glob("*.py")):
        text = read_text(file)
        prefix_match = PREFIX_RE.search(text)
        prefix = prefix_match.group(1) if prefix_match else ""
        for match in ROUTE_RE.finditer(text):
            local = match.group("path")
            base = norm(prefix + local)
            rows.append(
                {
                    "method": match.group("method").upper(),
                    "path": base,
                    "runtime_path": norm(API_PREFIX + base),
                    "file": str(file.relative_to(ROOT)),
                }
            )
    return rows


def frontend_files() -> list[Path]:
    suffixes = {".ts", ".tsx", ".js", ".jsx"}
    rows: list[Path] = []
    for file in FRONTEND_DIR.rglob("*"):
        rel = str(file.relative_to(ROOT)).lower()
        if "/faq/" in rel or "catalogs.ts" in rel:
            continue
        if file.suffix in suffixes:
            rows.append(file)
    return sorted(rows)


def collect_frontend() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for file in frontend_files():
        text = read_text(file)
        for value in API_RE.findall(text):
            if value.startswith("//"):
                continue
            rows.append(
                {
                    "path": norm(value),
                    "file": str(file.relative_to(ROOT)),
                }
            )
    return rows


def main() -> None:
    backend = collect_backend()
    frontend = collect_frontend()
    patterns = [
        (row, re.compile(route_regex(row["runtime_path"])))
        for row in backend
    ]
    matched_calls: list[dict[str, object]] = []
    unmatched_calls: list[dict[str, str]] = []
    consumers: dict[str, list[dict[str, str]]] = {}
    for call in frontend:
        hits = [row for row, rx in patterns if rx.match(call["path"])]
        if hits:
            matched_calls.append({"call": call, "routes": hits})
            for route in hits:
                key = route["runtime_path"]
                consumers.setdefault(key, []).append(call)
        else:
            unmatched_calls.append(call)

    orphan_routes = [
        row for row in backend if row["runtime_path"] not in consumers
    ]
    data = {
        "backend_routes": backend,
        "frontend_calls": frontend,
        "matched_calls": matched_calls,
        "unmatched_calls": unmatched_calls,
        "orphan_backend_routes": orphan_routes,
        "summary": {
            "backend_routes": len(backend),
            "frontend_calls": len(frontend),
            "matched_calls": len(matched_calls),
            "unmatched_calls": len(unmatched_calls),
            "orphan_backend_routes": len(orphan_routes),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(data["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
