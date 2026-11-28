from __future__ import annotations

import json
from typing import Any

from app.bot.bot import get_bot
from app.core.logging_core import get_logger
from app.identity.notification_channel import (
    NotificationChannelError,
    resolve_telegram_notification_channel,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

SHOP_NOTIFY_LANGS = (
    "en",
    "ru",
    "uk",
    "de",
    "fr",
    "es",
    "it",
    "tr",
    "pl",
    "da",
    "hi",
    "id",
    "sw",
    "pt",
    "ko",
    "ja",
)

_SHOP_ORDER_TEXTS: dict[str, dict[str, str]] = {
    "success": {
        "en": (
            "✅ Payment confirmed. The item has been credited. "
            "Return to Telegram."
        ),
        "ru": (
            "✅ Оплата подтверждена. Товар зачислен. "
            "Вернитесь в Telegram."
        ),
        "uk": (
            "✅ Оплату підтверджено. Товар зараховано. "
            "Поверніться до Telegram."
        ),
        "de": (
            "✅ Zahlung bestätigt. Der Artikel wurde gutgeschrieben. "
            "Kehren Sie zu Telegram zurück."
        ),
        "fr": (
            "✅ Paiement confirmé. L'article a été crédité. "
            "Retournez dans Telegram."
        ),
        "es": (
            "✅ Pago confirmado. El artículo fue acreditado. "
            "Vuelva a Telegram."
        ),
        "it": (
            "✅ Pagamento confermato. L'articolo è stato accreditato. "
            "Torna su Telegram."
        ),
        "tr": (
            "✅ Ödeme onaylandı. Ürün hesaba işlendi. Telegram'a dönün."
        ),
        "pl": (
            "✅ Płatność potwierdzona. Produkt został dodany. "
            "Wróć do Telegrama."
        ),
        "da": (
            "✅ Betalingen er bekræftet. Varen er krediteret. "
            "Vend tilbage til Telegram."
        ),
        "hi": (
            "✅ भुगतान की पुष्टि हो गई। आइटम जोड़ दिया गया है। "
            "Telegram पर लौटें।"
        ),
        "id": (
            "✅ Pembayaran dikonfirmasi. Item telah dikreditkan. "
            "Kembali ke Telegram."
        ),
        "sw": (
            "✅ Malipo yamethibitishwa. Bidhaa imeongezwa. "
            "Rudi Telegram."
        ),
        "pt": (
            "✅ Pagamento confirmado. O item foi creditado. "
            "Regresse ao Telegram."
        ),
        "ko": "✅ 결제가 확인되었습니다. 상품이 적립되었습니다. Telegram으로 돌아가세요.",
        "ja": "✅ 支払いが確認されました。商品が反映されました。Telegramに戻ってください。",
    },
    "error": {
        "en": "⚠️ Payment error. Contact support.",
        "ru": "⚠️ Ошибка платежа. Свяжитесь с поддержкой.",
        "uk": "⚠️ Помилка платежу. Зверніться до підтримки.",
        "de": "⚠️ Zahlungsfehler. Kontaktieren Sie den Support.",
        "fr": "⚠️ Erreur de paiement. Contactez le support.",
        "es": "⚠️ Error de pago. Contacte con soporte.",
        "it": "⚠️ Errore di pagamento. Contatta il supporto.",
        "tr": "⚠️ Ödeme hatası. Destek ile iletişime geçin.",
        "pl": "⚠️ Błąd płatności. Skontaktuj się ze wsparciem.",
        "da": "⚠️ Betalingsfejl. Kontakt support.",
        "hi": "⚠️ भुगतान त्रुटि। सहायता टीम से संपर्क करें।",
        "id": "⚠️ Kesalahan pembayaran. Hubungi dukungan.",
        "sw": "⚠️ Hitilafu ya malipo. Wasiliana na usaidizi.",
        "pt": "⚠️ Erro de pagamento. Contacte o suporte.",
        "ko": "⚠️ 결제 오류입니다. 지원팀에 문의하세요.",
        "ja": "⚠️ 支払いエラーです。サポートにお問い合わせください。",
    },
}


def _normalize_shop_notify_lang(lang: str | None) -> str:
    lc = str(lang or "").strip().lower()
    for code in SHOP_NOTIFY_LANGS:
        if lc.startswith(code):
            return code
    return "en"


def _shop_order_text(kind: str, lang: str | None) -> str:
    norm_lang = _normalize_shop_notify_lang(lang)
    bucket = _SHOP_ORDER_TEXTS[str(kind)]
    return bucket.get(norm_lang) or bucket["en"]


def _extract_lang_from_extra(extra_json: dict[str, Any]) -> str | None:
    for key in (
        "lang",
        "language",
        "language_code",
        "ui_lang",
        "preferred_language",
    ):
        value = extra_json.get(key)
        if value:
            return str(value)
    return None


async def _get_user_shop_notify_lang(
    db: AsyncSession,
    *,
    global_id: int,
    extra_json: dict[str, Any],
) -> str:
    from_extra = _extract_lang_from_extra(extra_json)
    if from_extra:
        return _normalize_shop_notify_lang(from_extra)
    row = (
        await db.execute(
            text(
                "SELECT meta FROM efhc_core.users "
                "WHERE global_id = :global_id LIMIT 1"
            ),
            {"global_id": int(global_id)},
        )
    ).first()
    if not row or not isinstance(row[0], dict):
        return "en"
    meta = row[0]
    for key in (
        "lang",
        "language",
        "language_code",
        "ui_lang",
        "preferred_language",
    ):
        value = meta.get(key)
        if value:
            return _normalize_shop_notify_lang(str(value))
    return "en"


async def _send_message(*, tg_id: int, text_message: str) -> bool:
    try:
        bot = get_bot()
        await bot.send_message(chat_id=int(tg_id), text=text_message)
        return True
    except Exception as exc:
        logger.warning(
            "shop order notify failed: recipient=<redacted> err=%s",
            exc,
        )
        return False


async def _store_notify_marks(
    db: AsyncSession,
    *,
    order_id: int,
    extra_json: dict[str, Any],
    status_mark: str | None = None,
    error_mark: str | None = None,
) -> None:
    updated = dict(extra_json)
    if status_mark is not None:
        updated["telegram_notified_status"] = str(status_mark)
    if error_mark is not None:
        updated["telegram_notified_error_log"] = str(error_mark)
    await db.execute(
        text(
            "UPDATE efhc_core.shop_orders "
            "SET extra = CAST(:extra_json AS jsonb), "
            "updated_at = NOW() "
            "WHERE id = :oid"
        ),
        {
            "oid": int(order_id),
            "extra_json": json.dumps(updated, ensure_ascii=False),
        },
    )


async def dispatch_shop_order_notifications(
    db: AsyncSession,
    *,
    limit: int = 100,
) -> dict[str, int]:
    rows = (
        (
            await db.execute(
                text(
                    "SELECT id, global_id, status, "
                    "payment_error_"
                    "log, extra "
                    "FROM efhc_core.shop_orders "
                    "WHERE global_id IS NOT NULL "
                    "ORDER BY updated_at ASC, id ASC "
                    "LIMIT :lim"
                ),
                {"lim": int(limit)},
            )
        )
        .mappings()
        .all()
    )

    sent_success = 0
    sent_error = 0
    skipped = 0

    for row in rows:
        order_id = int(row["id"])
        global_id = int(row["global_id"])
        try:
            channel = await resolve_telegram_notification_channel(
                db,
                global_id=global_id,
            )
        except NotificationChannelError as exc:
            logger.warning(
                "shop order channel conflict: "
                "order_id=%s global_id=%s err=%s",
                order_id,
                global_id,
                exc,
            )
            skipped += 1
            continue
        if channel is None:
            skipped += 1
            continue
        tg_id = int(channel.tg_id)
        status = str(row.get("status") or "")
        error_log = str(row.get("payment_error_log") or "").strip()
        extra_json = dict(row.get("extra") or {})
        notified_status = str(
            extra_json.get("telegram_notified_status") or ""
        )
        notified_error = str(
            extra_json.get("telegram_notified_error_log") or ""
        )
        lang = await _get_user_shop_notify_lang(
            db,
            global_id=global_id,
            extra_json=extra_json,
        )

        if status == "PAID_AUTO" and notified_status != "PAID_AUTO":
            ok = await _send_message(
                tg_id=tg_id,
                text_message=_shop_order_text("success", lang),
            )
            if ok:
                await _store_notify_marks(
                    db,
                    order_id=order_id,
                    extra_json=extra_json,
                    status_mark="PAID_AUTO",
                )
                sent_success += 1
            else:
                skipped += 1
            continue

        if (
            error_log
            and status != "PAID_AUTO"
            and notified_error != error_log
        ):
            ok = await _send_message(
                tg_id=tg_id,
                text_message=_shop_order_text("error", lang),
            )
            if ok:
                await _store_notify_marks(
                    db,
                    order_id=order_id,
                    extra_json=extra_json,
                    error_mark=error_log,
                )
                sent_error += 1
            else:
                skipped += 1
            continue

        skipped += 1

    return {
        "sent_success": sent_success,
        "sent_error": sent_error,
        "skipped": skipped,
    }
