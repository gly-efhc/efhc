# EFHC DEMO Backend

Единственный исходник TEST-адаптера — `environments/test/demo_backend/`. Бизнес-логика и маршруты принадлежат `backend/`.

Docker context — корень репозитория; Dockerfile — `environments/test/Dockerfile`. Конфигурация TEST передаётся серверу из отдельного приватного ENV вне дерева исходников. Genesis требует канонический OWNER allowlist из приватного Backend; публичная копия не заменяет его. Не использовать production DSN и реальные средства.

Офлайн-инвентаризация: из корня репозитория выполнить `PYTHONPATH=backend:environments/test python -m demo_backend.audit`. Результат диагностики выводится в stdout, не создаёт отдельный реестр маршрутов. Машинный контракт — `ROUTES.json` и `backend/openapi/openapi.json`.
