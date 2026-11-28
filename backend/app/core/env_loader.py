# backend/app/core/env_loader.py
# =====================================================================
# Назначение кода:
# Канонический загрузчик .env файлов для EFHC-Bot.
# Нужен, чтобы локальные/CI/Neon/Prod конфигурации подхватывались
# автоматически,
# а разработчику было достаточно заполнить .env.* файл.
#
# Канон/инварианты:
# • Секреты не печатаем в логах.
# • ENV переменные (в окружении) имеют приоритет над .env файлами.
# • Можно указать явный файл через ENV_FILE.
#
# ИИ-защита/самовосстановление:
# • Если .env файлов нет — это не ошибка (Vercel/Render дают ENV).
# • Никаких исключений наружу: загрузчик best-effort.
# =====================================================================

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


def _repo_root() -> Path:
    """Определяет корень репозитория.

    env_loader.py лежит в backend/app/core → определяем корень исходника.
    """
    return Path(__file__).resolve().parents[3]


def _candidate_files(env: str) -> list[Path]:
    """Список кандидатов .env файлов в каноническом порядке загрузки."""
    root = _repo_root()
    base = [root / ".env"]

    mapping = {
        "local": root / ".env.local",
        "prod": root / ".env.prod",
        "production": root / ".env.prod",
        "ci": root / ".env.ci",
        "neon": root / ".env.neon",
    }

    files: list[Path] = []
    files.extend(base)

    specific = mapping.get((env or "").lower())
    if specific:
        files.append(specific)

    # Явный файл: ENV_FILE=.env.whatever (или абсолютный путь)
    explicit = os.getenv("ENV_FILE", "").strip()
    if explicit:
        p = Path(explicit)
        files.append(p if p.is_absolute() else (root / p))

    # Убираем дубли
    uniq: list[Path] = []
    seen = set()
    for f in files:
        key = str(f)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(f)

    return uniq


def load_env_files(env: str | None = None) -> None:
    """Best-effort загрузка .env файлов в os.environ.

    Приоритеты:
      1) Уже заданные ENV переменные — не перезаписываются.
      2) .env (общий)
      3) .env.<env > (специфичный для окружения)
      4) ENV_FILE (если задан) — грузится последним

    Важно: override=False защищает от случайного перезаписывания
    секретов в Vercel/Render/CI.
    """
    try:
        env_name = (
            env or os.getenv("ENV") or os.getenv("APP_ENV") or "local"
        ).strip()
        for path in _candidate_files(env_name):
            if path.exists():
                load_dotenv(
                    dotenv_path=path,
                    override=False,
                    encoding="utf-8",
                )
    except Exception:
        # Канон: не валим приложение из-за .env
        return
