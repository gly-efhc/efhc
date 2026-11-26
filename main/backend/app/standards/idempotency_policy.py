# backend/app/standards/idempotency_policy.py
# ----------------------------------------------------------------------
# Единый классификатор политики идемпотентности по endpoint path.
# SSOT: ops/canon_rules.yaml (idempotency.*)
# ----------------------------------------------------------------------

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

ClassName = Literal["MUST", "SHOULD", "EXTERNAL", "NONE"]


@dataclass(frozen=True)
class IdempotencyPolicy:
    dependency: str
    must: list[re.Pattern[str]]
    external: list[re.Pattern[str]]
    should: list[re.Pattern[str]]


def _repo_root() -> str:
    parts = [os.path.dirname(__file__), "..", "..", ".."]
    return os.path.abspath(os.path.join(*parts))


@lru_cache(maxsize=1)
def load_policy() -> IdempotencyPolicy:
    """Загружает policy из SSOT.
    Компилирует must/external/should regex."""
    rules_path = os.path.join(_repo_root(), "ops", "canon_rules.yaml")

    import yaml  # type: ignore

    with open(rules_path, encoding="utf-8") as f:
        rules = yaml.safe_load(f) or {}

    idem = rules.get("idempotency") or {}
    dep = str(idem.get("dependency") or "require_idempotency_key")

    def _compile(lst: object) -> list[re.Pattern[str]]:
        out: list[re.Pattern[str]] = []
        if not isinstance(lst, list):
            return out
        for p in lst:
            out.append(re.compile(str(p)))
        return out

    return IdempotencyPolicy(
        dependency=dep,
        must=_compile(idem.get("must__path__patterns")),
        external=_compile(idem.get("external_event_id_paths")),
        should=_compile(idem.get("should__path__patterns")),
    )


def classify_path(path: str) -> ClassName:
    """Классифицирует endpoint path по SSOT policy."""
    p = "/" + str(path).lstrip("/")
    pol = load_policy()

    if any(rx.search(p) for rx in pol.external):
        return "EXTERNAL"
    if any(rx.search(p) for rx in pol.must):
        return "MUST"
    if any(rx.search(p) for rx in pol.should):
        return "SHOULD"
    return "NONE"
