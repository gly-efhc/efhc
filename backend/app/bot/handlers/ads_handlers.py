"""Bot ADS entrypoint.

Основной universal flow: ``/ads`` → WebApp → ``/tasks`` → AdManager.
Дополнительно, если AdsGram bot-native configuration реально настроена,
команда может показать официальный AdsGram Bot creative. Это рекламный
provider surface и не является отдельным EFHCb reward path.
"""

from __future__ import annotations

from aiogram import Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from app.bot.keyboards import kb__main__menu
from app.integrations.ads.adsgram_bot import fetch_adsgram_bot_ad
from app.services.ads.config_service import load_provider_config
from sqlalchemy.ext.asyncio import AsyncSession

router = Router()


def _native_keyboard(
    *,
    click_url: str | None,
    button_name: str | None,
    reward_url: str | None,
    reward_name: str | None,
) -> InlineKeyboardMarkup | None:
    rows: list[list[InlineKeyboardButton]] = []
    if click_url:
        rows.append([InlineKeyboardButton(text=button_name or "Открыть", url=click_url)])
    if reward_url:
        rows.append([InlineKeyboardButton(text=reward_name or "Проверить действие", url=reward_url)])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


@router.message(Command("ads"))
async def cmd_ads(message: Message, db: AsyncSession) -> None:
    """Открыть рекламные задания; при наличии config показать bot-native ad."""

    native_sent = False
    if message.from_user is not None:
        try:
            config = await load_provider_config(db, "adsgram")
            creative = await fetch_adsgram_bot_ad(
                config,
                provider_tg_id=message.from_user.id,
                language=str(message.from_user.language_code or "en"),
            )
        except Exception:
            # Bot-native реклама — дополнительный provider surface. Любой сбой
            # fail-closed переводит пользователя в универсальный WebApp flow.
            creative = None
        if creative is not None:
            markup = _native_keyboard(
                click_url=creative.click_url,
                button_name=creative.button_name,
                reward_url=creative.reward_url,
                reward_name=creative.button_reward_name,
            )
            if creative.image_url:
                await message.answer_photo(
                    photo=creative.image_url,
                    caption=creative.text_html,
                    parse_mode=ParseMode.HTML,
                    reply_markup=markup,
                    protect_content=True,
                )
            else:
                await message.answer(
                    creative.text_html,
                    parse_mode=ParseMode.HTML,
                    reply_markup=markup,
                    protect_content=True,
                )
            native_sent = True

    await message.answer(
        (
            "🎯 Рекламные задания и начисления EFHCb доступны в WebApp → Задания."
            if native_sent
            else "📺 Реклама сейчас доступна через WebApp → Задания."
        ),
        reply_markup=kb__main__menu(),
    )
