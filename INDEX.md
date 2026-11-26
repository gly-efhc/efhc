# INDEX.md — маршрутизатор публичного репозитория EFHC

**Назначение:** карта реально существующих исходников `gly-efhc/efhc` и публично безопасные указатели на приватный `gly-efhc/efhc_archive`. Этот индекс не хранит private CANON, SSOT, коммерческие параметры, историю или секреты.

## 1. Обязательный вход

[AGENTS.md](AGENTS.md) → [START_HERE.md](START_HERE.md) → [KERNEL.md](KERNEL.md) (**один раз за контекст**) → этот INDEX → фактический `CODE_HEAD` → нужный исходник.

При нормативной зависимости: авторизованный коннектор → приватные `AGENTS → START_HERE → KERNEL (однократно) → INDEX → 01_CANON/TERMS.md` → README раздела и предметный владелец. Записывать `ARCHIVE_HEAD` независимо от `CODE_HEAD`. Локальный `Archive_vNNN.zip` — отдельная физическая редакция.

## 2. Публичные исходники и инструкции

| Задача | Реальный путь efhc |
| --- | --- |
| Вход, правила и навигация | [AGENTS.md](AGENTS.md), [START_HERE.md](START_HERE.md), [KERNEL.md](KERNEL.md), [README.md](README.md) |
| React/Next.js приложение | [site/frontend/](site/frontend/), [package.json](site/frontend/package.json) |
| UI-компоненты и клиентская логика | [site/frontend/src/](site/frontend/src/) |
| Регрессия и parity | [site/frontend/tests/](site/frontend/tests/) |
| Parity-инструменты и проверка HTML | [site/ci/parity/](site/ci/parity/), [site/frontend/tests/parity/](site/frontend/tests/parity/) |
| Pages/browser CI | [site/ci/pages-tools/](site/ci/pages-tools/) |
| Восстановление frontend | [site/RECOVERY.md](site/RECOVERY.md) |
| Публичные правила приложения | [site/EFHC_APPLICATION_RULES.md](site/EFHC_APPLICATION_RULES.md) — маршрут B |
| Вторичная редакция правил | [site/APPLICATION_RULES.md](site/APPLICATION_RULES.md) — не самостоятельный SSOT |
| Идентичность TEST-релиза | [site/RELEASE.json](site/RELEASE.json) — контракт; `release.json` формируется при сборке |
| CI и публикация | [.github/workflows/](.github/workflows/) |
| Импорт исходного frontend | [import/README.md](import/README.md); не путать с документальным Архивом |

Наличие пути не доказывает успех сборки или актуальность ранее записанного release SHA. ZIP используется только для сравнения и восстановления в отдельной рабочей копии; маршрут в `import/README.md` не предусматривает автоматической замены исходников.

## 3. Приватные предметные маршруты

Приватный репозиторий: [`gly-efhc/efhc_archive`](https://github.com/gly-efhc/efhc_archive). Ссылки далее предназначены **только** авторизованным читателям и сами не открывают содержимое публично. Действующие пути проверены на архивной структуре; при изменении remote ref сверять их заново.

| Предмет | Действующий маршрут приватного Архива |
| --- | --- |
| Решения OWNER и словарь | `01_CANON/OWNER_DECISIONS.md`, `01_CANON/TERMS.md` |
| Архитектура и ADR | `02_ARCHITECTURE/README.md` |
| Отчёты и зарегистрированные доказательства | `03_REPORTS/README.md` и README проектной серии |
| Циклы и глобальные вопросы | `04_CYCLES/README.md`, `04_CYCLES/QUESTIONS_AND_ANSWERS_REGISTER.md`, `04_CYCLES/QUESTION_LINK_INDEX.md` |
| Единые продуктовые и технические контракты | `05_SSOT/README.md` |
| Постоянные нормы | `06_NORM/README.md` |
| Управление документами и формат серий | `06_NORM/DOCUMENTATION/DOCUMENT_MANAGEMENT_RULES.md`, `06_NORM/DOCUMENTATION/REPORTS_CYCLES_FORMAT_CONTROL.md` |
| FAQ и справочная информация | `07_GENERAL/README.md` |
| AI-маршруты и переход между репозиториями | `08_AI/README.md`, `08_AI/AI_CROSS_REPO_ROUTING.md` |
| Документация backend | `09_BACKEND/README.md` |
| Контракты frontend и визуальная приёмка | `10_FRONTEND/README.md` |
| Операционные инструкции | `12_RUNBOOKS/README.md` |
| Планы и единственный раздел ТЗ | `13_PLANS/README.md`, `13_PLANS/TECHNICAL_TASKS/README.md` |

Не восстанавливать отменённые самостоятельные разделы и не создавать ссылки на ненормативные внутренние контейнеры. README определяет назначение и навигацию, а не техническую хронологию.

## 4. Уточнение по предмету frontend

| Направление | Приватный первоисточник |
| --- | --- |
| Правила приложения и редакция B | `01_CANON/APP_RULES_OWNER_DECISION_B.md`, `05_SSOT/FRONTEND/APPLICATION_RULES.md` |
| Визуальный эталон, темы, React Admin | `01_CANON/FRONTEND/PUBLIC_VISUAL_BASELINE_CANON.md`, `06_NORM/FRONTEND/VISUAL_FRONTEND_PUBLIC_UI_NORM.md`, `10_FRONTEND/README.md` |
| PWA и владелец кеша Serwist | `05_SSOT/FRONTEND/EFHC_SERWIST_PWA_CACHE_STANDARD.md`, `05_SSOT/FRONTEND/EFHC_UNIFIED_CACHE_OWNER_SSOT.md` |
| Глобальная идентичность | `05_SSOT/CONTRACTS/GLOBAL_IDENTITY_SSOT.md` |
| Wallet и TON | `05_SSOT/CONTRACTS/WALLETS_TONCONNECT_SSOT.md` |
| PaymentIntent и вывод | `05_SSOT/CONTRACTS/PAYMENT_INTENT_SSOT.md`, `05_SSOT/CONTRACTS/EXCHANGE_WITHDRAW_MECHANICS_SSOT.md` |
| Admin и роли | `01_CANON/ADMIN/ADMIN_UNIFIED_CANON.md`, `06_NORM/ADMIN/RBAC_OWNER_APPROVED.md` |
| FAQ и переводы | `05_SSOT/CONTRACTS/FAQ_SSOT.md`, `07_GENERAL/README.md` |

Исходный `FRONTEND_v866.html` — отдельный внешний визуальный эталон; ссылку на файл или приёмку давать только после физической проверки. React Admin может исправляться по прямому поручению OWNER, его прежний общий visual freeze не восстанавливать. Защищённые локальные приёмки действуют в собственном scope.

## 5. Типовые маршруты и критерии результата

- **UI/React:** CANON/SSOT → точный code HEAD → компонент → регрессионные/parity tests → браузерное сравнение с физическим эталоном → acceptance OWNER.
- **Serwist/Cache:** Serwist SSOT → действующий service worker/source → проверка обновления, owner-isolation и сетевых границ → реальная browser regression.
- **Identity/Wallet/финансы:** предметный контракт → frontend/API → независимый backend и on-chain outcome. DEMO/HTTP/CI по отдельности не подтверждают финансовый результат.
- **CI/Pages:** существующий workflow → scoped diff → фактический job/artifact/browser verdict; не делать deploy без разрешения.
- **Документация:** private/public граница → адресное обновление разрешённых публичных файлов → link/readback check. Не открывать новый номерной цикл из-за commit.

Защитное правило: кодовые изменения, нормативные изменения в Архиве и запуск production — три разные команды. Отсутствующие права или первоисточник обозначать `BLOCKED`; не додумывать доказательства.

**Связанные документы:** [README.md](README.md) · [START_HERE.md](START_HERE.md) · [KERNEL.md](KERNEL.md).