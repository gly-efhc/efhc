# backend/app/middleware/telegram_webapp_auth.py
# ====================================================================
# EFHC Bot — Telegram WebApp security gate (канон).
# --------------------------------------------------------------------
# Задача:
# • Централизованно валидировать Telegram WebApp initData (HMAC).
# • Проставлять request.state.tg_id.
#
# Почему это важно:
# • tg_id нельзя доверять ни body, ни заголовкам без криптопроверки.
# • Идентичность пользователя в WebApp подтверждается только initData.
#
# Инварианты:
# • Никаких денежных операций здесь (только аутентификация).
# • Ошибки валидации не валят процесс — возвращаем контролируемый ответ.
# ====================================================================

from __future__ import annotations

from typing import Any, cast

from app.core.logging_core import get_logger
from app.core.security_core import validate_telegram__init__data
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

logger = get_logger(__name__)


def _extract_tg_id(payload: dict[str, Any]) -> int | None:
    """Достаём Telegram user.id из распарсенного initData."""
    user_obj = payload.get("user")
    if not isinstance(user_obj, dict):
        return None

    tg_id = user_obj.get("id")
    if tg_id is None:
        return None
    if not isinstance(tg_id, int | str):
        return None
    try:
        tg_id_i = int(tg_id)
    except Exception:
        return None

    return tg_id_i if tg_id_i > 0 else None


class TelegramWebAppAuthMiddleware(BaseHTTPMiddleware):
    """Валидирует Telegram initData и выставляет request.state.tg_id."""

    def __init__(
        self,
        app,
        *,
        header_name: str = "X-Telegram-Init-Data",
    ):
        super().__init__(app)
        self.header_name = header_name

    async def dispatch(self, request: Request, call_next) -> Response:
        # Если tg_id уже установлен (например, другим middleware/JWT),
        # не трогаем.
        if getattr(request.state, "tg_id", None):
            resp = await call_next(request)
            return cast(Response, resp)

        init_data = request.headers.get(self.header_name)
        if not init_data:
            alt = self.header_name.replace(" ", "")
            if alt != self.header_name:
                init_data = request.headers.get(alt)

        if init_data:
            try:
                parsed = validate_telegram__init__data(init_data)
                tg_id = _extract_tg_id(parsed)
                if tg_id:
                    request.state.tg_id = tg_id
                    request.state.tg_user = parsed.get("user")
            except Exception as e:
                # Не «роняем» приложение: verified provider-boundary dependency
                # даст 401 там, где нужно.
                logger.warning(
                    "Telegram initData validation failed: %s",
                    e,
                )

        resp = await call_next(request)
        return cast(Response, resp)
