from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import timedelta
from decimal import ROUND_DOWN, Decimal
from typing import Any

from app.core.config_core import get_settings
from app.core.database_core import get_session_factory
from app.core.logging_core import get_logger
from app.lib.time import utcnow
from app.models.admin_models import IdempotencyKey
from fastapi import FastAPI, Header, HTTPException, Request, status
from sqlalchemy import func, or_, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

logger = get_logger(__name__)
settings = get_settings()

# --------------------------------------------------------------------
# Внутренние константы канона (сравниваем с .env)
# --------------------------------------------------------------------
Q8 = Decimal(1).scaleb(-8)  # точность Decimal(8), округление вниз

GEN_PER_SEC_BASE_KWH_CANON = Decimal("0.00000692").quantize(
    Q8,
    rounding=ROUND_DOWN,
)
GEN_PER_SEC_VIP_KWH_CANON = Decimal("0.00000741").quantize(
    Q8,
    rounding=ROUND_DOWN,
)
EFHC_KWH_RATE_CANON = Decimal("1.0").quantize(
    Q8,
    rounding=ROUND_DOWN,
)

# --------------------------------------------------------------------
# Исключения и DTO для нарушений канона
# --------------------------------------------------------------------


class LockViolation(RuntimeError):
    """
    Нарушение канона / архитектурных запретов.

    Важно:
    • Это ОШИБКА ПРОЕКТА, а не «ошибка пользователя».
    • Должна отлавливаться верхним слоем и логироваться,
      но не маскироваться под 500 без объяснения.
    """


@dataclass(frozen=True)
class BalanceSnapshot:
    """
    Снимок пользовательского баланса для проверки «не уйти в минус».

    main:
        Основной баланс EFHC (панели, операции, вывод).
    bonus:
        Бонусный баланс EFHC (рефералка, задания и т.п.).
    """

    main: Decimal
    bonus: Decimal


# --------------------------------------------------------------------
# Публичные проверки — импортируются сервисами / роутами
# --------------------------------------------------------------------


def assert_per_sec_canon() -> None:
    """
    Проверяет, что в конфиге заданы канонические per-sec ставки
    генерации и фиксированный курс 1:1.
    и фиксированный курс 1:1.

    Вызывается на старте (init_system_locks).
    При несоответствии поднимает
    LockViolation и не даёт приложению запуститься.
    """
    # A deployment must supply both server-side rates explicitly.
    # Pydantic model_fields_set includes values from protected .env or process ENV.
    if getattr(settings, "env_normalized", "local") in {
        "prod", "production", "stage", "staging",
    }:
        provided = getattr(settings, "model_fields_set", set())
        missing = [
            name for name in ("GEN_PER_SEC_BASE_KWH", "GEN_PER_SEC_VIP_KWH")
            if name not in provided
        ]
        if missing:
            raise LockViolation(
                "Generation rate ENV must be explicitly configured: "
                + ", ".join(missing)
            )

    # Avoid a 9th decimal place passing silently via ROUND_DOWN.
    if (
        str(settings.GEN_PER_SEC_BASE_KWH) != "0.00000692"
        or str(settings.GEN_PER_SEC_VIP_KWH) != "0.00000741"
    ):
        raise LockViolation(
            "GEN_PER_SEC_BASE_KWH and GEN_PER_SEC_VIP_KWH "
            "must match the exact canonical D8 strings"
        )

    try:
        base = Decimal(str(settings.GEN_PER_SEC_BASE_KWH))
        vip = Decimal(str(settings.GEN_PER_SEC_VIP_KWH))
        rate = Decimal(str(settings.EFHC_KWH_RATE))
    except Exception as exc:  # noqa: BLE001
        raise LockViolation(
            f"Некорректные per-sec ставки или курс в настройках: {exc}",
        ) from exc

    base_q = base.quantize(Q8, rounding=ROUND_DOWN)
    vip_q = vip.quantize(Q8, rounding=ROUND_DOWN)
    rate_q = rate.quantize(Q8, rounding=ROUND_DOWN)

    if base_q != GEN_PER_SEC_BASE_KWH_CANON:
        raise LockViolation(
            "GEN_PER_SEC_BASE_KWH≠"
            f"{GEN_PER_SEC_BASE_KWH_CANON}. Найдено: {base}. "
            "Допустимо только каноническое значение.",
        )

    if vip_q != GEN_PER_SEC_VIP_KWH_CANON:
        raise LockViolation(
            "GEN_PER_SEC_VIP_KWH≠"
            f"{GEN_PER_SEC_VIP_KWH_CANON}. Найдено: {vip}. "
            "Допустимо только каноническое значение.",
        )

    if rate_q != EFHC_KWH_RATE_CANON:
        raise LockViolation(
            f"EFHC_KWH_RATE должен быть ровно 1.0. Найдено: {rate}.",
        )


def get_rate_base_d8() -> Decimal:
    """SSOT base per-sec rate as Decimal(d8), ROUND_DOWN."""
    return Decimal(str(settings.GEN_PER_SEC_BASE_KWH)).quantize(
        Q8,
        rounding=ROUND_DOWN,
    )


def get_rate_vip_d8() -> Decimal:
    """SSOT VIP per-sec rate as Decimal(d8), ROUND_DOWN."""
    return Decimal(str(settings.GEN_PER_SEC_VIP_KWH)).quantize(
        Q8,
        rounding=ROUND_DOWN,
    )


def assert_system_locks() -> None:
    """Единая точка стартовой проверки канона.

    Используется слоем запуска (backend.run) как компактная проверка
    «можно ли поднимать процесс». Без middleware и привязки к ASGI.
    """
    assert_per_sec_canon()


def assert_exchange_direction_kwh_to_efhc_only(
    *,
    reverse: bool = False,
) -> None:
    """
    Запрещает обратную конверсию EFHC→kWh.

    Сервис обмена должен вызывать без аргументов; передача reverse=True
    приводит к немедленной ошибке канона.
    """
    if reverse:
        raise LockViolation(
            "Обратная конверсия EFHC→kWh запрещена каноном EFHC.",
        )


def assert_p2p_forbidden(
    sender_tg_id: int | None,
    receiver_tg_id: int | None,
) -> None:
    """
    Запрещает любые прямые переводы user→user.

    Разрешены только операции «Банк↔Пользователь». Для банка следует
    передавать None вместо tg_id.
    """
    if sender_tg_id is not None and receiver_tg_id is not None:
        raise LockViolation(
            "P2P операции между пользователями запрещены каноном: "
            "разрешены только «Банк↔Пользователь».",
        )


def assert_no_auto_nft_delivery(*, auto: bool = False) -> None:
    """
    Запрещает авто-выдачу NFT.

    Любая попытка авто-доставки (auto=True) — нарушение канона. Выдача
    VIP-NFT и других NFT должна идти только по заявке и ручному апруву.
    """
    if auto:
        raise LockViolation(
            "Автоматическая выдача NFT запрещена. "
            "Допустимы только заявки и ручная обработка.",
        )


def ensure_user_non_negative_after(
    before: BalanceSnapshot,
    delta_main: Decimal,
    delta_bonus: Decimal,
) -> None:
    """
    Проверка «не уйти в минус» для пользователя.

    Использование:
    • Вызывать ПЕРЕД применением списания.
    • Покупки за EFHC блокируем, если расчёт даёт отрицательный итог.
    • Пополнения и конвертация kWh→EFHC не блокируются.

    before:
        Текущий снимок баланса.
    delta_main:
        Планируемое изменение основного баланса (может быть отриц.).
    delta_bonus:
        Планируемое изменение бонусного баланса (может быть отриц.).
    """
    after_main = (before.main + delta_main).quantize(
        Q8,
        rounding=ROUND_DOWN,
    )
    after_bonus = (before.bonus + delta_bonus).quantize(
        Q8,
        rounding=ROUND_DOWN,
    )

    if after_main < 0 or after_bonus < 0:
        raise LockViolation(
            "Списание дало бы отрицательный баланс пользователя: "
            f"main={after_main}, bonus={after_bonus}. "
            "Операция запрещена.",
        )


def flag_bank_deficit_if_negative(after_bank_balance: Decimal) -> None:
    """
    Логирует дефицит Банка EFHC, если баланс отрицательный.

    Важно:
    • Банк МОЖЕТ уходить в минус, это не блокирует операции.
    • Хелпер для метрик/логов: позволяет отслеживать моменты,
      когда Банк выдаёт больше EFHC, чем получил.
    """
    if after_bank_balance < 0:
        logger.warning(
            "BANK DEFICIT MODE: after=%s",
            str(after_bank_balance),
        )


# --------------------------------------------------------------------
# Обязательный Idempotency-Key для денежных запросов
# --------------------------------------------------------------------
async def require_idempotency_key(
    idempotency_key: str | None = Header(
        default=None,
        convert_underscores=False,
        alias="Idempotency-Key",
    ),
) -> str:
    """
    FastAPI-зависимость для денежных POST/PUT/PATCH/DELETE.

    Возвращает ключ, либо 400, если заголовок пустой или отсутствует.
    """
    if not idempotency_key or not idempotency_key.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Idempotency-Key header is strictly required for "
                "monetary operations."
            ),
        )
    return idempotency_key.strip()


def monetary_op(func: Callable[..., Any]) -> Callable[..., Any]:
    """
    Декоратор-метка для эндпоинтов: middleware видит денежную операцию.

    Пример:
        @router.post(
            "/activate-panel (compat path /buy)",
            dependencies=[Depends(require_idempotency_key)],
        )
        @monetary_op
        async def activate_panel(...):
            ...
    """
    func._monetary_op = True  # type: ignore[attr-defined]
    return func


def idempotent_action(
    *,
    ttl_sec: int = 30,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Декоратор: точечная идемпотентность (TTL) для одного эндпоинта.

    Это UX-замок от двойных кликов. Бизнес-идемпотентность остаётся
    обеспеченной SSOT/уникальностями доменных таблиц.

    ttl_sec:
        Окно блокировки дублей для пары (path, Idempotency-Key).
    """

    safe_ttl = int(ttl_sec)
    if safe_ttl < 1:
        safe_ttl = 1
    if safe_ttl > 3600:
        safe_ttl = 3600

    def _wrap(func: Callable[..., Any]) -> Callable[..., Any]:
        meta = func.__dict__
        meta["_idempotent_ttl_sec"] = safe_ttl
        meta["_monetary_op"] = True
        return func

    return _wrap


def _build_ttl_lock_key(
    path: str,
    global_id: int,
    idempotency_key: str,
) -> str:
    """Строит owner-scoped TTL-ключ только по canonical global_id."""
    owner_token = f"G{int(global_id):010d}"
    raw = f"http_ttl|{path}|{owner_token}|{idempotency_key}".encode()
    digest = hashlib.sha256(raw).hexdigest()
    return f"http_ttl:{digest}"


async def _acquire_idempotency_ttl_lock(
    *,
    path: str,
    global_id: int,
    idempotency_key: str,
    ttl_sec: int,
) -> bool:
    """Пытается атомарно занять TTL-замок в общей таблице БД.

    Возвращает True, если текущий запрос первый или предыдущий замок
    уже истёк. Возвращает False, если активный TTL-замок уже занят.
    """
    session_factory = get_session_factory()
    now = utcnow()
    expires_at = now + timedelta(seconds=int(ttl_sec))
    owner_token = f"G{int(global_id):010d}"
    key = _build_ttl_lock_key(path, int(global_id), idempotency_key)
    scope = f"http_ttl:{path}"[:64]
    fingerprint = f"{owner_token}:{idempotency_key}"[:128]

    stmt = (
        pg_insert(IdempotencyKey)
        .values(
            key=key,
            scope=scope,
            request_fingerprint=fingerprint,
            global_id=int(global_id),
            used=False,
            expires_at=expires_at,
        )
        .on_conflict_do_update(
            index_elements=[IdempotencyKey.key],
            set_={
                "scope": scope,
                "request_fingerprint": fingerprint,
                "global_id": int(global_id),
                "used": False,
                "expires_at": expires_at,
            },
            where=or_(
                IdempotencyKey.expires_at.is_(None),
                IdempotencyKey.expires_at <= now,
            ),
        )
        .returning(IdempotencyKey.key)
    )

    async with session_factory() as db:
        try:
            res = await db.execute(stmt)
            await db.commit()
        except Exception:  # noqa: BLE001
            logger.exception(
                "Idempotency TTL DB lock failed",
                extra={"path": path},
            )
            return False

    return res.scalar_one_or_none() is not None


def _extract_tg_id_from__init__data(init_data: str) -> int | None:
    """Извлекает tg_id только из Telegram ingress initData."""
    try:
        from app.core.security_core import validate_telegram__init__data
    except Exception:  # noqa: BLE001
        return None

    try:
        parsed = validate_telegram__init__data(init_data)
    except Exception:  # noqa: BLE001
        return None

    user_obj = parsed.get("user")
    if not isinstance(user_obj, dict):
        return None
    raw = user_obj.get("id")
    if raw is None:
        return None
    try:
        tg_id = int(raw)
    except Exception:  # noqa: BLE001
        return None
    return tg_id if tg_id > 0 else None


def _positive_global_id(value: Any) -> int | None:
    """Вернуть валидный внутренний global_id без создания новых keys."""
    raw = getattr(value, "value", value)
    try:
        global_id = int(raw)
    except Exception:  # noqa: BLE001
        return None
    if global_id <= 0 or global_id > 9_999_999_999:
        return None
    return global_id


async def _resolve_monetary_global_id(request: Request) -> int | None:
    """Разрешить monetary owner до создания lock/rate-limit key.

    Новые financial keys строятся только по canonical ``global_id``.
    Telegram subject допускается здесь лишь как ingress для identity
    resolution; в key/fingerprint он не попадает.
    """
    state_global_id = _positive_global_id(
        getattr(request.state, "global_id", None)
    )
    if state_global_id is not None:
        return state_global_id

    state_context = getattr(request.state, "auth_context", None)
    context_global_id = _positive_global_id(
        getattr(state_context, "global_id", None)
    )
    if context_global_id is not None:
        return context_global_id

    raw_auth = (request.headers.get("Authorization") or "").strip()
    if raw_auth:
        scheme, separator, token = raw_auth.partition(" ")
        if separator == " " and scheme.lower() == "bearer" and token:
            try:
                from app.identity.auth_runtime_services import (
                    AuthSessionService,
                )

                context = await AuthSessionService(
                    get_session_factory()
                ).authenticate(token)
                bearer_global_id = _positive_global_id(
                    context.global_id
                )
                if bearer_global_id is not None:
                    return bearer_global_id
            except Exception:  # noqa: BLE001
                # Auth dependency ниже по стеку сохраняет свою 401
                # семантику; middleware не подменяет её.
                logger.debug(
                    "Не удалось разрешить bearer global_id "
                    "для monetary key",
                    exc_info=True,
                )

    provider_tg_id: int | None = None
    state_tg_id = getattr(request.state, "tg_id", None)
    try:
        parsed_state_tg = int(state_tg_id) if state_tg_id is not None else 0
    except Exception:  # noqa: BLE001
        parsed_state_tg = 0
    if parsed_state_tg > 0:
        provider_tg_id = parsed_state_tg
    else:
        init_data = (
            request.headers.get("X-Telegram-Init-Data") or ""
        ).strip()
        if init_data:
            provider_tg_id = _extract_tg_id_from__init__data(init_data)

    if provider_tg_id is None:
        return None

    try:
        from app.identity.telegram_auth_session import (
            resolve_telegram_subject_global_id,
        )

        session_factory = get_session_factory()
        async with session_factory() as db:
            resolved = await resolve_telegram_subject_global_id(
                db, int(provider_tg_id)
            )
        if resolved is None:
            return None
        return _positive_global_id(resolved.value)
    except Exception:  # noqa: BLE001
        return None


def _strip_api_prefix(path: str) -> str:
    """Return route-local path for a runtime API-prefixed request."""
    api_prefix = str(getattr(settings, "API_PREFIX", "/api") or "")
    api_prefix = api_prefix.rstrip("/")
    if not api_prefix:
        return path
    if path == api_prefix:
        return "/"
    if path.startswith(f"{api_prefix}/"):
        return path[len(api_prefix):]
    return path


def _match_monetary__path__scope(
    path: str,
    prefixes: Iterable[str],
) -> str | None:
    """Return the canonical monetary scope for runtime/local paths."""
    route_local_path = _strip_api_prefix(path)
    for prefix in prefixes:
        normalized = str(prefix)
        if route_local_path.startswith(normalized):
            return normalized
    return None


async def _acquire_monetary_rate_limit_slot(
    *,
    global_id: int,
    scope_path: str,
    window_sec: int,
    max_requests: int,
) -> bool:
    """Занять monetary rate-limit slot по canonical global_id."""
    session_factory = get_session_factory()
    now = utcnow()
    expires_at = now + timedelta(seconds=int(window_sec))
    scope = f"monetary_rl:{scope_path}"[:64]
    fingerprint = f"global:G{int(global_id):010d}"
    lock_key = f"{scope}:{fingerprint}"
    nonce = hashlib.sha256(
        f"{scope}|{fingerprint}|{now.timestamp()}".encode()
    ).hexdigest()

    async with session_factory() as db:
        await db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
            {"lock_key": lock_key},
        )
        count_stmt = (
            select(func.count())
            .select_from(IdempotencyKey)
            .where(IdempotencyKey.scope == scope)
            .where(IdempotencyKey.request_fingerprint == fingerprint)
            .where(IdempotencyKey.expires_at.is_not(None))
            .where(IdempotencyKey.expires_at > now)
        )
        current = int((await db.scalar(count_stmt)) or 0)
        if current >= int(max_requests):
            await db.rollback()
            return False

        db.add(
            IdempotencyKey(
                key=nonce,
                scope=scope,
                request_fingerprint=fingerprint,
                global_id=int(global_id),
                used=True,
                expires_at=expires_at,
            )
        )
        await db.commit()
    return True


class MonetaryIdempotencyMiddleware(BaseHTTPMiddleware):
    """
    Middleware-страховка: если разработчик забыл зависимость
    require_idempotency_key на «денежной ручке», этот слой проверит
    заголовок
    по префиксам пути ИЛИ по явной метке @monetary_op и вернёт 400 при
    отсутствии ключа.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        path_prefixes: Iterable[str] | None = None,
        methods: tuple[str, ...] = (
            "POST",
            "PUT",
            "PATCH",
            "DELETE",
        ),
    ) -> None:
        """Создаёт middleware для проверки Idempotency-Key."""
        super().__init__(app)
        self.methods = methods

        # Конфигурируемые префиксы денежных зон:
        # • можно передать в конструктор;
        # • можно задать в settings.MONETARY_PATH_PREFIXES;
        # • иначе используются дефолтные значения.
        default_prefixes: tuple[str, ...] = (
            "/deposit",
            "/exchange",
            "/panels",
            "/payment-intents",
            "/shop",
            "/withdraw",
            "/admin",
        )

        if path_prefixes is not None:
            self.prefixes = tuple(path_prefixes)
        else:
            cfg = getattr(settings, "MONETARY_PATH_PREFIXES", None)
            if isinstance(cfg, list | tuple):
                self.prefixes = tuple(str(p) for p in cfg)
            else:
                self.prefixes = default_prefixes

    async def dispatch(  # type: ignore[override]
        self,
        request: Request,
        call_next: Callable[[Request], Any],
    ) -> Any:
        # Не проверяем безопасные методы.
        """Проверяет Idempotency-Key для денежного запроса."""
        if request.method not in self.methods:
            return await call_next(request)

        path = request.url.path or "/"

        # 1) Если путь «денежный» по префиксу — требуем ключ.
        path_matches = (
            _match_monetary__path__scope(path, self.prefixes)
            is not None
        )

        # 2) Если эндпоинт помечен @monetary_op — тоже требуем.
        marked = False
        ttl_sec: int | None = None
        router = getattr(request.app, "router", None)
        if router is not None:
            for route in router.routes:
                route_path = getattr(route, "path", None)
                route_methods = getattr(route, "methods", None)
                if route_path != path or not route_methods:
                    continue
                endpoint = getattr(route, "endpoint", None)
                endpoint_is_marked = bool(endpoint)
                if endpoint_is_marked:
                    endpoint_is_marked = bool(
                        getattr(endpoint, "_monetary_op", False)
                    )
                if endpoint_is_marked:
                    marked = True
                    ttl_attr = getattr(
                        endpoint,
                        "_idempotent_ttl_sec",
                        None,
                    )
                    if isinstance(ttl_attr, int) and ttl_attr > 0:
                        ttl_sec = int(ttl_attr)
                    break

        if path_matches or marked:
            idk = (request.headers.get("Idempotency-Key") or "").strip()
            if not idk:
                return _http_400(
                    "Idempotency-Key header is required "
                    "for monetary operations.",
                )

            # TTL-идемпотентность включаем только для
            # @idempotent_action. Блокировка хранится в БД,
            # чтобы работать одинаково на нескольких инстансах.
            if ttl_sec is not None:
                global_id = await _resolve_monetary_global_id(request)
                if global_id is None:
                    return await call_next(request)
                acquired = await _acquire_idempotency_ttl_lock(
                    path=path,
                    global_id=global_id,
                    idempotency_key=idk,
                    ttl_sec=ttl_sec,
                )
                if not acquired:
                    return _json_response(
                        status.HTTP_409_CONFLICT,
                        {
                            "detail": (
                                "Duplicate request blocked by "
                                "idempotency TTL."
                            )
                        },
                    )

        return await call_next(request)


class MonetaryRateLimitMiddleware(BaseHTTPMiddleware):
    """Ограничивает денежные запросы по canonical global_id."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        path_prefixes: Iterable[str] | None = None,
        methods: tuple[str, ...] = (
            "POST",
            "PUT",
            "PATCH",
            "DELETE",
        ),
        window_sec: int | None = None,
        max_requests: int | None = None,
    ) -> None:
        super().__init__(app)
        self.methods = methods
        default_prefixes: tuple[str, ...] = (
            "/deposit",
            "/exchange",
            "/panels",
            "/payment-intents",
            "/shop",
            "/withdraw",
            "/admin",
        )
        if path_prefixes is not None:
            self.prefixes = tuple(path_prefixes)
        else:
            cfg = getattr(settings, "MONETARY_PATH_PREFIXES", None)
            if isinstance(cfg, list | tuple):
                self.prefixes = tuple(str(p) for p in cfg)
            else:
                self.prefixes = default_prefixes

        raw_window = window_sec
        if raw_window is None:
            raw_window = getattr(
                settings,
                "MONETARY_RATE_LIMIT_WINDOW_SEC",
                60,
            )
        raw_max = max_requests
        if raw_max is None:
            raw_max = getattr(
                settings,
                "MONETARY_RATE_LIMIT_MAX_REQUESTS",
                20,
            )
        self.window_sec = max(1, int(raw_window))
        self.max_requests = max(1, int(raw_max))

    async def dispatch(  # type: ignore[override]
        self,
        request: Request,
        call_next: Callable[[Request], Any],
    ) -> Any:
        if request.method not in self.methods:
            return await call_next(request)

        path = request.url.path or "/"
        scope_path = _match_monetary__path__scope(path, self.prefixes)
        if scope_path is None:
            return await call_next(request)

        global_id = await _resolve_monetary_global_id(request)
        if global_id is None:
            return await call_next(request)

        try:
            allowed = await _acquire_monetary_rate_limit_slot(
                global_id=global_id,
                scope_path=scope_path,
                window_sec=self.window_sec,
                max_requests=self.max_requests,
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "Monetary rate limit check failed",
                extra={"path": path, "global_id": global_id},
            )
            return _json_response(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                {"detail": "Monetary rate limit unavailable."},
            )

        if not allowed:
            return _json_response(
                status.HTTP_429_TOO_MANY_REQUESTS,
                {
                    "detail": (
                        "Too many monetary requests. Please slow down."
                    )
                },
            )

        return await call_next(request)


def _http_400(msg: str) -> JSONResponse:
    """Короткий JSON-ответ 400."""
    return _json_response(
        status.HTTP_400_BAD_REQUEST,
        {"detail": msg},
    )


def _json_response(code: int, payload: dict) -> JSONResponse:
    """Короткий JSONResponse без лишних зависимостей."""
    return JSONResponse(
        status_code=code,
        content=payload,
    )


# --------------------------------------------------------------------
# Инициализация «замков» на старте приложения
# --------------------------------------------------------------------


def install_security_middlewares(app: FastAPI) -> None:
    """Установить канонический security middleware ровно в одном месте."""
    from app.middleware.telegram_webapp_auth import (
        TelegramWebAppAuthMiddleware,
    )

    app.add_middleware(TelegramWebAppAuthMiddleware)
    app.add_middleware(MonetaryIdempotencyMiddleware)
    app.add_middleware(MonetaryRateLimitMiddleware)
    logger.info(
        "SystemLocks: Telegram auth, monetary idempotency и rate-limit "
        "middleware установлены."
    )


def init_system_locks(app: FastAPI) -> None:
    """
    Инициализация канон-проверок и middleware.

    Вызывать один раз при сборке FastAPI:
        app = FastAPI(...)
        init_system_locks(app)
    """
    # 1) Жёсткая проверка канонических системных locks.
    assert_system_locks()
    logger.info("SystemLocks: startup canon validated.")

    # 2) Compatibility-фасад вызывает тот же канонический установщик.
    install_security_middlewares(app)

    # 3) (опционально) Логи о режиме банка.
    allow_negative_bank = bool(
        getattr(settings, "ALLOW_NEGATIVE_BANK_BALANCE", True),
    )
    if not allow_negative_bank:
        logger.warning(
            "ALLOW_NEGATIVE_BANK_BALANCE = false. "
            "Это противоречит канону (банку разрешён минус). "
            "Рекомендуется установить true.",
        )


__all__ = [
    "LockViolation",
    "BalanceSnapshot",
    "assert_per_sec_canon",
    "get_rate_base_d8",
    "get_rate_vip_d8",
    "assert_system_locks",
    "assert_exchange_direction_kwh_to_efhc_only",
    "assert_p2p_forbidden",
    "assert_no_auto_nft_delivery",
    "ensure_user_non_negative_after",
    "flag_bank_deficit_if_negative",
    "require_idempotency_key",
    "monetary_op",
    "MonetaryIdempotencyMiddleware",
    "MonetaryRateLimitMiddleware",
    "install_security_middlewares",
    "init_system_locks",
]

# =====================================================================
# Пояснения «для чайника»:
# • Сервисы должны вызывать ensure_user_non_negative_after(...) перед
# любыми списаниями с пользовательских балансов.
# Если расчёт даёт минус —
# поднимаем LockViolation и НЕ выполняем операцию.
# • Для банка: после применения операции вызывайте
# flag_bank_deficit_if_negative(...) чтобы фиксировать дефицит в логах.
# Операция при этом не блокируется — это штатная ситуация.
# • Денежные эндпоинты:
# а) dependencies=[Depends(require_idempotency_key)];
# б) декоратор-метка @monetary_op.
# Даже если забыли — middleware проверит по префиксу пути.
# • P2P: при любой попытке указать одновременно sender_global_id и
# Для receiver_global_id вызывайте
# assert_p2p_forbidden(...), чтобы немедленно завершить операцию.
# поймать нарушение канона «нет внутренних переводов».
# • NFT: авто-доставка запрещена. watcher/shop должны создавать заявки
# со статусом наподобие PAID_PENDING_MANUAL, а админ-панель уже решает,
# когда и кому фактически выдавать NFT.
# =====================================================================
