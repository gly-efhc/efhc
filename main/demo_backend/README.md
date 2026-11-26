# EFHC DEMO Backend

Единственный исходник TEST-адаптера — `main/demo_backend/`. Бизнес-логика и маршруты принадлежат `main/backend/`.

Docker context — корень репозитория; Dockerfile — `main/demo_backend/Dockerfile`. Конфигурация TEST передаётся серверу из отдельного приватного ENV вне дерева исходников. Genesis требует канонический OWNER allowlist из приватного Backend; публичная копия не заменяет его. Не использовать production DSN и реальные средства.

Офлайн-инвентаризация: из `main/` выполнить `PYTHONPATH=backend:. python -m demo_backend.audit`. Результат диагностики выводится в stdout, не создаёт отдельный реестр маршрутов. Машинный контракт — `ROUTES.json` и `main/backend/openapi/openapi.json`.
