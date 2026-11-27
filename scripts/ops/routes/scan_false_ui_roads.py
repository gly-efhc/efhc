from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "main"
FRONTEND = ROOT / "frontend"


def build() -> dict[str, object]:
    paths: list[dict[str, str]] = []
    for ext in ("*.ts", "*.tsx"):
        for file_path in sorted(FRONTEND.rglob(ext)):
            if "faq" in str(file_path).lower():
                continue
            text = file_path.read_text(
                encoding="utf-8",
                errors="replace",
            )
            pattern = r"['\"]((?:/api)?/[A-Za-z0-9_{}:$?&=./-]+)['\"]"
            for match in re.finditer(pattern, text):
                paths.append(
                    {
                        "file": str(file_path.relative_to(ROOT)),
                        "path": match.group(1),
                    }
                )
    return {
        "frontend__path__strings": len(paths),
        "paths": paths,
        "frontend_modified": False,
        "faq_modified": False,
        "boundary": "navigation strings are not backend route proof",
    }


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))
