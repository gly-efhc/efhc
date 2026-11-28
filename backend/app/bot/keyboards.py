"""Telegram inline keyboards for EFHC Bot (aiogram v3).

Buttons are navigation-only:
- open WebApp URLs
- optionally show "check subscription".
"""

from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo,
)
from app.core.config_core import get_settings

settings = get_settings()


def _webapp_url(path: str = "") -> str:
    """Build absolute WebApp URL for a path.

    Returns empty string if WEBAPP_URL is not configured.
    """
    base = (getattr(settings, "WEBAPP_URL", None) or "").rstrip("/")
    if not base:
        # Without WEBAPP_URL we still can show text-only bot commands.
        return ""
    if not path:
        return base
    if not path.startswith("/"):
        path = "/" + path
    return base + path


def kb__main__menu(
    *,
    require_subscribe: bool = False,
) -> InlineKeyboardMarkup:
    """Главное меню: кнопки разделов WebApp."""
    rows = []

    url_home = _webapp_url("/")
    if url_home:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🏠 WebApp",
                    web_app=WebAppInfo(url=url_home),
                ),
            ]
        )

    # Разделы (пути оставляем «логическими»; фронт сам роутит вкладки)

    def webapp_btn(
        text: str,
        path: str,
    ) -> InlineKeyboardButton | None:
        """Return WebApp button for path.

        Returns None if WEBAPP_URL is empty.
        """
        url = _webapp_url(path)
        if not url:
            return None
        return InlineKeyboardButton(
            text=text,
            web_app=WebAppInfo(url=url),
        )

    row1 = [
        b
        for b in [
            webapp_btn("⚡ Панели", "/panels"),
            webapp_btn("🔁 Обмен", "/exchange"),
        ]
        if b
    ]
    if row1:
        rows.append(row1)

    row2 = [
        b
        for b in [
            webapp_btn("🧭 Hub", "/hub"),
            webapp_btn("🏆 Рейтинг", "/ranks"),
        ]
        if b
    ]
    if row2:
        rows.append(row2)

    row3 = [
        b
        for b in [
            webapp_btn("🎯 Задания", "/tasks"),
        ]
        if b
    ]
    if row3:
        rows.append(row3)

    row4 = [
        b
        for b in [
            webapp_btn("👥 Рефералы", "/referrals"),
            webapp_btn("💸 Вывод", "/withdraw"),
        ]
        if b
    ]
    if row4:
        rows.append(row4)

    if require_subscribe:
        rows.append(
            [
                InlineKeyboardButton(
                    text="✅ Проверить подписку",
                    callback_data="check_subscribe",
                ),
            ]
        )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_subscribe(
    channel_username: str | None,
) -> InlineKeyboardMarkup:
    """Кнопки для обязательной подписки."""
    rows = []
    if channel_username:
        url = f"https://t.me/{channel_username.lstrip('@')}"
        rows.append(
            [
                InlineKeyboardButton(
                    text="📣 Перейти в канал",
                    url=url,
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="✅ Я подписался / Проверить",
                callback_data="check_subscribe",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_admin_entry() -> InlineKeyboardMarkup:
    """Admin entry keyboard with direct Admin → Hub access."""
    rows = []

    admin_hub = _webapp_url("/admin/hub")
    if admin_hub:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🛠 Admin Hub",
                    web_app=WebAppInfo(url=admin_hub),
                ),
            ]
        )

    main_hub = _webapp_url("/hub")
    if main_hub:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🧭 Hub",
                    web_app=WebAppInfo(url=main_hub),
                ),
            ]
        )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_faq_entry() -> InlineKeyboardMarkup:
    """FAQ entry keyboard with direct FAQ + Hub access."""
    rows = []

    faq_url = _webapp_url("/faq")
    if faq_url:
        rows.append(
            [
                InlineKeyboardButton(
                    text="❓ FAQ",
                    web_app=WebAppInfo(url=faq_url),
                ),
            ]
        )

    hub_url = _webapp_url("/hub")
    if hub_url:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🧭 Hub",
                    web_app=WebAppInfo(url=hub_url),
                ),
            ]
        )

    return InlineKeyboardMarkup(inline_keyboard=rows)
