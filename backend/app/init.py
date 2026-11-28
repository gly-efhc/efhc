# backend/app/init.py
# Совместимая точка входа, сохраняемая как startup compatibility boundary.

from __future__ import annotations


def create_app():
    """Вернуть канонический объект приложения из ``app.main``."""
    from .main import app as main_app

    return main_app


__all__ = ["create_app"]
