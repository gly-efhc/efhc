# EFHC — публичный репозиторий приложения

**Проект:** Energy for Humanity Coin (EFHC) · **Исходный код:** [gly-efhc/efhc](https://github.com/gly-efhc/efhc) · **Документальный Архив:** приватный [gly-efhc/efhc_archive](https://github.com/gly-efhc/efhc_archive).

Этот репозиторий содержит исходные файлы React/Next.js frontend, FastAPI backend, общий контракт, изолированный TEST-адаптер, тесты, инструменты CI/Pages и публично безопасные инструкции. Он **не** является копией приватного документального Архива, production backend, базой данных или доказательством исполнения финансовой операции. Наличие приложения в GitHub Pages либо успешного frontend build не подтверждает состояние production, реальность выплат и on-chain settlement.

## Начало работы

Для разработчика и AI-агента предусмотрен единый порядок:

[AGENTS.md](AGENTS.md) → [START_HERE.md](START_HERE.md) → [KERNEL.md](KERNEL.md) (**однократно за операционный контекст**) → [INDEX.md](INDEX.md) → фактический исходный ref/HEAD → конкретная задача.

- **AGENTS** — полномочия, защита, приоритет источников и правила изменения кода.
- **START_HERE** — последовательность входа и выбор документальной зависимости.
- **KERNEL** — операционный диспетчер, не исполняемая программа.
- **INDEX** — пути frontend, CI и предметные маршруты к действующей структуре приватного Архива.

Текущий `main` следует проверять по реальному commit SHA. Архив `Archive_vNNN.zip` (локальная полная копия), удалённый `efhc_archive/main`, public `efhc/main` и развернутый release — **разные состояния**; совпадение одного не подтверждает другие.

## Состав репозитория

| Путь | Назначение |
| --- | --- |
| [frontend/](frontend/) | React/Next.js приложение и зависимости |
| [frontend/src/](frontend/src/) | Реальные компоненты, состояния и маршруты |
| [tests/frontend/](tests/frontend/) | Регрессионные и parity-проверки |
| [backend/](backend/) | Общий backend, API, Bot, scheduler, миграции |
| [contracts/](contracts/) | Общие контракты |
| [environments/test/demo_backend/](environments/test/demo_backend/) | Изолированный TEST-адаптер |
| [tests/backend/](tests/backend/), [tests/integration/](tests/integration/) | Backend и интеграционные тесты |
| [scripts/parity/](scripts/parity/) | Сопоставление frontend с исходными эталонами |
| [deployment/pages-tools/](deployment/pages-tools/) | Проверки публикации и browser smoke |
| [.github/workflows/](.github/workflows/) | GitHub Actions и процедуры CI/Pages |
| [frontend/RECOVERY.md](frontend/RECOVERY.md) | Техническая инструкция восстановления frontend; исторические утверждения сверять с текущими решениями OWNER |
| [frontend/EFHC_APPLICATION_RULES.md](frontend/EFHC_APPLICATION_RULES.md) | Утверждённый публичный маршрут правил приложения (редакция B) |
| [frontend/APPLICATION_RULES.md](frontend/APPLICATION_RULES.md) | Вторичный публичный документ, не независимый SSOT |
| [frontend/RELEASE.json](frontend/RELEASE.json) | Контракт идентичности TEST-релиза; фактический `release.json` формируется из Git и собранного Serwist |
| [import/README.md](import/README.md) | Безопасное сравнение архивов; автоматическая замена исходников запрещена |

Единая команда компиляции — `npm run build`; Pages использует её для статического профиля. `release.json` идентифицирует исходные деревья и скомпилированный PWA, но не подтверждает развернутый Backend или миграции БД. Приватный `Archive_vNNN.zip` не загружается в публичный `efhc/import/`.

## Локальная разработка

Рабочий каталог frontend — `frontend/`. Команды объявлены в [package.json](frontend/package.json):

```bash
cd frontend
npm ci
npm run dev
```

Для проверки изменений в исходниках, когда это соответствует scope:

```bash
npm run typecheck
npm run test:frontend-regression
npm run build
```

Точное поведение скриптов и доступность зависимостей проверяются по текущему `package.json` и окружению. Не объявлять команды выполненными без фактического запуска; `NOT_RUN` не означает `PASS`.

## Актуальные документальные правила EFHC

**Нормативный источник — приватный Архив**, доступный только авторизованным участникам. Установленный порядок: последнее прямое решение OWNER → `01_CANON/` → `05_SSOT/` → `06_NORM/` → архитектура и ТЗ в `13_PLANS/TECHNICAL_TASKS/` → конкретный source как факт реализации. `03_REPORTS/` и `04_CYCLES/` фиксируют историю исполнения и решения, не создавая альтернативную действующую норму.

Применимые читателю маршруты внутри приватного Архива:

- `AGENTS.md`, `START_HERE.md`, `KERNEL.md` (один раз), `INDEX.md`, `01_CANON/TERMS.md` — точка входа.
- `05_SSOT/FRONTEND/APPLICATION_RULES.md`, `10_FRONTEND/README.md` — frontend и визуальные контракты.
- `05_SSOT/FRONTEND/EFHC_SERWIST_PWA_CACHE_STANDARD.md` — PWA-кеш Serwist; `05_SSOT/FRONTEND/EFHC_UNIFIED_CACHE_OWNER_SSOT.md` — связанные ограничения пользовательского состояния.
- `05_SSOT/CONTRACTS/` и `01_CANON/ADMIN/` — Identity, Wallet, TON, Admin и финансовые интерфейсы.
- `06_NORM/DOCUMENTATION/DOCUMENT_MANAGEMENT_RULES.md`, `08_AI/AI_CROSS_REPO_ROUTING.md`, `12_RUNBOOKS/README.md` — управление документами, маршрутизация и эксплуатационные процедуры.

Авторизованный GitHub-коннектор необходим для чтения закрытых файлов; публичная ссылка не отменяет ограничения доступа. Оригиналы приватных CANON/SSOT/NORM, номерных свидетельств, ключей, персональной информации, коммерческих данных и непубличных HTML-эталонов **не размещаются** здесь.

## Текущие инженерные границы

Frontend восстанавливается и проверяется относительно принятого внешнего визуального HTML-эталона v866 и применимых решений OWNER. Общий запрет на визуальные изменения React Admin **не действует**: исправление допустимо при отдельном прямом разрешении и реальном сравнении с эталоном. Уже принятые отдельные интерфейсные механизмы остаются защищёнными в точных пределах своих решений.

Serwist является владельцем PWA/CacheStorage; приложение не должно создавать конкурирующий собственный PWA cache engine. При этом Global ID, owner-scoped пользовательское состояние, сессии, финансовые операции и соединения с кошельком проверяются по их самостоятельным контрактам. Demo/fixtures не выдаются за реальные проводки, а изменения кода не доказывают восстановление backend/TON без предметной проверки.

Для изменения исходников, тестов, workflows, архитектурных и финансовых механизмов требуется конкретное распоряжение OWNER. Документационное поручение не разрешает побочные миграции, deploy, работу с secrets или изменения приватного Архива. Итог подтверждается `commit → remote readback`; тесты, CI, browser и приёмка OWNER фиксируются отдельно.

**Полная навигация:** [INDEX.md](INDEX.md). **Правила для AI:** [AGENTS.md](AGENTS.md).