from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.core.config_core import get_settings
from app.core.logging_core import get_logger
from app.core.security_core import create_jwt_token
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

SUPPORTED_OUTCOME_LANGS = (
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

_WITHDRAW_COMMENT_DEFAULTS: dict[str, dict[str, str]] = {
    "withdraw_success_comment": {
        "en": "Withdrawal confirmed. Your EFHC payout is on the way.",
        "ru": "Вывод подтверждён. Выплата EFHC уже в пути.",
        "uk": "Виведення підтверджено. Виплата EFHC вже в дорозі.",
        "de": (
            "Auszahlung bestätigt. Ihre EFHC-Auszahlung ist unterwegs."
        ),
        "fr": "Retrait confirmé. Votre versement EFHC est en cours.",
        "es": "Retiro confirmado. Su pago EFHC ya está en camino.",
        "it": "Prelievo confermato. Il tuo pagamento EFHC è in arrivo.",
        "tr": "Çekim onaylandı. EFHC ödemeniz yolda.",
        "pl": "Wypłata potwierdzona. Twoja wypłata EFHC jest w drodze.",
        "da": (
            "Udbetalingen er bekræftet. Din EFHC-udbetaling er på vej."
        ),
        "hi": "निकासी की पुष्टि हो गई। आपका EFHC भुगतान रास्ते में है।",
        "id": (
            "Penarikan dikonfirmasi. Pembayaran "
            "EFHC Anda sedang diproses."
        ),
        "sw": "Utoaji umethibitishwa. Malipo yako ya EFHC yako njiani.",
        "pt": "Levantamento confirmado. O seu pagamento EFHC está a caminho.",
        "ko": "출금이 확인되었습니다. EFHC 지급이 진행 중입니다.",
        "ja": "出金が確認されました。EFHCの支払いを処理しています。",
    },
    "withdraw_reject_comment": {
        "en": (
            "Withdrawal was not approved. Please review the note below."
        ),
        "ru": (
            "Вывод не был подтверждён. Пожалуйста, "
            "ознакомьтесь с примечанием ниже."
        ),
        "uk": (
            "Виведення не було підтверджено. Будь ласка, "
            "ознайомтеся з приміткою нижче."
        ),
        "de": (
            "Die Auszahlung wurde nicht bestätigt. "
            "Bitte lesen Sie den Hinweis unten."
        ),
        "fr": (
            "Le retrait n'a pas été confirmé. "
            "Veuillez lire la note ci-dessous."
        ),
        "es": "El retiro no fue confirmado. Revise la nota de abajo.",
        "it": (
            "Il prelievo non è stato confermato. "
            "Leggi la nota qui sotto."
        ),
        "tr": "Çekim onaylanmadı. Lütfen aşağıdaki notu inceleyin.",
        "pl": (
            "Wypłata nie została potwierdzona. "
            "Proszę sprawdzić notatkę poniżej."
        ),
        "da": (
            "Udbetalingen blev ikke bekræftet. "
            "Se venligst noten nedenfor."
        ),
        "hi": (
            "निकासी की पुष्टि नहीं हुई। "
            "कृपया नीचे दी गई टिप्पणी देखें।"
        ),
        "id": (
            "Penarikan tidak dikonfirmasi. "
            "Silakan lihat catatan di bawah."
        ),
        "sw": (
            "Utoaji haukuthibitishwa. "
            "Tafadhali soma maelezo hapa chini."
        ),
        "pt": (
            "O levantamento não foi confirmado. "
            "Consulte a nota abaixo."
        ),
        "ko": "출금이 확인되지 않았습니다. 아래 안내를 확인하세요.",
        "ja": "出金は確認されませんでした。以下の案内をご確認ください。",
    },
}

_WITHDRAW_PROMO_DEFAULTS: dict[str, dict[str, str]] = {
    "title": {
        "en": "Keep building your EFHC reserve",
        "ru": "Продолжайте наращивать свой резерв EFHC",
        "uk": "Продовжуйте нарощувати свій резерв EFHC",
        "de": "Bauen Sie Ihre EFHC-Reserve weiter auf",
        "fr": "Continuez à renforcer votre réserve EFHC",
        "es": "Siga fortaleciendo su reserva EFHC",
        "it": "Continua a rafforzare la tua riserva EFHC",
        "tr": "EFHC rezervinizi güçlendirmeye devam edin",
        "pl": "Dalej wzmacniaj swoją rezerwę EFHC",
        "da": "Fortsæt med at styrke din EFHC-reserve",
        "hi": "अपना EFHC रिज़र्व आगे बढ़ाते रहें",
        "id": "Terus bangun cadangan EFHC Anda",
        "sw": "Endelea kujenga akiba yako ya EFHC",
        "pt": "Continue a aumentar a sua reserva EFHC",
        "ko": "EFHC 준비금을 계속 늘리세요",
        "ja": "EFHCリザーブを引き続き増やしましょう",
    },
    "body": {
        "en": (
            "Return to the profile and continue your clean-energy path."
        ),
        "ru": "Вернитесь в профиль и продолжайте путь чистой энергии.",
        "uk": (
            "Поверніться до профілю й продовжуйте шлях чистої енергії."
        ),
        "de": (
            "Kehren Sie zum Profil zurück und setzen Sie "
            "Ihren Weg sauberer Energie fort."
        ),
        "fr": (
            "Retournez au profil et poursuivez "
            "votre parcours d'énergie propre."
        ),
        "es": (
            "Vuelva al perfil y continúe su camino de energía limpia."
        ),
        "it": (
            "Torna al profilo e continua "
            "il tuo percorso di energia pulita."
        ),
        "tr": (
            "Profile dönün ve temiz enerji yolculuğunuza devam edin."
        ),
        "pl": (
            "Wróć do profilu i kontynuuj swoją drogę czystej energii."
        ),
        "da": (
            "Vend tilbage til profilen og fortsæt "
            "din vej med ren energi."
        ),
        "hi": (
            "प्रोफ़ाइल पर लौटें और "
            "अपनी स्वच्छ ऊर्जा यात्रा जारी रखें।"
        ),
        "id": (
            "Kembali ke profil dan lanjutkan "
            "perjalanan energi bersih Anda."
        ),
        "sw": (
            "Rudi kwenye wasifu na uendelee "
            "na njia yako ya nishati safi."
        ),
        "pt": (
            "Regresse ao perfil e continue "
            "o seu percurso de energia limpa."
        ),
        "ko": "프로필로 돌아가 청정 에너지 여정을 계속하세요.",
        "ja": "プロフィールに戻り、クリーンエネルギーの歩みを続けましょう。",
    },
    "cta_label": {
        "en": "Open profile",
        "ru": "Открыть профиль",
        "uk": "Відкрити профіль",
        "de": "Profil öffnen",
        "fr": "Ouvrir le profil",
        "es": "Abrir perfil",
        "it": "Apri profilo",
        "tr": "Profili aç",
        "pl": "Otwórz profil",
        "da": "Åbn profil",
        "hi": "प्रोफ़ाइल खोलें",
        "id": "Buka profil",
        "sw": "Fungua wasifu",
        "pt": "Abrir perfil",
        "ko": "프로필 열기",
        "ja": "プロフィールを開く",
    },
}


@dataclass
class OutcomeCommentBlock:
    text: str
    template_key: str | None
    source: str
    locale: str
    manual_override_used: bool
    auto_translated: bool


@dataclass
class OutcomePromoBlock:
    enabled: bool
    key: str | None
    title: str | None
    body: str | None
    cta_label: str | None
    cta_url: str | None
    source: str | None


@dataclass
class WithdrawOutcomeBundle:
    request_id: int
    global_id: int
    tg_id: int
    outcome_kind: str
    locale: str
    comment: OutcomeCommentBlock
    promo: OutcomePromoBlock | None
    top_zone_enabled: bool
    metadata: dict[str, Any]


def _append_token(url: str, token: str) -> str:
    """Добавить handoff bearer во fragment, не в HTTP query."""

    parts = urlsplit(url)
    fragment = dict(parse_qsl(parts.fragment, keep_blank_values=True))
    fragment["token"] = token
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            parts.query,
            urlencode(fragment),
        )
    )


def _derive_web_profile_public_url() -> str | None:
    settings = get_settings()
    explicit = str(
        getattr(settings, "WEB_PROFILE_PUBLIC_URL", "") or ""
    ).strip()
    if explicit:
        return explicit
    handoff = str(
        getattr(settings, "HUB_EFHC_BUY_URL", "") or ""
    ).strip()
    if not handoff:
        return None
    parts = urlsplit(handoff)
    if not parts.scheme or not parts.netloc:
        return None
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            "/web-profile",
            "",
            "",
        )
    )


def create_withdraw_outcome_web_profile_url(
    *,
    global_id: int,
) -> str | None:
    base = _derive_web_profile_public_url()
    if not base:
        return None
    ttl = int(
        getattr(get_settings(), "HUB_EFHC_HANDOFF_TTL_SEC", 300) or 300
    )
    token = create_jwt_token(
        "hub_efhc_handoff",
        expires_delta=timedelta(seconds=ttl),
        extra={
            "kind": "hub_efhc_handoff",
            "aud": "efhc_buy_site",
            "global_id": int(global_id),
        },
    )
    return _append_token(base, token)


def build_withdraw_outcome_telegram_message(
    *,
    bundle: WithdrawOutcomeBundle,
    profile_url: str | None,
) -> str:
    header = (
        f"✅ Withdrawal update #{bundle.request_id}"
        if bundle.outcome_kind == "success"
        else f"⚠️ Withdrawal update #{bundle.request_id}"
    )
    lines = [header]
    if bundle.outcome_kind == "success":
        lines.append(
            "Open your Web-Profile to see the confirmed result "
            "and next steps."
        )
    else:
        lines.append(
            "Open your Web-Profile to review the result note "
            "and next steps."
        )
    if profile_url:
        lines.append(profile_url)
    return "\n".join(lines)


async def mark_withdraw_outcome_delivery(
    db: AsyncSession,
    *,
    request_id: int,
    channel: str,
    status: str,
) -> None:
    await db.execute(
        text(
            """
            UPDATE efhc_core.withdraw_outcome_events
            SET source_snapshot = jsonb_set(
                    COALESCE(source_snapshot, '{}'::jsonb),
                    CAST(:path AS text[]),
                    to_jsonb(CAST(:status AS text)),
                    true
                ),
                updated_at = timezone('utc', now())
            WHERE withdraw_request_id = :request_id
            """
        ),
        {
            "request_id": int(request_id),
            "status": str(status),
            "path": [str(channel)],
        },
    )


async def send_withdraw_outcome_telegram_notification(
    db: AsyncSession,
    *,
    bundle: WithdrawOutcomeBundle,
) -> bool:
    profile_url = create_withdraw_outcome_web_profile_url(
        global_id=int(bundle.global_id)
    )
    if profile_url:
        bundle.metadata["web_profile_outcome_url"] = profile_url
    message = build_withdraw_outcome_telegram_message(
        bundle=bundle,
        profile_url=profile_url,
    )
    try:
        from app.bot.bot import get_bot

        bot = get_bot()
        await bot.send_message(
            chat_id=int(bundle.tg_id),
            text=message,
            disable_web_page_preview=True,
        )
    except Exception as exc:
        logger.warning(
            "withdraw outcome telegram notify failed: "
            "req=%s global_id=%s recipient=<redacted> err=%s",
            bundle.request_id,
            bundle.global_id,
            exc,
        )
        await mark_withdraw_outcome_delivery(
            db,
            request_id=int(bundle.request_id),
            channel="telegram_delivery",
            status="failed",
        )
        return False
    await mark_withdraw_outcome_delivery(
        db,
        request_id=int(bundle.request_id),
        channel="telegram_delivery",
        status="sent",
    )
    return True


def normalize_outcome_lang(lang: str | None) -> str:
    lc = str(lang or "").strip().lower()
    for code in SUPPORTED_OUTCOME_LANGS:
        if lc.startswith(code):
            return code
    return "ru"


def _default_value(bucket: str, lang: str) -> str | None:
    values = _WITHDRAW_COMMENT_DEFAULTS.get(bucket)
    if values:
        return values.get(lang) or values.get("ru")
    values = _WITHDRAW_PROMO_DEFAULTS.get(bucket)
    if values:
        return values.get(lang) or values.get("ru") or values.get("en")
    return None


async def get_user_outcome_lang(
    db: AsyncSession,
    *,
    global_id: int,
) -> str:
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
        return "ru"
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
            return normalize_outcome_lang(str(value))
    return "ru"


async def get_system_template(
    db: AsyncSession,
    *,
    key: str,
    lang: str,
) -> str | None:
    norm_lang = normalize_outcome_lang(lang)
    search_keys = [f"{key}.{norm_lang}"]
    if norm_lang != "ru":
        search_keys.append(f"{key}.ru")
    search_keys.append(str(key))
    for lookup in search_keys:
        row = (
            await db.execute(
                text(
                    "SELECT content FROM efhc_core.system_templates "
                    "WHERE key = :key LIMIT 1"
                ),
                {"key": lookup},
            )
        ).first()
        if row and row[0] is not None:
            value = str(row[0]).strip()
            if value:
                return value
    return _default_value(str(key), norm_lang)


@dataclass
class AdminWithdrawOutcomePreview:
    request_id: int
    withdrawal_status: str
    preview_mode: str
    bundle: WithdrawOutcomeBundle


async def resolve_withdraw_comment(
    db: AsyncSession,
    *,
    global_id: int,
    outcome_kind: str,
    manual_override: str | None = None,
    auto_translated: bool = False,
    locale: str | None = None,
) -> OutcomeCommentBlock:
    lang = (
        normalize_outcome_lang(locale)
        if locale
        else (await get_user_outcome_lang(db, global_id=int(global_id)))
    )
    clean_override = str(manual_override or "").strip()
    if clean_override:
        return OutcomeCommentBlock(
            text=clean_override,
            template_key=None,
            source="manual_override",
            locale=lang,
            manual_override_used=True,
            auto_translated=bool(auto_translated),
        )
    template_key = (
        "withdraw_success_comment"
        if outcome_kind == "success"
        else "withdraw_reject_comment"
    )
    text_out = await get_system_template(
        db,
        key=template_key,
        lang=lang,
    )
    return OutcomeCommentBlock(
        text=str(text_out or "").strip(),
        template_key=template_key,
        source="system_template",
        locale=lang,
        manual_override_used=False,
        auto_translated=False,
    )


async def resolve_withdraw_promo(
    db: AsyncSession,
    *,
    outcome_kind: str,
    locale: str,
    context: str = "default",
) -> OutcomePromoBlock | None:
    if outcome_kind != "success":
        return None
    lang = normalize_outcome_lang(locale)
    row = (
        await db.execute(
            text(
                "SELECT id, title, body, cta_label, cta_url "
                "FROM efhc_core.outcome_fallback_promos "
                "WHERE domain = 'withdraw_success' "
                "AND locale IN (:locale, 'ru') "
                "AND (context = :context OR context IS NULL) "
                "AND is_active = TRUE "
                "ORDER BY CASE WHEN locale = :locale "
                "THEN 0 ELSE 1 END, "
                "CASE WHEN context = :context "
                "THEN 0 ELSE 1 END, id ASC "
                "LIMIT 1"
            ),
            {"locale": lang, "context": context},
        )
    ).first()
    if row:
        return OutcomePromoBlock(
            enabled=True,
            key=f"fallback_promo:{int(row[0])}",
            title=str(row[1] or "").strip() or None,
            body=str(row[2] or "").strip() or None,
            cta_label=str(row[3] or "").strip() or None,
            cta_url=str(row[4] or "").strip() or None,
            source="fallback_promo",
        )
    return OutcomePromoBlock(
        enabled=True,
        key="fallback_promo:withdraw_success",
        title=_default_value("title", lang),
        body=_default_value("body", lang),
        cta_label=_default_value("cta_label", lang),
        cta_url="/profile",
        source="fallback_promo_default",
    )


async def save_withdraw_outcome_event(
    db: AsyncSession,
    *,
    bundle: WithdrawOutcomeBundle,
) -> None:
    promo = bundle.promo
    await db.execute(
        text(
            """
            INSERT INTO efhc_core.withdraw_outcome_events (
                withdraw_request_id,
                global_id,
                tg_id,
                outcome_kind,
                locale,
                comment_template_key,
                comment_text,
                comment_source,
                manual_override_used,
                auto_translated,
                promo_enabled,
                promo_key,
                promo_title,
                promo_body,
                promo_cta_label,
                promo_cta_url,
                promo_source,
                source_snapshot
            ) VALUES (
                :withdraw_request_id,
                :global_id,
                :tg_id,
                :outcome_kind,
                :locale,
                :comment_template_key,
                :comment_text,
                :comment_source,
                :manual_override_used,
                :auto_translated,
                :promo_enabled,
                :promo_key,
                :promo_title,
                :promo_body,
                :promo_cta_label,
                :promo_cta_url,
                :promo_source,
                CAST(:source_snapshot AS jsonb)
            )
            ON CONFLICT (withdraw_request_id) DO UPDATE SET
                global_id = EXCLUDED.global_id,
                tg_id = EXCLUDED.tg_id,
                outcome_kind = EXCLUDED.outcome_kind,
                locale = EXCLUDED.locale,
                comment_template_key = EXCLUDED.comment_template_key,
                comment_text = EXCLUDED.comment_text,
                comment_source = EXCLUDED.comment_source,
                manual_override_used = EXCLUDED.manual_override_used,
                auto_translated = EXCLUDED.auto_translated,
                promo_enabled = EXCLUDED.promo_enabled,
                promo_key = EXCLUDED.promo_key,
                promo_title = EXCLUDED.promo_title,
                promo_body = EXCLUDED.promo_body,
                promo_cta_label = EXCLUDED.promo_cta_label,
                promo_cta_url = EXCLUDED.promo_cta_url,
                promo_source = EXCLUDED.promo_source,
                source_snapshot = EXCLUDED.source_snapshot,
                updated_at = timezone('utc', now())
            """
        ),
        {
            "withdraw_request_id": int(bundle.request_id),
            "global_id": int(bundle.global_id),
            "tg_id": int(bundle.tg_id),
            "outcome_kind": bundle.outcome_kind,
            "locale": bundle.locale,
            "comment_template_key": bundle.comment.template_key,
            "comment_text": bundle.comment.text,
            "comment_source": bundle.comment.source,
            "manual_override_used": bundle.comment.manual_override_used,
            "auto_translated": bundle.comment.auto_translated,
            "promo_enabled": bool(promo and promo.enabled),
            "promo_key": promo.key if promo else None,
            "promo_title": promo.title if promo else None,
            "promo_body": promo.body if promo else None,
            "promo_cta_label": promo.cta_label if promo else None,
            "promo_cta_url": promo.cta_url if promo else None,
            "promo_source": promo.source if promo else None,
            "source_snapshot": __import__("json").dumps(
                bundle.metadata,
                ensure_ascii=False,
            ),
        },
    )


async def build_withdraw_outcome_bundle(
    db: AsyncSession,
    *,
    request_id: int,
    tg_id: int,
    outcome_kind: str,
    global_id: int,
    manual_comment: str | None = None,
    auto_translated: bool = False,
    locale: str | None = None,
) -> WithdrawOutcomeBundle:
    comment = await resolve_withdraw_comment(
        db,
        global_id=int(global_id),
        outcome_kind=outcome_kind,
        manual_override=manual_comment,
        auto_translated=auto_translated,
        locale=locale,
    )
    promo = await resolve_withdraw_promo(
        db,
        outcome_kind=outcome_kind,
        locale=comment.locale,
    )
    return WithdrawOutcomeBundle(
        request_id=int(request_id),
        global_id=int(global_id),
        tg_id=int(tg_id),
        outcome_kind=outcome_kind,
        locale=comment.locale,
        comment=comment,
        promo=promo,
        top_zone_enabled=bool(promo and promo.enabled),
        metadata={
            "request_id": int(request_id),
            "outcome_kind": outcome_kind,
        },
    )


async def get_withdraw_outcome_bundle(
    db: AsyncSession,
    *,
    request_id: int,
    global_id: int,
) -> WithdrawOutcomeBundle:
    query = text(
        """
        SELECT
            wr.id,
            wr.tg_id,
            woe.outcome_kind,
            woe.locale,
            woe.comment_template_key,
            woe.comment_text,
            woe.comment_source,
            woe.manual_override_used,
            woe.auto_translated,
            woe.promo_enabled,
            woe.promo_key,
            woe.promo_title,
            woe.promo_body,
            woe.promo_cta_label,
            woe.promo_cta_url,
            woe.promo_source,
            woe.source_snapshot,
            wr.status,
            wr.global_id
        FROM efhc_core.withdraw_requests wr
        LEFT JOIN efhc_core.withdraw_outcome_events woe
          ON woe.withdraw_request_id = wr.id
        WHERE wr.id = :request_id
          AND wr.global_id = :global_id
        LIMIT 1
        """
    )
    params = {
        "request_id": int(request_id),
        "global_id": int(global_id),
    }
    row = (await db.execute(query, params)).first()

    if not row:
        raise ValueError("withdraw outcome not found")
    if row[2] is None:
        status = str(row[17] or "")
        if status == "PAID":
            outcome_kind = "success"
        elif status in {"REJECTED", "CANCELED"}:
            outcome_kind = "reject"
        else:
            raise ValueError("withdraw outcome is not ready")
        bundle = await build_withdraw_outcome_bundle(
            db,
            request_id=int(row[0]),
            tg_id=int(row[1]),
            global_id=int(row[18]),
            outcome_kind=outcome_kind,
        )
        return bundle
    promo = None
    if bool(row[9]):
        promo = OutcomePromoBlock(
            enabled=True,
            key=row[10],
            title=row[11],
            body=row[12],
            cta_label=row[13],
            cta_url=row[14],
            source=row[15],
        )
    return WithdrawOutcomeBundle(
        request_id=int(row[0]),
        global_id=int(row[18]),
        tg_id=int(row[1]),
        outcome_kind=str(row[2]),
        locale=str(row[3]),
        comment=OutcomeCommentBlock(
            text=str(row[5]),
            template_key=row[4],
            source=str(row[6]),
            locale=str(row[3]),
            manual_override_used=bool(row[7]),
            auto_translated=bool(row[8]),
        ),
        promo=promo,
        top_zone_enabled=bool(row[9]),
        metadata=dict(row[16] or {}),
    )


async def get_admin_withdraw_outcome_preview(
    db: AsyncSession,
    *,
    request_id: int,
    mode: str = "auto",
) -> AdminWithdrawOutcomePreview:
    row = (
        await db.execute(
            text(
                """
                SELECT id, tg_id, status, global_id
                FROM efhc_core.withdraw_requests
                WHERE id = :request_id
                LIMIT 1
                """
            ),
            {"request_id": int(request_id)},
        )
    ).first()
    if not row:
        raise ValueError("withdraw request not found")
    status = str(row[2] or "")
    norm_mode = str(mode or "auto").strip().lower()
    if norm_mode == "success":
        outcome_kind = "success"
    elif norm_mode == "reject":
        outcome_kind = "reject"
    elif status == "PAID":
        outcome_kind = "success"
        norm_mode = "stored"
    elif status in {"REJECTED", "CANCELED"}:
        outcome_kind = "reject"
        norm_mode = "stored"
    else:
        outcome_kind = "success"
        norm_mode = "pending_success_preview"
    if status in {"PAID", "REJECTED", "CANCELED"}:
        bundle = await get_withdraw_outcome_bundle(
            db,
            request_id=int(row[0]),
            global_id=int(row[3]),
        )
    else:
        bundle = await build_withdraw_outcome_bundle(
            db,
            request_id=int(row[0]),
            tg_id=int(row[1]),
            global_id=int(row[3]),
            outcome_kind=outcome_kind,
        )
    return AdminWithdrawOutcomePreview(
        request_id=int(row[0]),
        withdrawal_status=status,
        preview_mode=norm_mode,
        bundle=bundle,
    )
