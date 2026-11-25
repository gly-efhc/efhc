import fnmatch
import re
from pathlib import Path

import yaml


def _matches_any(rel: str, globs_list):
    rel = rel.replace("\\", "/")
    for g in globs_list:
        pat = g.replace("\\", "/")
        if fnmatch.fnmatch(rel, pat):
            return True
    return False


def test_public_layer_forbids_tg_id():
    """SSOT: публичный слой не содержит global_id (только TG - ID).

    Проверяем routes + schemas, исключая admin контур по allow-globs.
    """

    repo = Path(__file__).resolve().parents[3]
    raw = (repo / "ops" / "canon_rules.yaml").read_text("utf-8")
    rules = yaml.safe_load(raw)

    forbidden = set(rules.get("public_api_forbidden_fields") or [])
    allowed = list(rules.get("public_api_allowed_globs") or [])

    targets = []
    targets += list(
        (repo / "backend" / "app" / "routes").glob("**/*.py")
    )
    targets += list(
        (repo / "backend" / "app" / "schemas").glob("**/*.py")
    )

    offenders = []
    for f in targets:
        rel = str(f.relative_to(repo)).replace("\\", "/")
        if _matches_any(rel, allowed):
            continue
        txt = f.read_text("utf-8")
        for word in forbidden:
            if re.search(rf"\b{re.escape(word)}\b", txt):
                offenders.append(rel)
                break

    assert not offenders, (
        "Forbidden fields found in public layer: " f"{offenders}"
    )
