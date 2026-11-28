from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TESTS = ROOT / "tests"
KEYWORDS = [
    "withdraw",
    "deposit",
    "exchange",
    "panel",
    "shop",
    "payment",
    "wallet",
    "admin",
    "user",
    "task",
    "ads",
]


def build() -> dict[str, object]:
    files = sorted(TESTS.rglob("*.py"))
    result: dict[str, list[str]] = {}
    for keyword in KEYWORDS:
        matches: list[str] = []
        for file_path in files:
            rel = str(file_path.relative_to(ROOT))
            text = file_path.read_text(
                encoding="utf-8",
                errors="replace",
            )
            if keyword in rel.lower() or keyword in text.lower():
                matches.append(rel)
        result[keyword] = matches[:30]
    return {
        "test_files_count": len(files),
        "keywords": KEYWORDS,
        "test_map": result,
        "boundary": "static map is not final contract coverage",
    }


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))
