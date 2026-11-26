from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SSOT_ROUTES = ROOT / "docs/SSOT/ssot_pack/SSOT_ROUTES.csv"
OPENAPI = ROOT / "backend/openapi/openapi.json"
FRONTEND_FILES = [
    ROOT / "frontend/src/features/shop/ShopEntryPage.tsx",
    ROOT / "frontend/src/features/profile/WebProfilePage.tsx",
    ROOT / "frontend/src/features/browser-shop/BrowserShopPage.tsx",
    ROOT / "frontend/src/lib/api/generated/economicUserSeams.ts",
]
REQUIRED = [
    "/shopfront/access-key",
    "/shopfront/profile",
    "/shopfront/bootstrap",
    "/shopfront/catalog",
    "/shopfront/create-intent",
    "/shopfront/intent-status",
]


def read_ssot_paths() -> set[str]:
    text = SSOT_ROUTES.read_text(encoding="utf-8")
    return {p for p in REQUIRED if p in text}


def read_openapi_paths() -> set[str]:
    spec = json.loads(OPENAPI.read_text(encoding="utf-8"))
    norm = set()
    for path in spec.get("paths", {}):
        norm.add(path[4:] if path.startswith("/api/") else path)
    return {p for p in REQUIRED if p in norm}


def read_frontend_paths() -> set[str]:
    found: set[str] = set()
    for file in FRONTEND_FILES:
        text = file.read_text(encoding="utf-8")
        for path in REQUIRED:
            if path in text:
                found.add(path)
    return found


def main() -> int:
    ssot = read_ssot_paths()
    openapi = read_openapi_paths()
    frontend = read_frontend_paths()
    missing = []
    for path in REQUIRED:
        gaps = []
        if path not in ssot:
            gaps.append("SSOT_ROUTES")
        if path not in openapi:
            gaps.append("openapi")
        if path not in frontend:
            gaps.append("frontend_used_paths")
        if gaps:
            missing.append((path, gaps))
    print("SHOP PAYMENT PATH COVERAGE AUDIT")
    for path in REQUIRED:
        print(
            f"- {path}: ssot={'yes' if path in ssot else 'no'}, "
            f"openapi={'yes' if path in openapi else 'no'}, "
            f"frontend={'yes' if path in frontend else 'no'}"
        )
    if missing:
        print("MISSING:")
        for path, gaps in missing:
            print(f"  {path}: {', '.join(gaps)}")
        return 1
    print(
        "OK: all required shop payment paths are covered by "
        "SSOT, openapi and frontend used paths."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
