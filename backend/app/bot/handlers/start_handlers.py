# backend/app/bot/handlers/start_handlers.py
# ======================================================================
# Назначение кода:
# /start и базовая навигация Telegram-бота EFHC Bot (aiogram v3).
#
# Канон/инварианты:
# • Бот-слой не делает денег.
# • /start делает read-through регистрацию пользователя (users) и
#   выдаёт меню WebApp.
# • Реферальный параметр допускается, но учёт рефералов ведёт backend.
# ======================================================================

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message
from app.bot.keyboards import kb__main__menu, kb_faq_entry, kb_subscribe
from app.bot.texts import t
from app.core.logging_core import get_logger
from app.crud.user_crud import get_user_by_telegram_subject
from app.deps import d8
from app.services.panels_service import panels_summary
from app.services.referral_service import (
    ReferralOnboardingRejected,
    onboard_user_at_first_creation_in_transaction,
)
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)
router = Router()


def _extract_start_payload(message: Message) -> str | None:
    text = getattr(message, "text", None)
    if not isinstance(text, str):
        return None
    parts = text.strip().split(maxsplit=1)
    if len(parts) < 2:
        return None
    payload = parts[1].strip()
    return payload or None


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    db: AsyncSession,
    is_subscribed: bool = True,
    required_channel_username: str | None = None,
    required_channel_id: int | None = None,
) -> None:
    """/start — регистрация пользователя и показ меню."""
    if not message.from_user:
        return

    sender = message.from_user
    username = sender.username or sender.full_name or "user"
    tg_id = int(sender.id)

    # Канон: реферальная принадлежность фиксируется только вместе с
    # первым созданием пользователя. Существующий пользователь, включая
    # 0 user, никогда не может быть привязан или перепривязан позднее.
    payload = _extract_start_payload(message)
    try:
        await onboard_user_at_first_creation_in_transaction(
            db,
            tg_id=tg_id,
            username=sender.username,
            start_param=payload,
        )
    except ReferralOnboardingRejected as exc:
        logger.warning(
            "new user referral onboarding rejected: "
            "provider_subject=<redacted> reason=%s",
            exc.reason,
        )
        return
    except Exception:
        logger.exception("user onboarding failed")
        raise

    # Если включена обязательная подписка — сначала требуем её.
    if required_channel_id and not is_subscribed:
        channel = required_channel_username or str(required_channel_id)
        await message.answer(
            t("subscribe.required", channel=channel),
            reply_markup=kb_subscribe(required_channel_username),
        )
        return

    # Достаём факты для приветствия (без денег-операций).
    vip_flag = "?"
    panels = "0"
    avail_kwh = "0.00000000"
    try:
        user = await get_user_by_telegram_subject(db, tg_id=tg_id)
        if user:
            is_vip = bool(getattr(user, "is_vip", False))
            vip_flag = "VIP" if is_vip else "NO"
            avail_kwh = d8(getattr(user, "available_kwh", 0))

        if user and user.global_id is not None:
            summ = await panels_summary(
                db,
                global_id=int(user.global_id),
            )
            panels = str(summ.get("active_panels_count", 0))
    except Exception as e:
        logger.debug("start greeting data fetch skipped: %s", e)

    await message.answer(
        t(
            "welcome",
            username=username,
            vip_flag=vip_flag,
            panels=panels,
            avail_kwh=avail_kwh,
        ),
        reply_markup=kb__main__menu(
            require_subscribe=bool(required_channel_id),
        ),
    )
    await message.answer(t("help"))


@router.message(Command("help"))
async def cmd_help(
    message: Message,
    required_channel_id: int | None = None,
) -> None:
    """/help — краткая справка и меню."""
    await message.answer(
        t("help"),
        reply_markup=kb__main__menu(
            require_subscribe=bool(required_channel_id),
        ),
    )


@router.message(Command("faq"))
async def cmd_faq(message: Message) -> None:
    """/faq — direct WebApp FAQ entry."""
    await message.answer(
        t("faq.entry"),
        reply_markup=kb_faq_entry(),
    )


@router.callback_query(lambda c: c.data == "check_subscribe")
async def cb_check_subscribe(
    call: CallbackQuery,
    is_subscribed: bool = True,
    required_channel_username: str | None = None,
    required_channel_id: int | None = None,
) -> None:
    """Проверка подписки по кнопке."""
    if required_channel_id and not is_subscribed:
        await call.answer(
            "Не вижу подписку. Попробуйте ещё раз.",
            show_alert=True,
        )
        try:
            channel = required_channel_username or str(
                required_channel_id
            )
            msg = getattr(call, "message", None)
            if msg is None or not hasattr(msg, "edit_text"):
                return
            await msg.edit_text(
                t("subscribe.required", channel=channel),
                reply_markup=kb_subscribe(required_channel_username),
            )
        except Exception:
            return
        return

    await call.answer(
        "✅ Подписка подтверждена.",
        show_alert=True,
    )
    try:
        msg = getattr(call, "message", None)
        if msg is None or not hasattr(msg, "edit_text"):
            return
        await msg.edit_text(
            t("help"),
            reply_markup=kb__main__menu(
                require_subscribe=bool(required_channel_id),
            ),
        )
    except Exception:
        return
