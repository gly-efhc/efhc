# backend/app/integrations/ton_api.py
# ====================================================================
# EFHC Bot — Интеграция с TON API (клиент + DTO событий)
# --------------------------------------------------------------------
# Назначение:
# • Давать устойчивый доступ к входящим платежам TON
#   на адрес проекта.
# • Нормализовать разные форматы ответов (tonapi.io,
#   альтернативные ноды) в единый DTO TonAPIEvent
#   для вотчера.
#
# Канон/инварианты:
# • Денежные операции НЕ выполняются здесь. Модуль лишь читает блокчейн.
# • Идемпотентность на уровне вотчера
#   (UNIQUE tx_hash в БД).
# • Никаких NFT/генераций/балансов. Только получение
#   и нормализация событий.
#
# ИИ-защиты/самовосстановление:
# • Таймауты и последовательный fallback по списку базовых URL.
# • Мягкая деградация форматов: поддержка нескольких схем JSON-ответов.
# • Защита от дублей в пределах страницы (по tx_hash).
# • Детектор «дыр» по времени (optional, для метрик)
#   возвращает маркеры.
#
# Запреты:
# • Никакой записи в БД, переводов средств, автодоставки
#   NFT — здесь это
# запрещено.
# ====================================================================

from __future__ import annotations

import asyncio
import base64
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, cast

import httpx

# асинхронный HTTP-клиент; нужна зависимость "httpx[http2]"
from app.core.config_core import get_settings
from app.core.logging_core import get_logger
from app.integrations.ton_api_urls import ton_api_v2
from app.lib.time import utcnow

MIN_SAFE_NANOTON: int = 10_000_000  # 0.01 TON

logger = get_logger(__name__)
settings = get_settings()


# --------------------------------------------------------------------
# Публичный DTO события входящего платежа
# --------------------------------------------------------------------
@dataclass
class TonAPIEvent:
    """
    Унифицированное событие для вотчера.

    Важно:
    - Для TON: asset="TON", amount=TON, amount_asset=TON.
    - Для jetton: asset="JETTON", jetton_master заполняется,
      amount_asset = jetton amount (в минимальных единицах).
    """

    tx_hash: str
    from_address: str
    to_address: str
    amount: Decimal  # TON (для совместимости)
    memo: str
    utime: int
    asset: str = "TON"
    jetton_master: str = ""
    amount_asset: Decimal = Decimal("0")


# --------------------------------------------------------------------
# Вспомогательные утилиты нормализации
# --------------------------------------------------------------------


def _nt_to_ton(value: Any) -> Decimal:
    """
    Перевод нанотонов (int/str) в TON (Decimal).
    Если приходит уже в TON — интерпретируем как TON.
    """
    try:
        # Популярный формат: нанотоны в строке или числе
        n = Decimal(str(value))
        # Эвристика: большие значения считаем нанотонами
        # 10 млн нанотон = 0.01 TON, порог безопасен
        if n > MIN_SAFE_NANOTON:
            return (n / Decimal("1e9")).quantize(Decimal("0.000000001"))
        # Иначе — это уже TON
        return n.quantize(Decimal("0.000000001"))
    except Exception:
        return Decimal("0")


def _norm_addr(addr: str | None) -> str:
    """
    Нормализация адресов: убираем пробелы/кавычки/None,
    приводим к верхнему регистру
    для стабильных сравнений (визуальный формат в UI может быть иным).
    """
    s = (addr or "").strip()
    # У некоторых API встречаются поля type: "raw"/"bounceable" — тут не
    # различаем
    return s.upper()


def _norm_memo(m: str | None) -> str:
    """
    Нормализация MEMO/сообщения: безопасная строка UTF-8,
    обрезаем мусор.
    """
    if m is None:
        return ""
    try:
        # Иногда поле приходит как base64-строка — попытаемся понять
        if _looks_like_b64(m):
            try:
                raw = base64.b64decode(m, validate=True)
                m = raw.decode("utf-8", errors="replace")
            except Exception as exc:
                # Не критично — оставим как есть, но не молчим.
                logger.debug(
                    "TonAPI: memo b64 decode failed: %s",
                    exc,
                )
        return (m or "").strip()
    except Exception:
        return ""


def _looks_like_b64(s: str) -> bool:
    """Эвристика: похоже ли значение на base64."""
    if not s or len(s) < 8:
        return False
    try:
        base64.b64decode(s, validate=True)
        return True
    except Exception:
        return False


def _dedupe_by_hash(events: Iterable[TonAPIEvent]) -> list[TonAPIEvent]:
    """Удаляет дубли в пределах страницы по tx_hash."""
    seen = set()
    out: list[TonAPIEvent] = []
    for e in events:
        if e.tx_hash in seen:
            continue
        seen.add(e.tx_hash)
        out.append(e)
    return out


# --------------------------------------------------------------------
# Основной клиент TonAPI с fallback-логикой
# --------------------------------------------------------------------


class TonAPIClient:
    """
    Асинхронный клиент TON: fallback-узлы, таймауты, унификация
    ответов. Поддерживает tonapi.io и toncenter-подобные.
    """

    def __init__(
        self,
        base_url: str | None = None,
        fallback_urls: list[str] | None = None,
        api_key: str | None = None,
        request_timeout_sec: float = 20.0,
    ) -> None:
        """Инициализация клиента TON API с fallback и таймаутом."""
        env_primary = getattr(settings, "TON_API_BASE_URL", "")
        selected = base_url or env_primary or "https://tonapi.io"
        self._primary = ton_api_v2(selected)
        # fallback из .env
        # TON_API_FALLBACK_URLS="https://toncenter.com/api/v2,"
        # "https://tonapi.io/v2"
        env_fb = getattr(settings, "TON_API_FALLBACK_URLS", "")
        env_fb_list = [
            u.strip() for u in env_fb.split(",") if u.strip()
        ]
        self._fallbacks = (
            fallback_urls
            or env_fb_list
            or [
                "https://tonapi.io/v2",
                "https://toncenter.com/api/v2",
            ]
        )
        # Гарантируем без дубликатов при сборке списка
        seq = [
            self._primary,
            *[u for u in self._fallbacks if u != self._primary],
        ]
        self._urls = [ton_api_v2(u) for u in seq]

        self._key = api_key or getattr(settings, "TON_API_KEY", None)
        self._timeout = request_timeout_sec

        # Внутренний лимитер параллелизма (защита от "DDOS" внешних API)
        self._sem = asyncio.Semaphore(3)

    # -----------------------------
    # Публичный метод: входящие платежи
    # -----------------------------
    async def get_incoming_payments(
        self,
        to_address: str,
        limit: int = 200,
        since_utime: int | None = None,
    ) -> list[TonAPIEvent]:
        """
        Получить входящие транзакции на адрес проекта.
        • to_address — адрес приёма (обязателен)
        • limit — размер страницы (по умолчанию 200)
        • since_utime — нижняя граница (unixtime), опционально
        Возвращает список TonAPIEvent, по возможности отсортированный
        по времени убыванию.
        """
        if not to_address:
            logger.warning("TonAPIClient: empty to_address")
            return []

        # Jetton history is the authoritative source of TEP-74 transfers.
        # A failure of generic TON /events must never prevent Jetton reads.
        # Conversely, a generic-only reply must not advance the watcher
        # watermark while the Jetton source is unavailable.
        last_err: Exception | None = None
        for base in self._urls:
            try:
                async with self._sem:
                    jdata = await self._fetch_jettons_history(
                        base, to_address, limit, since_utime
                    )
                jetton_events = self._unify_jetton_ops(jdata, to_address)
            except Exception as exc:
                last_err = exc
                logger.warning(
                    "TonAPIClient: %s Jetton history unavailable (%s)", base, exc
                )
                continue

            generic_events: list[TonAPIEvent] = []
            try:
                async with self._sem:
                    data = await self._fetch_generic(
                        base, to_address, limit, since_utime
                    )
                generic_events = self._unify_events(data, to_address)
            except Exception as exc:
                # Successful Jetton history is sufficient for a deposit scan;
                # do not turn unrelated TON endpoint failures into a 503.
                logger.debug(
                    "TonAPIClient: %s generic TON history unavailable (%s)",
                    base, exc,
                )

            all_events = [*jetton_events, *generic_events]
            all_events.sort(key=lambda event: (event.utime, event.tx_hash), reverse=True)
            return _dedupe_by_hash(all_events)

        if last_err:
            raise last_err
        return []

    # -----------------------------
    # Частные методы — универсальный фетч и унификация
    # -----------------------------
    async def _fetch_generic(
        self,
        base_url: str,
        to_address: str,
        limit: int,
        since_utime: int | None,
    ) -> dict[str, Any]:
        """
        Универсальный фетч: пробует несколько эндпоинтов для base_url.
        Нормализует адрес и поддерживает tonapi/toncenter-подобные.
        """
        # TON friendly addresses encode case-sensitive base64url.
        # Uppercasing a wallet address changes the account; preserve bytes
        # for HTTP routes and use canonical raw addresses for comparisons.
        addr = str(to_address or "").strip()
        headers = {"Accept": "application/json"}
        if self._key:
            headers["Authorization"] = f"Bearer {self._key}"

        # Набор кандидатов эндпоинтов (в порядке приоритета).
        # Нельзя полагаться на один маршрут: у провайдера версии
        # меняются.
        candidates: list[tuple[str, dict[str, Any]]] = []

        start_date: str | None = None
        if since_utime:
            start_date = str(int(since_utime))

        # base_url already ends in exactly one /v2 (ton_api_v2).
        # Appending /v2 again produces 404: /v2/v2/accounts.
        # TonAPI v2 transaction API path: /v2/accounts/{address}/transactions
        candidates.append(
            (
                f"{base_url}/accounts/{addr}/transactions",
                {
                    "limit": str(int(limit)),
                    "start_date": start_date,
                },
            )
        )

        # tonapi.io events (альтернатива): /v2/accounts/{address}/events
        candidates.append(
            (
                f"{base_url}/accounts/{addr}/events",
                {
                    # TonAPI /events rejects any limit greater than 100.
                    "limit": str(max(1, min(int(limit), 100))),
                    "start_date": start_date,
                },
            )
        )

        # toncenter: /getTransactions?address=...&limit=...
        candidates.append(
            (
                f"{base_url}/getTransactions",
                {
                    "address": addr,
                    "limit": str(int(limit)),
                },
            )
        )

        async with httpx.AsyncClient(
            timeout=self._timeout,
            http2=True,
        ) as client:
            for url, params in candidates:
                # очищаем None из query
                q = {k: v for k, v in params.items() if v is not None}
                try:
                    r = await client.get(
                        url,
                        params=q,
                        headers=headers,
                    )
                    if r.status_code >= 500:
                        # серверная ошибка — пробуем следующий маршрут
                        # или базовый URL
                        # базовый URL
                        msg = f"upstream {url} http {r.status_code}"
                        raise RuntimeError(msg)
                    if r.status_code == 404:
                        # у конкретного base_url нет такого маршрута —
                        # пробуем
                        # следующий маршрут
                        continue
                    r.raise_for_status()
                    return cast(dict[str, Any], r.json())
                except (httpx.ReadTimeout, httpx.ConnectTimeout) as e:
                    logger.warning(
                        "TonAPIClient timeout: %s %s",
                        url,
                        e,
                    )
                    continue
                except Exception as e:
                    logger.warning(
                        "TonAPIClient route fail: %s %s",
                        url,
                        e,
                    )
                    continue
        # Если ничего не удалось получить — бросим исключение выше
        msg = f"All routes failed for base {base_url}"
        raise RuntimeError(msg)

    async def _fetch_jettons_history(
        self,
        base_url: str,
        account_id: str,
        limit: int,
        since_utime: int | None,
    ) -> dict[str, Any]:
        """Фетч jetton history для аккаунта.

        Используем TonAPI Accounts endpoint:
        /v2/accounts/{account_id}/jettons/history

        Важно: этот endpoint может отсутствовать на некоторых
        fallback-узлах, поэтому ошибки обрабатываются выше.
        """
        # Base already contains /v2; only append /accounts/...
        # Preserve the original case of friendly TON account addresses.
        addr = str(account_id or "").strip()
        headers = {"Accept": "application/json"}
        if self._key:
            headers["Authorization"] = f"Bearer {self._key}"

        params: dict[str, Any] = {"limit": str(int(limit))}
        if since_utime:
            params["start_date"] = str(int(since_utime))

        url = f"{base_url}/accounts/{addr}/jettons/history"
        async with httpx.AsyncClient(
            timeout=self._timeout,
            http2=True,
        ) as client:
            r = await client.get(
                url,
                params=params,
                headers=headers,
            )
            if r.status_code == 404:
                raise RuntimeError("jettons history not supported")
            r.raise_for_status()
            return cast(dict[str, Any], r.json())

    def _unify_jetton_ops(
        self,
        data: dict[str, Any],
        to_address: str,
    ) -> list[TonAPIEvent]:
        """Приводит jettons/history к TonAPIEvent.

        Канон: мы НЕ строим сложную логику на actions/events.
        Мы только пытаемся извлечь:
        - tx_hash
        - sender/recipient
        - jetton master
        - amount (как amount_asset)
        - memo/comment (если есть)
        - timestamp

        Если формат не распознан — возвращаем [].
        """
        addr_to = _norm_addr(to_address)
        ops = None
        if isinstance(data, dict):
            ops = data.get("operations") or data.get("items")

        if not isinstance(ops, list):
            return []

        out: list[TonAPIEvent] = []
        for it in ops:
            if not isinstance(it, dict):
                continue

            tx_hash = str(
                it.get("transaction_hash")
                or it.get("tx_hash")
                or it.get("hash")
                or ""
            )
            if not tx_hash:
                continue

            ts = it.get("timestamp") or it.get("utime") or 0
            try:
                utime = int(ts or 0)
            except Exception:
                utime = 0

            sender = it.get("sender") or it.get("source") or it.get("from") or {}
            recip = it.get("recipient") or it.get("destination") or it.get("to") or {}

            from_addr = _norm_addr(
                sender.get("address")
                if isinstance(sender, dict)
                else sender
            )
            to_addr = _norm_addr(
                recip.get("address")
                if isinstance(recip, dict)
                else recip
            )

            jetton = it.get("jetton") or {}
            master = ""
            if isinstance(jetton, dict):
                master = str(
                    jetton.get("address") or jetton.get("master") or ""
                )
                if isinstance(jetton.get("master"), dict):
                    master = str(
                        jetton.get("master", {}).get("address")
                        or master
                    )
            master = _norm_addr(master)

            amt_raw = (
                it.get("amount")
                or it.get("quantity")
                or it.get("value")
                or "0"
            )
            try:
                amount_asset = Decimal(str(amt_raw))
            except Exception:
                amount_asset = Decimal("0")

            # TonAPI /jettons/history supplies TEP-74 text comments in
            # payload.Value.Text, not in the top-level comment field.
            payload = it.get("payload")
            payload_text = ""
            if isinstance(payload, dict) and payload.get("SumType") == "TextComment":
                value = payload.get("Value")
                if isinstance(value, dict) and isinstance(value.get("Text"), str):
                    payload_text = value["Text"]
            memo = _norm_memo(
                it.get("comment")
                or it.get("memo")
                or it.get("message")
                or payload_text
                or ""
            )

            # Некоторые форматы не возвращают recipient.
            # Для совместимости подставим account, если пусто.
            if not to_addr:
                to_addr = addr_to

            out.append(
                TonAPIEvent(
                    tx_hash=tx_hash,
                    from_address=from_addr,
                    to_address=to_addr,
                    amount=Decimal("0"),
                    memo=memo,
                    utime=utime,
                    asset="JETTON",
                    jetton_master=master,
                    amount_asset=amount_asset,
                )
            )

        return out

    def _unify_events(
        self,
        data: dict[str, Any],
        to_address: str,
    ) -> list[TonAPIEvent]:
        """
        Приводит разные структуры ответов к списку TonAPIEvent.
        Поддерживаем несколько форматов:
          • {"transactions": [...]}
          • {"events": [...]}
          • {"result": [...]}  # toncenter
        """
        addr_to = _norm_addr(to_address)
        out: list[TonAPIEvent] = []

        # --- Ветвь 1: tonapi.io { "transactions": [...] }
        txs = None
        if isinstance(data, dict):
            txs = data.get("transactions")
        if isinstance(txs, list):
            for item in txs:
                ev = self._mk_from_tonapi_transactions(item, addr_to)
                if ev:
                    out.append(ev)

        # --- Ветвь 2: tonapi.io { "events": [...] }
        evs = None
        if isinstance(data, dict):
            evs = data.get("events")
        if isinstance(evs, list):
            for item in evs:
                ev = self._mk_from_tonapi_events(item, addr_to)
                if ev:
                    out.append(ev)

        # --- Ветвь 3: toncenter { "result": [...] }
        res = None
        if isinstance(data, dict):
            res = data.get("result")
        if isinstance(res, list):
            for item in res:
                ev = self._mk_from_toncenter(item, addr_to)
                if ev:
                    out.append(ev)

        return out

    # -----------------------------
    # Конкретные унификаторы под разные семейства API
    # -----------------------------
    def _mk_from_tonapi_transactions(
        self,
        item: dict[str, Any],
        expect_to: str,
    ) -> TonAPIEvent | None:
        """Унификация ответа tonapi /transactions в TonAPIEvent."""
        try:
            tx_hash = str(
                item.get("hash") or item.get("transaction_id") or ""
            )
            if not tx_hash:
                return None

            in_msg = item.get("in_msg") or item.get("in_message") or {}
            from_addr = _norm_addr(
                in_msg.get("source")
                or in_msg.get("from")
                or in_msg.get("src")
            )
            to_addr = _norm_addr(
                in_msg.get("destination")
                or in_msg.get("to")
                or in_msg.get("dst")
                or item.get("account", "")
            )
            amount = _nt_to_ton(
                in_msg.get("value")
                or in_msg.get("amount")
                or item.get("amount")
            )
            memo = _norm_memo(
                in_msg.get("message")
                or in_msg.get("comment")
                or item.get("message")
                or ""
            )
            utime_raw = (
                item.get("utime")
                or item.get("created_at")
                or item.get("timestamp")
            )
            utime = _coerce_utime(utime_raw)

            if expect_to and to_addr and expect_to != to_addr:
                return None
            if amount <= 0:
                return None

            return TonAPIEvent(
                tx_hash=tx_hash,
                from_address=from_addr,
                to_address=to_addr or expect_to,
                amount=amount,
                memo=memo,
                utime=utime,
            )
        except Exception as e:
            logger.debug("unify tonapi.transactions item failed: %s", e)
            return None

    def _mk_from_tonapi_events(
        self,
        item: dict[str, Any],
        expect_to: str,
    ) -> TonAPIEvent | None:
        """Унификация ответа tonapi /events в TonAPIEvent."""
        try:
            tx_hash = str(
                item.get("event_id")
                or item.get("transaction_id")
                or item.get("hash")
                or ""
            )
            if not tx_hash:
                return None

            in_msg = item.get("in_msg") or item.get("in_message") or {}
            if not in_msg and isinstance(item.get("actions"), list):
                for act in item["actions"]:
                    if not isinstance(act, dict):
                        continue
                    act_in = act.get("in_msg")
                    act_msg = act.get("message")
                    in_msg = act_in or act_msg or in_msg

            msg = in_msg or {}
            from_addr = _norm_addr(
                msg.get("source") or msg.get("from") or ""
            )
            to_addr = _norm_addr(
                msg.get("destination") or msg.get("to") or ""
            )
            amount = _nt_to_ton(msg.get("value") or msg.get("amount"))
            memo = _norm_memo(msg.get("message") or msg.get("comment"))

            utime_raw = (
                item.get("utime")
                or item.get("created_at")
                or item.get("timestamp")
            )
            utime = _coerce_utime(utime_raw)

            if expect_to and to_addr and expect_to != to_addr:
                return None
            if amount <= 0:
                return None

            return TonAPIEvent(
                tx_hash=tx_hash,
                from_address=from_addr,
                to_address=to_addr or expect_to,
                amount=amount,
                memo=memo,
                utime=utime,
            )
        except Exception as e:
            logger.debug("unify tonapi.events item failed: %s", e)
            return None

    def _mk_from_toncenter(
        self,
        item: dict[str, Any],
        expect_to: str,
    ) -> TonAPIEvent | None:
        """Унификация toncenter /getTransactions в TonAPIEvent."""
        try:
            tx_id = item.get("transaction_id")
            txh = None
            if isinstance(tx_id, dict):
                txh = tx_id.get("hash")
            if txh is None:
                txh = item.get("hash")

            tx_hash = str(txh or "")
            if not tx_hash:
                return None

            in_msg = item.get("in_msg") or item.get("in_message") or {}
            msg = in_msg or {}
            from_addr = _norm_addr(
                msg.get("source") or msg.get("src") or ""
            )
            to_addr = _norm_addr(
                msg.get("destination") or msg.get("dst") or ""
            )
            amount = _nt_to_ton(msg.get("value") or item.get("value"))
            memo = _norm_memo(msg.get("message") or item.get("comment"))

            utime_raw = (
                item.get("utime")
                or item.get("created_at")
                or item.get("timestamp")
            )
            utime = _coerce_utime(utime_raw)

            if expect_to and to_addr and expect_to != to_addr:
                return None
            if amount <= 0:
                return None

            return TonAPIEvent(
                tx_hash=tx_hash,
                from_address=from_addr,
                to_address=to_addr or expect_to,
                amount=amount,
                memo=memo,
                utime=utime,
            )
        except Exception as e:
            logger.debug("unify toncenter item failed: %s", e)
            return None


def _coerce_utime(raw: Any) -> int:
    """
    Приведение разных представлений времени к unixtime (секунды).
    Поддержка: int/str (секунды), ISO-8601 строка,
    миллисекунды (эвристика).
    """
    if raw is None:
        return int(utcnow().timestamp())
    try:
        if isinstance(raw, int | float):
            v = int(raw)
            # Эвристика: слишком большое число — вероятно миллисекунды
            if v > 2_000_000_000_000:  # 2e12 ~ 2033 год в мс
                return int(v / 1000)
            return v
        if isinstance(raw, str):
            s = raw.strip()
            if s.isdigit():
                v = int(s)
                if v > 2_000_000_000_000:
                    return int(v / 1000)
                return v
            # ISO-8601
            try:
                dt = datetime.fromisoformat(s.replace("Z", " + 00:00"))
                return int(dt.timestamp())
            except Exception as exc:
                logger.debug(
                    "TonAPI: utime iso parse failed: %s",
                    exc,
                )
    except Exception as exc:
        logger.warning(
            "TonAPI: utime parse failed, use now: %s",
            exc,
        )
    # fallback: текущее время
    return int(utcnow().timestamp())


# ====================================================================
# Пояснения:
# • Модуль только читает TON API и нормализует ответы для вотчера.
# • БД не трогает и балансы не меняет.
# • Устойчивость: fallback-узлы + таймауты. Ошибки логируем.
# • Amount может быть в нанотонах — переводим в TON, точность d8.
# • Memo может быть base64 — пытаемся декодировать.
#   При ошибке оставляем как есть.
# • Дедупликация по tx_hash — в пределах страницы;
#   глобальная идемпотентность — в БД (UNIQUE tx_hash) у вотчера.
# ====================================================================
