"""Canon guard: project must not contain legacy words.

This is a FIRST-LAUNCH canonical rename to 'ranks' everywhere.
"""

from __future__ import annotations

import re
from pathlib import Path

FORBIDDEN = ("ra" + "ting", "rei" + "ting")

CONTROL_PLANE_EVIDENCE_PATHS = {
    "ARCHITECTURAL_LOCKS.md",
    "CONTINUE_IN_NEW_CHAT.md",
    "KERNEL.md",
    "README.md",
    "README_RELEASE.md",
    "START_HERE.md",
    "docs/NORM/ARCHITECTURAL_LOCKS.md",
    "docs/SSOT/CURRENT_RELEASE_STATE.md",
    "docs/SSOT/EFHC_OPERATOR_KERNEL_SSOT.md",
}


def _is_control_plane_evidence_path(path: Path, repo: Path) -> bool:
    return path.relative_to(repo).as_posix() in CONTROL_PLANE_EVIDENCE_PATHS


def _is_faq_ssot_path(path: Path, repo: Path) -> bool:
    rel = path.relative_to(repo).as_posix()
    return rel.startswith("docs/SSOT/faq_ssot/")


def _is_generated_faq_catalog(path: Path, repo: Path) -> bool:
    rel = path.relative_to(repo).as_posix()
    return rel == "frontend/src/data/faq/catalogs.ts"


def _is_historical_document_path(path: Path, repo: Path) -> bool:
    rel = path.relative_to(repo).as_posix()
    return rel.startswith(
        (
            "docs/audits/",
            "docs/cycles/",
            "docs/chats/",
            "reports/",
            "docs/history/",
        )
    )


def test_no_legacy_words_present() -> None:
    repo = Path(__file__).resolve().parents[3]  # repo root
    # skip binary / build dirs
    skip_dirs = {
        "песочница",
        ".git",
        ".venv",
        "audit",
        "reports",
        "reports_archived_2026_04_08",
        "ORIGINAL_SOURCES",
        "CHAT_BRANCHES",
        "CHATS",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        "artifacts",
        "history",
        "logs",
    }

    offenders: list[str] = []
    for p in repo.rglob("*"):
        if p.is_dir():
            continue
        if p.name == "EFHC_ERRORS_REGISTRY_AND_GUARDS_TEAM.md":
            continue
        if p.name.startswith("logs_"):
            continue
        rel = p.relative_to(repo).as_posix()
        if rel in {
            "docs/frontend/FRONTEND_PWA_INSTALL_POLICY.md",
            "docs/frontend/FRONTEND_FUNCTION_RECOVERY_CANON.md",
        }:
            continue
        if _is_historical_document_path(p, repo):
            continue
        if _is_control_plane_evidence_path(p, repo):
            continue
        if _is_faq_ssot_path(p, repo):
            continue
        if _is_generated_faq_catalog(p, repo):
            continue
        if any(part in skip_dirs for part in p.parts):
            continue
        bin_exts = {
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".webp",
            ".ico",
            ".pdf",
            ".zip",
            ".woff",
            ".woff2",
            ".ttf",
        }
        if p.suffix.lower() in bin_exts:
            continue
        try:
            data = p.read_text(encoding="utf-8")
        except Exception:
            continue
        patterns = [re.compile(rf"(?<![A-Za-z]){re.escape(word)}(?![A-Za-z])", re.IGNORECASE) for word in FORBIDDEN]
        if any(pattern.search(data) for pattern in patterns):
            offenders.append(str(p.relative_to(repo)))

    assert offenders == [], "Legacy words found: " + ", ".join(
        offenders
    )
