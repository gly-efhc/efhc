"""Публичные утилиты верхнего уровня.

Назначение:
- форматирование EFHC/kWh с учётом runtime-настроек;
- безопасные конвертации Decimal и ограничение значений;
- sha256/HMAC и генерация реф/идемпотентных ключей;
- геттеры публичного конфига (CORS, webhook URL, TON memo).

Важно:
- без зависимостей от FastAPI/SQLAlchemy;
- точность и округление берутся из core/config_core.py;
- низкоуровневые утилиты: backend/app/core/utils_core.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

# Конфигурация приложения (BaseSettings)
from .core.config_core import get_settings

# Низкоуровневые утилиты (без зависимостей от фреймворков)
from .core.utils_core import (
    clamp as _clamp,
)
from .core.utils_core import (
    decimal_from as _decimal_from,
)
from .core.utils_core import (
    format_decimal_str as _format_decimal_str,
)
from .core.utils_core import (
    gen_idempotency_key as _gen_idempotency_key,
)
from .core.utils_core import (
    gen_ref_code as _gen_ref_code,
)
from .core.utils_core import (
    hmac_sha256_hex as _hmac_sha256_hex,
)
from .core.utils_core import (
    parse_csv_list as _parse_csv_list,
)
from .core.utils_core import (
    parse_kv_thresholds as _parse_kv_thresholds,
)
from .core.utils_core import (
    quantize_decimal as _quantize_decimal,
)
from .core.utils_core import (
    sha256_hex as _sha256_hex,
)
from .core.utils_core import (
    unix_ms as _unix_ms,
)
from .core.utils_core import (
    utcnow as _utcnow,
)

NumberLike = str | int | float | Decimal

# ----------------------------------------------------------------------
# Константы слоя utils (не меняют глобальные настройки Decimal)
# ----------------------------------------------------------------------
_DECIMALS_DEFAULT = 8
# Единый стандарт проекта для fixed-point значений.
_DECIMAL_STEP_8 = Decimal("0.00000001")


# ----------------------------------------------------------------------
# Доступ к runtime-настройкам
# ----------------------------------------------------------------------


def _settings_rounding_mode() -> str:
    """
    Возвращает режим округления из .env (например, "DOWN").
    """
    return get_settings().ROUNDING_MODE or "DOWN"


def _settings_efhc_decimals() -> int:
    """
    Возвращает точность EFHC для UI/форматирования.
    """
    try:
        return int(get_settings().EFHC_DECIMALS)
    except Exception:
        return _DECIMALS_DEFAULT


def _settings_kwh_decimals() -> int:
    """
    Возвращает точность kWh для расчётов.
    """
    try:
        return int(get_settings().KWH_DECIMALS)
    except Exception:
        return _DECIMALS_DEFAULT


def _settings_kwh_display_decimals() -> int:
    """
    Возвращает точность kWh для отображения в интерфейсе.
    """
    try:
        return int(get_settings().KWH_DISPLAY_DECIMALS)
    except Exception:
        return _DECIMALS_DEFAULT


# ----------------------------------------------------------------------
# Обёртки форматирования EFHC/kWh, учитывающие конфиг
# ----------------------------------------------------------------------


def efhc_to_str(
    value: NumberLike,
    *,
    trim_trailing_zeros: bool = True,
) -> str:
    """
    Возвращает строку EFHC согласно настройкам
    (EFHC_DECIMALS, ROUNDING_MODE).
    Пример: efhc_to_str(1.23456789) -> "1.23456789"
    """
    return _format_decimal_str(
        value,
        decimals=_settings_efhc_decimals(),
        trim_trailing_zeros=trim_trailing_zeros,
        rounding=_settings_rounding_mode(),
    )


def kwh_to_str(
    value: NumberLike,
    *,
    trim_trailing_zeros: bool = True,
) -> str:
    """
    Возвращает строку kWh согласно настройкам
    (KWH_DISPLAY_DECIMALS, ROUNDING_MODE).
    Пример: kwh_to_str(0.00000691) -> "0.00000691"
    """
    return _format_decimal_str(
        value,
        decimals=_settings_kwh_display_decimals(),
        trim_trailing_zeros=trim_trailing_zeros,
        rounding=_settings_rounding_mode(),
    )


def quantize_eight(
    value: NumberLike,
    *,
    rounding: str | None = None,
) -> Decimal:
    """
    Округляет число до 8 знаков после запятой (fixed-point),
    с режимом из настроек или заданным явно.
    """
    return _quantize_decimal(
        value,
        decimals=_DECIMALS_DEFAULT,
        rounding=rounding or _settings_rounding_mode(),
    )


def quantize_efhc(value: NumberLike) -> Decimal:
    """
    Округляет значение EFHC согласно настройкам точности/округления.
    """
    return _quantize_decimal(
        value,
        decimals=_settings_efhc_decimals(),
        rounding=_settings_rounding_mode(),
    )


def quantize_kwh(value: NumberLike) -> Decimal:
    """
    Округляет значение kWh согласно настройкам точности/округления
    для расчётов.
    """
    return _quantize_decimal(
        value,
        decimals=_settings_kwh_decimals(),
        rounding=_settings_rounding_mode(),
    )


# ----------------------------------------------------------------------
# Безопасные числовые операции
# ----------------------------------------------------------------------


def decimal_from(value: NumberLike) -> Decimal:
    """
    Безопасно приводит к Decimal (float → через str, чтобы избежать
    артефактов).
    """
    return _decimal_from(value)


def clamp(
    value: NumberLike,
    *,
    min_value: NumberLike | None = None,
    max_value: NumberLike | None = None,
) -> Decimal:
    """
    Ограничивает значение снизу/сверху (включительно).
    """
    return _clamp(value, min_value=min_value, max_value=max_value)


def parse_decimal_8(raw: str | None) -> Decimal | None:
    """
    Парсит строку в Decimal с точностью до 8 знаков. Пустое → None.
    Бросает ValueError при некорректном формате.
    """
    if raw is None or raw == "":
        return None
    try:
        return quantize_eight(_decimal_from(raw))
    except Exception as exc:
        msg = (
            f"Некорректное число: {raw!r}. Ожидается Decimal "
            f"с точностью до 8 знаков."
        )
        raise ValueError(msg) from exc


# ----------------------------------------------------------------------
# Хэши / HMAC и идентификаторы
# ----------------------------------------------------------------------


def sha256_hex(data: str | bytes) -> str:
    """
    SHA-256 в hex для строки/байт.
    """
    return _sha256_hex(data)


def hmac_sha256_hex(
    secret: str | bytes,
    message: str | bytes,
) -> str:
    """
    HMAC-SHA256 в hex (секрет + сообщение).
    """
    return _hmac_sha256_hex(secret, message)


def gen_ref_code(length: int = 8) -> str:
    """
    Короткий реф-код (алфавит без 0/O для читаемости).
    """
    return _gen_ref_code(length=length)


def gen_idempotency_key(prefix: str = "idem", length: int = 24) -> str:
    """
    Идемпотентный ключ вида: idem_<random>.
    """
    return _gen_idempotency_key(prefix=prefix, length=length)


# ----------------------------------------------------------------------
# Работа со временем
# ----------------------------------------------------------------------


def utcnow() -> datetime:
    """
    Текущее время в UTC с tzinfo.
    """
    return _utcnow()


def unix_ms() -> int:
    """
    Unix timestamp в миллисекундах.
    """
    return _unix_ms()


# ----------------------------------------------------------------------
# Публичные срезы настроек и вспомогательные геттеры
# ----------------------------------------------------------------------


def public_frontend_config() -> dict[str, str]:
    """
    Публичный конфиг для фронтенда (без секретов). Строковые значения.
    """
    return get_settings().export_public_frontend_config()


def cors_origins() -> list[str]:
    """
    Разрешённые источники CORS (без дубликатов).
    """
    return get_settings().effective_cors_origins()


def build_tg_webhook_url() -> str | None:
    """
    Итоговый URL webhook для Telegram, если включён и задан BASE_URL.
    """
    return get_settings().build_tg_webhook_url()


def make_ton_memo(tg_id: int, pak_code: str | None = None) -> str:
    """
    MEMO для платежа TON: id<tg_id>[:<pak_code>]
    """
    return get_settings().make_ton_memo(
        tg_id=tg_id,
        pak_code=pak_code,
    )


# ----------------------------------------------------------------------
# Разбор строк и коллекций
# ----------------------------------------------------------------------


def parse_csv_list(s: str | None) -> list[str]:
    """
    Превращает CSV-строку в список (обрезает пробелы, убирает пустые).
    """
    return _parse_csv_list(s)


def parse_kv_thresholds(s: str | None) -> list[tuple[int, Decimal]]:
    """
    Парсер строк вида "10:1,100:10" →
    [(10, Decimal('1')), (100, Decimal('10'))]
    Удобно для пороговых бонусов/награды за рефералов.
    """
    return _parse_kv_thresholds(s)


# ----------------------------------------------------------------------
# Данные о приложении (удобно для health-check/метаданных)
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class AppMeta:
    """
    Небольшой контейнер с публичной информацией о приложении.
    """

    project_name: str
    app_version: str
    api_prefix: str
    env: str

    @classmethod
    def current(cls) -> AppMeta:
        """Текущие публичные метаданные приложения (из настроек)."""
        s = get_settings()
        return cls(
            project_name=s.PROJECT_NAME,
            app_version=s.APP_VERSION,
            api_prefix=s.API_PREFIX,
            env=s.env_normalized,
        )


def app_meta() -> AppMeta:
    """
    Возвращает публичные метаданные приложения.
    """
    return AppMeta.current()


# ----------------------------------------------------------------------
# Публичный интерфейс модуля
# ----------------------------------------------------------------------
__all__ = [
    # типы
    "NumberLike",
    "AppMeta",
    # форматирование и округление
    "efhc_to_str",
    "kwh_to_str",
    "quantize_eight",
    "quantize_efhc",
    "quantize_kwh",
    "decimal_from",
    "clamp",
    "parse_decimal_8",
    # время
    "utcnow",
    "unix_ms",
    # крипто/идентификаторы
    "sha256_hex",
    "hmac_sha256_hex",
    "gen_ref_code",
    "gen_idempotency_key",
    # строки/коллекции
    "parse_csv_list",
    "parse_kv_thresholds",
    # алиасы
    # конфиг-helpers
    "public_frontend_config",
    "cors_origins",
    "build_tg_webhook_url",
    "make_ton_memo",
    "app_meta",
]


# ----------------------------------------------------------------------
# Локальный self-test (запуск: python -m app.utils)
# ----------------------------------------------------------------------
if __name__ == "__main__":
    # Простая дымовая проверка функционала.
    meta = app_meta()
    print("[EFHC][utils] App:", meta)
    print("[EFHC][utils] EFHC str:", efhc_to_str(1.23456789123))
    print("[EFHC][utils] kWh  str:", kwh_to_str(0.000006913456))
    print("[EFHC][utils] Q8    :", quantize_eight("123.456789999"))
    print(
        "[EFHC][utils] clamp :",
        clamp("10.1", min_value="0", max_value="10"),
    )
    print("[EFHC][utils] SHA256:", sha256_hex("hello"))
    print("[EFHC][utils] HMAC  :", hmac_sha256_hex("key", "hello"))
    print("[EFHC][utils] Ref   :", gen_ref_code())
    print("[EFHC][utils] Idem  :", gen_idempotency_key())
    print("[EFHC][utils] CORS  :", cors_origins())
    print("[EFHC][utils] Public:", public_frontend_config())
    print("[EFHC][utils] Webhook:", build_tg_webhook_url())
    print(
        "[EFHC][utils] MEMO  :",
        make_ton_memo(123456789, "pak_100_efhc"),
    )
