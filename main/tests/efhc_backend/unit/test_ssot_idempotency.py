import re
from pathlib import Path

import yaml


def test_must_idempotency_paths_have_depends_marker():
    """SSOT: денежно-опасные пути (MUST) обязаны иметь
    Depends(require_idempotency_key).

    Static-тест: для каждого MUST пути ищем декоратор с этим путём и
    проверяем, что в окне рядом присутствует require_idempotency_key.
    """

    repo = Path(__file__).resolve().parents[3]
    raw = (repo / "ops" / "canon_rules.yaml").read_text("utf-8")
    rules = yaml.safe_load(raw)
    patterns: list[re.Pattern[str]] = []
    for pat in rules["idempotency"]["must__path__patterns"]:
        patterns.append(re.compile(pat))

    route_files = list(
        (repo / "backend" / "app" / "routes").glob("**/*.py")
    )

    offenders = []
    for f in route_files:
        txt = f.read_text("utf-8")
        lines = txt.splitlines()
        for i, line in enumerate(lines):
            if "@router." not in line:
                continue
            # попытка достать путь из декоратора
            m = re.search(r"\(\s*\"([^\"]+)\"", line)
            if not m:
                m = re.search(r"\(\s * '([^']+)'", line)
            if not m:
                continue
            path = m.group(1)
            # Нас интересуют только /api/... ручки.
            # В SSOT пути без /api.
            # префикса,
            # поэтому нормализуем.
            norm = path
            if norm.startswith("/api"):
                norm = norm[len("/api") :]
            for pat in patterns:
                if pat.match(norm):
                    end = min(i + 80, len(lines))
                    window = "\n".join(lines[i:end])
                    if "require_idempotency_key" not in window:
                        offenders.append(
                            (
                                str(f.relative_to(repo)),
                                norm,
                                pat.pattern,
                            )
                        )

    assert not offenders, (
        "Missing require_idempotency_key near decorators: "
        f"{offenders}"
    )
