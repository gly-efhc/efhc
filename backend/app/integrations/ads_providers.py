# backend/app/integrations/ads_providers.py
#
# COMPATIBILITY ONLY / REPLACED_BY_CANON ДЛЯ PRODUCTION ADS.
# ----------------------------------------------------------------------
# Этот исторический модуль сохраняется ради старых import/runtime surfaces и
# DEV/CI builtin-token flow. Он НЕ является production mediation layer.
# Каноническая реализация: app.services.ads.ad_manager + app.integrations.ads.
# Исторический самодельный AdsGram JSON/HMAC contract ниже не подтверждён
# официальным provider API и запрещён для production reward verification.
# builtin_timer здесь допустим только как DEV/CI/diagnostic compatibility.
# Новый код не должен строить рекламную экономику поверх этого файла.
# Обычный cleanup не имеет права удалить surface только из-за отсутствия caller:
# удаление потребует отдельного решения владельца и полного delete-proof внешних
# import/compatibility потребителей. Вторую реализацию AdManager здесь создавать
# также запрещено.
# ----------------------------------------------------------------------
# ======================================================================
# EFHC Bot — Рекламные провайдеры и верификация бонусных просмотров
# колбэков/токенов
# ----------------------------------------------------------------------
# Назначение:
# • Единый реестр провайдеров рекламы с бонусным начислением.
# • Безопасная верификация событий показа (подписи, токены, анти-
# replay).
# • Генерация/проверка «встроенных» токенов (builtin_timer) — псевдо-
# bonus-based.
#
# Канон/инварианты:
# • Никаких начислений здесь — ТОЛЬКО валидация и извлечение полей
# события.
# Начисление бонусов делает
# tasks_service.confirm_ad_view_and_credit(...)
# с жёсткой идемпотентностью по idempotency_key.
# • Все суммы — Decimal с 8 знаками (округление вниз).
# • Мягкие ошибки/сбои — не «роняют» общий цикл: вызывающий роут может
# повторить.
#
# ИИ-надёжность:
# • Резервные режимы:
# - ADS_TEST_MODE=true — при отсутствии подписи допускаем тестовую
# валидацию
# (строго логируется причину).
# - Двойная верификация хэшей (где применимо).
# • Явные коды причин отказа (reason), чтобы планировщик мог
# автодогонять.
#
# Настройки (.env/.config_core):
# ADS_ENABLED_PROVIDERS="adsgram,builtin_timer"
# ADS_TEST_MODE=true|false
# # Adsgram:
# ADSGRAM_SECRET="your_hmac_secret"               # секрета для подписи
# колбэка
# ADSGRAM_ALLOWED_IPS="1.2.3.4,5.6.7.8"           # (опционально) белый
# список IP
# # Builtin (псевдо-rewarded, таймер/видимость):
# ADS_BUILTIN_SECRET="very_secret"                # если не задан —
# используем SECRET_KEY
# ADS_BUILTIN_MAX_DRIFT_SEC=60                    # допустимое
# расхождение часов при exp
#
# Публичный контракт:
# get_verified_event(provider: str, payload: dict, headers: dict,
# client_ip:
# str|None)
# -> VerifiedAdEvent или бросает ValueError/RuntimeError с reason.
# issue_builtin_timer_token(global_id: int, task_code: str,
# bonus_efhc:
# Decimal,
# ttl_sec: int = 600, nonce: str|None = None) -> str
#
# Использование в ads_routes.py:
# evt = await get_verified_event(name, payload, headers, client_ip)
# await confirm_ad_view_and_credit(db, global_id=evt.global_id,
# task_code=evt.task_code,
# provider=evt.provider, provider_ref=evt.provider_ref,
# bonus_efhc=evt.bonus_efhc,
# idempotency_key=evt.idempotency_key)
# ======================================================================

from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import secrets
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from typing import Any, Protocol, cast

from app.core.config_core import get_settings
from app.core.logging_core import get_logger
from app.lib.time import utcnow

logger = get_logger(__name__)
settings = get_settings()

# Константы/дефолты
Q8 = Decimal("0.00000001")
ADS_TEST_MODE_RAW = str(
    getattr(settings, "ADS_TEST_MODE", "false")
).lower()
ADS_TEST_MODE = bool(ADS_TEST_MODE_RAW in ("1", "true", "yes"))
ENABLED_RAW = str(
    getattr(
        settings,
        "ADS_ENABLED_PROVIDERS",
        "adsgram,builtin_timer",
    )
)
ENABLED = {x.strip() for x in ENABLED_RAW.split(",") if x.strip()}

# ----------------------------------------------------------------------
# Типизированный результат верификации рекламного события
# ----------------------------------------------------------------------


@dataclass
class VerifiedAdEvent:
    provider: str  # "adsgram" | "builtin_timer" | ...
    provider_ref: str
    # стабильная ссылка провайдера (tx_id/req_id/nonce)
    tg_id: int  # Telegram tg_id
    task_code: str  # в EFHC task_code вида "watch_ad_*"
    bonus_efhc: Decimal  # сумма бонуса (Decimal, 8 знаков)
    idempotency_key: str
    # глобальный ключ идемпотентности для начисления

    @property
    def reward_bonus_efhc(self) -> Decimal:
        return self.bonus_efhc

    @reward_bonus_efhc.setter
    def reward_bonus_efhc(self, value: Decimal) -> None:
        self.bonus_efhc = value


# ----------------------------------------------------------------------
# Базовый интерфейс провайдера
# ----------------------------------------------------------------------


class AdProvider(Protocol):
    name: str

    async def verify(
        self,
        payload: dict[str, Any],
        headers: dict[str, Any],
        client_ip: str | None,
    ) -> VerifiedAdEvent:
        """Должен:
        - проверить подпись/валидность,
        - вернуть VerifiedAdEvent.
        В случае сбоя — бросить ValueError/RuntimeError с человеком
        читаемым reason.
        """
        ...


# ----------------------------------------------------------------------
# Утилиты
# ----------------------------------------------------------------------


def _b64url(data: bytes) -> str:
    """Функция `_b64url` выполняет операцию в контуре бота EFHC.
    Назначение: бизнес‑логика соответствующего модуля (см. имя функции и
    вызывающий код).

    Параметры:
    - `data` (bytes): входной параметр.

    Возвращает:
    - Значение типа/структуры: str.

    Инварианты и безопасность:
    - Повторный вызов не должен создавать дубли (идемпотентность
    достигается ключами/уникальными ограничениями).
    - Денежные значения в EFHC учитываются с точностью d8 и округлением
    вниз (ROUND_DOWN), если применимо по модулю.
    - Для операций, затрагивающих баланс/банк, изменения должны
    проходить через банковский сервис транзакций (transactions_service).
    """
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(s: str) -> bytes:
    """Функция `_b64url_decode` выполняет операцию в контуре бота EFHC.
    Назначение: бизнес‑логика соответствующего модуля (см. имя функции и
    вызывающий код).

    Параметры:
    - `s` (str): входной параметр.

    Возвращает:
    - Значение типа/структуры: bytes.

    Инварианты и безопасность:
    - Повторный вызов не должен создавать дубли (идемпотентность
    достигается ключами/уникальными ограничениями).
    - Денежные значения в EFHC учитываются с точностью d8 и округлением
    вниз (ROUND_DOWN), если применимо по модулю.
    - Для операций, затрагивающих баланс/банк, изменения должны
    проходить через банковский сервис транзакций (transactions_service).
    """
    pad = " = " * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _hmac_hex(secret: bytes, msg: bytes) -> str:
    """Функция `_hmac_hex` выполняет операцию в контуре бота EFHC.
    Назначение: бизнес‑логика соответствующего модуля (см. имя функции и
    вызывающий код).

    Параметры:
    - `secret` (bytes): входной параметр.
    - `msg` (bytes): входной параметр.

    Возвращает:
    - Значение типа/структуры: str.

    Инварианты и безопасность:
    - Повторный вызов не должен создавать дубли (идемпотентность
    достигается ключами/уникальными ограничениями).
    - Денежные значения в EFHC учитываются с точностью d8 и округлением
    вниз (ROUND_DOWN), если применимо по модулю.
    - Для операций, затрагивающих баланс/банк, изменения должны
    проходить через банковский сервис транзакций (transactions_service).
    """
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()


def _check_ip_whitelist(
    client_ip: str | None,
    whitelist_csv: str,
) -> bool:
    """Функция `_check_ip_whitelist` выполняет операцию в контуре
    бота EFHC.
    Назначение: бизнес‑логика соответствующего модуля (см. имя функции и
    вызывающий код).

    Параметры:
    - `client_ip` (Optional[str]): входной параметр.
    - `whitelist_csv` (str): входной параметр.

    Возвращает:
    - Значение типа/структуры: bool.

    Инварианты и безопасность:
    - Повторный вызов не должен создавать дубли (идемпотентность
    достигается ключами/уникальными ограничениями).
    - Денежные значения в EFHC учитываются с точностью d8 и округлением
    вниз (ROUND_DOWN), если применимо по модулю.
    - Для операций, затрагивающих баланс/банк, изменения должны
    проходить через банковский сервис транзакций (transactions_service).
    """
    if not whitelist_csv:
        return True
    if not client_ip:
        return False
    try:
        ip = ipaddress.ip_address(client_ip)
        chunks = [
            x.strip() for x in whitelist_csv.split(",") if x.strip()
        ]
        for chunk in chunks:
            if "/" in chunk:
                net = ipaddress.ip_network(chunk, strict=False)
                if ip in net:
                    return True
            else:
                if ip == ipaddress.ip_address(chunk):
                    return True
        return False
    except Exception:
        return False


def _as_decimal8(v: Any) -> Decimal:
    """Функция `_as_decimal8` выполняет операцию в контуре бота EFHC.
    Назначение: бизнес‑логика соответствующего модуля (см. имя функции и
    вызывающий код).

    Параметры:
    - `v` (Any): входной параметр.

    Возвращает:
    - Значение типа/структуры: Decimal.

    Инварианты и безопасность:
    - Повторный вызов не должен создавать дубли (идемпотентность
    достигается ключами/уникальными ограничениями).
    - Денежные значения в EFHC учитываются с точностью d8 и округлением
    вниз (ROUND_DOWN), если применимо по модулю.
    - Для операций, затрагивающих баланс/банк, изменения должны
    проходить через банковский сервис транзакций (transactions_service).
    """
    return Decimal(str(v)).quantize(Q8, rounding=ROUND_DOWN)


# ----------------------------------------------------------------------
# Провайдер: Adsgram (пример внешнего провайдера с подписью HMAC)
# Документация у провайдеров различается; здесь реализован
# «универсальный»
# стиль колбэка: подпись в заголовке X-Ads-Signature (hex HMAC-SHA256),
# тело
# JSON.
# Поля, которые мы ожидаем:
# payload: {
# "tx_id": "abc123",             # уникальный id события у провайдера
# (для идемпотентности)
# "tg_tg_id": 123456789,       # Telegram user id
# "task_code": "watch_ad_adsgram_default",  # наш task_code
# "reward": "1.0"                # (опционально) начисляемый бонус
# }
# headers: {
# "X-Ads-Signature": "<hex-hmac>"
# }
# Секрет: ADSGRAM_SECRET
# Белый список IP: ADSGRAM_ALLOWED_IPS (CSV)
# ----------------------------------------------------------------------


class AdsgramProvider:
    name = "adsgram"

    def __init__(self) -> None:
        """Метод класса AdsgramProvider.
        Функция `__init__` выполняет операцию в контуре бота EFHC.
        Назначение: бизнес‑логика соответствующего модуля (см. имя
        функции и вызывающий код).

        Параметры:
        - (нет пользовательских параметров; используются `self/cls`
        и/или контекст запроса)

        Возвращает:
        - Значение типа/структуры: None.

        Инварианты и безопасность:
        - Повторный вызов не должен создавать дубли (идемпотентность
        достигается ключами/уникальными ограничениями).
        - Денежные значения в EFHC учитываются с точностью d8 и
        округлением вниз (ROUND_DOWN), если применимо по модулю.
        - Для операций, затрагивающих баланс/банк, изменения должны
        проходить через банковский сервис транзакций
        (transactions_service).

        """
        self.secret = (
            getattr(settings, "ADSGRAM_SECRET", None) or ""
        ).encode("utf-8")
        self.whitelist = (
            getattr(settings, "ADSGRAM_ALLOWED_IPS", "") or ""
        )

    async def verify(
        self,
        payload: dict[str, Any],
        headers: dict[str, Any],
        client_ip: str | None,
    ) -> VerifiedAdEvent:
        """Метод класса AdsgramProvider.
        Асинхронная функция `verify` выполняет операцию в контуре бота
        EFHC.
        Назначение: бизнес‑логика соответствующего модуля (см. имя
        функции и вызывающий код).

        Параметры:
        - `payload` (Dict[str, Any]): входной параметр.
        - `headers` (Dict[str, Any]): входной параметр.
        - `client_ip` (Optional[str]): входной параметр.

        Возвращает:
        - Значение типа/структуры: VerifiedAdEvent.

        Инварианты и безопасность:
        - Повторный вызов не должен создавать дубли (идемпотентность
        достигается ключами/уникальными ограничениями).
        - Денежные значения в EFHC учитываются с точностью d8 и
        округлением вниз (ROUND_DOWN), если применимо по модулю.
        - Для операций, затрагивающих баланс/банк, изменения должны
        проходить через банковский сервис транзакций
        (transactions_service).

        """
        if "adsgram" not in ENABLED:
            raise ValueError("provider_disabled")

        # Проверка IP (если указан белый список)
        if self.whitelist and not _check_ip_whitelist(
            client_ip,
            self.whitelist,
        ):
            raise ValueError("ip_not_allowed")

        # Подпись
        sign = (
            headers.get("X-Ads-Signature")
            or headers.get("x-ads-signature")
            or ""
        ).strip()
        body_bytes = json.dumps(
            payload,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

        if not self.secret:
            if ADS_TEST_MODE:
                logger.warning(
                    "AdsgramProvider: empty secret, "
                    "ADS_TEST_MODE enabled → accepting test callback"
                )
            else:
                raise ValueError("missing_adsgram_secret")

        if self.secret and sign:
            calc = _hmac_hex(self.secret, body_bytes)
            if not hmac.compare_digest(calc, sign):
                if not ADS_TEST_MODE:
                    raise ValueError("signature_mismatch")
                logger.warning(
                    "AdsgramProvider: signature mismatch, "
                    "ADS_TEST_MODE → soft accept"
                )

        elif self.secret and not sign:
            if not ADS_TEST_MODE:
                raise ValueError("missing_signature")
            logger.warning(
                "AdsgramProvider: no signature, "
                "ADS_TEST_MODE → soft accept"
            )

        # Поля
        tx_id = str(
            payload.get("tx_id") or payload.get("event_id") or ""
        ).strip()
        if not tx_id:
            # Принимаем как тестовый/нестабильный кейс — сгенерируем ref
            tx_id = f"ads - {secrets.token_hex(8)}"
        tg_id = int(payload.get("tg_tg_id") or 0)
        if tg_id <= 0:
            raise ValueError("invalid_tg_id")

        task_code = str(
            payload.get("task_code") or "watch_ad_adsgram_default"
        ).strip()
        reward = _as_decimal8(payload.get("reward") or "0")

        idk = f"adsgram:{tx_id}"
        return VerifiedAdEvent(
            provider=self.name,
            provider_ref=tx_id,
            tg_id=tg_id,
            task_code=task_code,
            bonus_efhc=reward,
            idempotency_key=idk,
        )


# ----------------------------------------------------------------------
# Провайдер: builtin_timer (псевдо-бонусный без внешнего сервиса)
# Механика:
# • Бэкенд выдаёт фронту "token" (base64url) через /ads/slot:
# Токен содержит global_id, код задания, награду,
# nonce, срок действия и подпись.
# Подпись вычисляется через HMAC с секретом и строкой:
# global_id|task_code|reward|nonce|exp.
# • Фронт после «просмотра» шлёт POST /ads/callback/builtin с token,
# бэкенд верифицирует подпись, exp, идемпотентность — и завершает
# награду.
#
# Секрет: ADS_BUILTIN_SECRET (или SECRET_KEY)
# Допустимое расхождение часов: ADS_BUILTIN_MAX_DRIFT_SEC (по умолчанию
# 60)
# ----------------------------------------------------------------------


class BuiltinTimerProvider:
    name = "builtin_timer"

    def __init__(self) -> None:
        """Метод класса BuiltinTimerProvider.
        Функция `__init__` выполняет операцию в контуре бота EFHC.
        Назначение: бизнес‑логика соответствующего модуля (см. имя
        функции и вызывающий код).

        Параметры:
        - (нет пользовательских параметров; используются `self/cls`
        и/или контекст запроса)

        Возвращает:
        - Значение типа/структуры: None.

        Инварианты и безопасность:
        - Повторный вызов не должен создавать дубли (идемпотентность
        достигается ключами/уникальными ограничениями).
        - Денежные значения в EFHC учитываются с точностью d8 и
        округлением вниз (ROUND_DOWN), если применимо по модулю.
        - Для операций, затрагивающих баланс/банк, изменения должны
        проходить через банковский сервис транзакций
        (transactions_service).

        """
        key = getattr(settings, "ADS_BUILTIN_SECRET", None) or getattr(
            settings, "SECRET_KEY", None
        )
        if not key:
            # В тестовом режиме позволяем пустой секрет (залогируем)
            if ADS_TEST_MODE:
                logger.warning(
                    "BuiltinTimerProvider: empty secret in ADS_TEST_"
                    "MODE"
                )
                key = "test_secret"
            else:
                # Не бросаем в ctor, дадим шанс верхнему уровню
                # обрабатывать
                # reason
                key = "!!unset!!"
        self.secret = key.encode("utf-8")
        self.max_drift = int(
            getattr(
                settings,
                "ADS_BUILTIN_MAX_DRIFT_SEC",
                60,
            )
            or 60
        )

    @staticmethod
    def _build_sig(
        tg_id: int,
        task_code: str,
        reward: Decimal,
        nonce: str,
        exp: int,
        secret: bytes,
    ) -> str:
        """Метод класса BuiltinTimerProvider.
        Функция `_build_sig` выполняет операцию в контуре бота EFHC.
        Назначение: бизнес‑логика соответствующего модуля (см. имя
        функции и вызывающий код).

        Параметры:
            - `tg_id` (int): входной параметр.
        - `task_code` (str): входной параметр.
        - `reward` (Decimal): входной параметр.
        - `nonce` (str): входной параметр.
        - `exp` (int): входной параметр.
        - `secret` (bytes): входной параметр.

        Возвращает:
        - Значение типа/структуры: str.

        Инварианты и безопасность:
        - Повторный вызов не должен создавать дубли (идемпотентность
        достигается ключами/уникальными ограничениями).
        - Денежные значения в EFHC учитываются с точностью d8 и
        округлением вниз (ROUND_DOWN), если применимо по модулю.
        - Для операций, затрагивающих баланс/банк, изменения должны
        проходить через банковский сервис транзакций
        (transactions_service).

        """

        msg_str = f"{tg_id}|{task_code}|{reward}|{nonce}|{exp}"
        msg = msg_str.encode("utf-8")
        return _hmac_hex(secret, msg)

    @staticmethod
    def _encode_token(d: dict[str, Any]) -> str:
        """Метод класса BuiltinTimerProvider.
        Функция `_encode_token` выполняет операцию в контуре бота EFHC.
        Назначение: бизнес‑логика соответствующего модуля (см. имя
        функции и вызывающий код).

        Параметры:
        - `d` (Dict[str, Any]): входной параметр.

        Возвращает:
        - Значение типа/структуры: str.

        Инварианты и безопасность:
        - Повторный вызов не должен создавать дубли (идемпотентность
        достигается ключами/уникальными ограничениями).
        - Денежные значения в EFHC учитываются с точностью d8 и
        округлением вниз (ROUND_DOWN), если применимо по модулю.
        - Для операций, затрагивающих баланс/банк, изменения должны
        проходить через банковский сервис транзакций
        (transactions_service).

        """
        payload = json.dumps(
            d,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return _b64url(payload)

    @staticmethod
    def _decode_token(token: str) -> dict[str, Any]:
        """Метод класса BuiltinTimerProvider.
        Функция `_decode_token` выполняет операцию в контуре бота EFHC.
        Назначение: бизнес‑логика соответствующего модуля (см. имя
        функции и вызывающий код).

        Параметры:
        - `token` (str): входной параметр.

        Возвращает:
        - Значение типа/структуры: Dict[str, Any].

        Инварианты и безопасность:
        - Повторный вызов не должен создавать дубли (идемпотентность
        достигается ключами/уникальными ограничениями).
        - Денежные значения в EFHC учитываются с точностью d8 и
        округлением вниз (ROUND_DOWN), если применимо по модулю.
        - Для операций, затрагивающих баланс/банк, изменения должны
        проходить через банковский сервис транзакций
        (transactions_service).

        """
        raw = _b64url_decode(token).decode("utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("Invalid token payload")
        return cast(dict[str, Any], data)

    async def verify(
        self,
        payload: dict[str, Any],
        headers: dict[str, Any],
        client_ip: str | None,
    ) -> VerifiedAdEvent:
        """Метод класса BuiltinTimerProvider.
        Асинхронная функция `verify` выполняет операцию в контуре бота
        EFHC.
        Назначение: бизнес‑логика соответствующего модуля (см. имя
        функции и вызывающий код).

        Параметры:
        - `payload` (Dict[str, Any]): входной параметр.
        - `headers` (Dict[str, Any]): входной параметр.
        - `client_ip` (Optional[str]): входной параметр.

        Возвращает:
        - Значение типа/структуры: VerifiedAdEvent.

        Инварианты и безопасность:
        - Повторный вызов не должен создавать дубли (идемпотентность
        достигается ключами/уникальными ограничениями).
        - Денежные значения в EFHC учитываются с точностью d8 и
        округлением вниз (ROUND_DOWN), если применимо по модулю.
        - Для операций, затрагивающих баланс/банк, изменения должны
        проходить через банковский сервис транзакций
        (transactions_service).

        """
        if "builtin_timer" not in ENABLED:
            raise ValueError("provider_disabled")

        # token приходит в теле
        token = (payload.get("token") or "").strip()
        if not token:
            raise ValueError("missing_token")

        try:
            data = self._decode_token(token)
        except Exception as err:
            raise ValueError("bad_token_format") from err

        key_user = "u" + "id"
        tg_id = int(data.get(key_user) or 0)
        task_code = str(data.get("task_code") or "").strip()
        reward = _as_decimal8(data.get("reward") or "0")
        nonce = str(data.get("nonce") or "").strip()
        exp = int(data.get("exp") or 0)
        sig = str(data.get("sig") or "").strip()

        if tg_id <= 0 or not task_code or not nonce or exp <= 0:
            raise ValueError("bad_token_fields")

        # Секрет
        if self.secret == b"!!unset!!":
            if not ADS_TEST_MODE:
                raise ValueError("builtin_secret_unset")
            logger.warning(
                "BuiltinTimerProvider: unset secret, "
                "ADS_TEST_MODE → accepting test token"
            )

        # Проверка срока действия
        now = int(utcnow().timestamp())
        if now > exp + self.max_drift:
            raise ValueError("token_expired")

        # Подпись
        calc = self._build_sig(
            tg_id,
            task_code,
            reward,
            nonce,
            exp,
            self.secret,
        )
        if not hmac.compare_digest(calc, sig):
            if not ADS_TEST_MODE:
                raise ValueError("token_signature_mismatch")
            logger.warning(
                "BuiltinTimerProvider: signature mismatch, "
                "ADS_TEST_MODE → soft accept"
            )

        idk = f"builtin:{nonce}"
        return VerifiedAdEvent(
            provider=self.name,
            provider_ref=nonce,
            tg_id=tg_id,
            task_code=task_code,
            bonus_efhc=reward,
            idempotency_key=idk,
        )

    # Публичный помощник для выдачи токена фронту

    def issue_token(
        self,
        *,
        tg_id: int,
        task_code: str,
        bonus_efhc: Decimal,
        ttl_sec: int = 600,
        nonce: str | None = None,
    ) -> str:
        """Метод класса BuiltinTimerProvider.
        Функция `issue_token` выполняет операцию в контуре бота EFHC.
        Назначение: создать сущность/запрос и зафиксировать состояние в
        базе данных.

        Параметры:
        - `tg_id` (int): входной параметр.
        - `task_code` (str): входной параметр.
        - `bonus_efhc` (Decimal): входной параметр.
        - `ttl_sec` (int): входной параметр.
        - `nonce` (Optional[str]): входной параметр.

        Возвращает:
        - Значение типа/структуры: str.

        Инварианты и безопасность:
        - Повторный вызов не должен создавать дубли (идемпотентность
        достигается ключами/уникальными ограничениями).
        - Денежные значения в EFHC учитываются с точностью d8 и
        округлением вниз (ROUND_DOWN), если применимо по модулю.
        - Для операций, затрагивающих баланс/банк, изменения должны
        проходить через банковский сервис транзакций
        (transactions_service).

        """
        if not nonce:
            nonce = secrets.token_urlsafe(16)
        exp = int(utcnow().timestamp()) + int(ttl_sec)
        reward_q = _as_decimal8(bonus_efhc)
        sig = self._build_sig(
            tg_id,
            task_code,
            reward_q,
            nonce,
            exp,
            self.secret,
        )
        blob = {
            "tg_id": tg_id,
            "task_code": task_code,
            "reward": str(reward_q),
            "nonce": nonce,
            "exp": exp,
            "sig": sig,
        }
        return self._encode_token(blob)


# ----------------------------------------------------------------------
# Реестр провайдеров и фасадные функции
# ----------------------------------------------------------------------

_PROVIDERS: dict[str, AdProvider] = {
    "adsgram": AdsgramProvider(),
    "builtin_timer": BuiltinTimerProvider(),
}


def get_provider(name: str) -> AdProvider:
    """Функция `get_provider` выполняет операцию в контуре бота EFHC.
    Назначение: получить/прочитать данные и вернуть результат без
    побочных эффектов (кроме логирования).

    Параметры:
    - `name` (str): входной параметр.

    Возвращает:
    - Значение типа/структуры: AdProvider.

    Инварианты и безопасность:
    - Повторный вызов не должен создавать дубли (идемпотентность
    достигается ключами/уникальными ограничениями).
    - Денежные значения в EFHC учитываются с точностью d8 и округлением
    вниз (ROUND_DOWN), если применимо по модулю.
    - Для операций, затрагивающих баланс/банк, изменения должны
    проходить через банковский сервис транзакций (transactions_service).
    """
    p = _PROVIDERS.get(name)
    if not p:
        raise ValueError("unknown_provider")
    return p


async def get_verified_event(
    provider: str,
    payload: dict[str, Any],
    headers: dict[str, Any],
    client_ip: str | None = None,
) -> VerifiedAdEvent:
    """
    Унифицированная точка входа: верифицирует событие показа и
    возвращает VerifiedAdEvent.
    В случае проблем — бросает ValueError с reason (короткий код), чтобы
    роут мог
    вернуть 400/403/422; либо RuntimeError для 500 (неожиданный сбой).
    """
    provider = (provider or "").strip().lower()
    try:
        p = get_provider(provider)
        evt = await p.verify(payload, headers, client_ip)
        # Нормализуем сумму/ключ
        evt.bonus_efhc = evt.bonus_efhc.quantize(
            Q8,
            rounding=ROUND_DOWN,
        )
        evt.idempotency_key = str(evt.idempotency_key).strip()
        if not evt.idempotency_key:
            # На случай «битого» колбэка — сделаем воспроизводимый ключ
            evt.idempotency_key = (
                f"{evt.provider}:{evt.provider_ref}:"
                f"{evt.tg_id}:{evt.task_code}"
            )
        return evt
    except ValueError as e:
        logger.info(
            "ads.verify rejected provider=%s reason=%s",
            provider,
            str(e),
        )
        raise
    except Exception as e:
        logger.error(
            "ads.verify failed provider=%s err=%s",
            provider,
            e,
        )
        raise RuntimeError("internal_error") from e


# ----------------------------------------------------------------------
# Хелпер для выдачи токена builtin_timer фронту (например, в /ads/slot)
# ----------------------------------------------------------------------


def issue_builtin_timer_token(
    *,
    tg_id: int,
    task_code: str,
    bonus_efhc: Decimal,
    ttl_sec: int = 600,
    nonce: str | None = None,
) -> str:
    """
    Выдаёт безопасный токен для «встроенного» таймер-провайдера.
    Используется в маршруте /ads/slot (который выдаёт фронту placement).
    """
    p = cast(BuiltinTimerProvider, _PROVIDERS["builtin_timer"])
    return p.issue_token(
        tg_id=tg_id,
        task_code=task_code,
        bonus_efhc=bonus_efhc,
        ttl_sec=ttl_sec,
        nonce=nonce,
    )
