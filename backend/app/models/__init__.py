from __future__ import annotations

import importlib
import inspect

from app.core.logging_core import get_logger

from .base import SCHEMA, Base, TimestampMixin

logger = get_logger(__name__)


# ----------------------------------------------------------------------
# Автоподключение модулей с моделями.
# ----------------------------------------------------------------------
# Примечание: исторически встречались разные имена файлов (ед/мн.
# число).
# Чтобы не «ронять» импорт при неполном наборе моделей, пробуем
# варианты.
_MODEL_MODULE_CANDIDATES: list[str] = [
    # ядро пользователей/транзакций/TON-логов
    "user_models",
    "identity_models",
    "auth_models",
    "transactions_models",
    "ton_logs_models",
    "bank_balance_models",
    "bank_metrics_snapshot_models",
    "settings_models",
    # панели/архив/ранги/скины/достижения/вывод
    "panels_models",
    "skins_models",
    "achievements_models",
    "withdraw_models",
    # рефералы
    "referral_models",
    "referral_codes_models",
    # магазин/заказы/платёжные интенты
    "shop_models",
    "hub_links_models",
    "payment_intents_models",
    "shop_payment_tx_hash_lock_models",
    # задачи/планировщик/внешние события
    "tasks_models",
    "scheduler_models",
    "external_events_models",
    "system_templates_models",
    "outcome_models",
    # админ-таблицы/кошельки/реклама
    "admin_models",
    "wallets_models",
    "ads_models",
]


def _safe_import(module_name: str):
    """Импортирует app.models.<module_name>.

    При ошибке возвращает None (не «роняем» процесс на неполном наборе).
    """

    full = f"app.models.{module_name}"
    try:
        mod = importlib.import_module(full)
        logger.debug("models: imported %s", full)
        return mod
    except Exception as exc:  # pragma: no cover
        logger.debug("models: skip %s (%s)", full, exc)
        return None


def _collect_model_classes(module) -> dict[str, type[Base]]:
    """Возвращает {ClassName: Class} для моделей SQLAlchemy.

    Критерий: подкласс Base + объявлен __tablename__.
    """

    registry: dict[str, type[Base]] = {}
    if not module:
        return registry

    for name, obj in vars(module).items():
        if not inspect.isclass(obj):
            continue
        if issubclass(obj, Base) and hasattr(obj, "__tablename__"):
            registry[name] = obj

    return registry


# ----------------------------------------------------------------------
# Строим глобальный реестр моделей.
# ----------------------------------------------------------------------
MODEL_REGISTRY: dict[str, type[Base]] = {}
MODEL_MODULES_LOADED: list[str] = []

for candidate in _MODEL_MODULE_CANDIDATES:
    mod = _safe_import(candidate)
    if not mod:
        continue
    classes = _collect_model_classes(mod)
    if classes:
        MODEL_REGISTRY.update(classes)
        MODEL_MODULES_LOADED.append(candidate)


def get_model(name: str) -> type[Base] | None:
    """Возвращает класс модели по имени Python-класса."""

    return MODEL_REGISTRY.get(name)


def list_models() -> list[tuple[str, str]]:
    """Список (ClassName, __tablename__) по registry."""

    out: list[tuple[str, str]] = []
    for cls_name, cls in sorted(
        MODEL_REGISTRY.items(),
        key=lambda kv: kv[0].lower(),
    ):
        out.append((cls_name, getattr(cls, "__tablename__", "?")))
    return out


def models_health() -> dict[str, object]:
    """Минимальная диагностика полноты набора моделей."""

    required_class_names = [
        "User",
        "UserIdentity",
        "AuthChallenge",
        "AuthSession",
        "UserRole",
        "EfhcTransferLog",
        "TonInboxLog",
        "Panel",
        "ShopOrder",
    ]

    present_pairs = list_models()
    present_classes = {cls for cls, _ in present_pairs}
    missing_classes = [
        rc for rc in required_class_names if rc not in present_classes
    ]

    ok = len(missing_classes) == 0
    report = {
        "ok": ok,
        "missing_classes": missing_classes,
        "loaded_modules": list(MODEL_MODULES_LOADED),
        "present": present_pairs,
        "schema": SCHEMA,
    }

    if not ok:
        logger.warning("models_health: missing=%s", missing_classes)
    else:
        logger.info(
            "models_health: OK, %d models in %d modules",
            len(present_pairs),
            len(MODEL_MODULES_LOADED),
        )
    return report


__all__ = [
    "Base",
    "TimestampMixin",
    "SCHEMA",
    "MODEL_REGISTRY",
    "MODEL_MODULES_LOADED",
    "get_model",
    "list_models",
    "models_health",
]
