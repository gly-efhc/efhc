# START_HERE.md — начало работы с EFHC

**Репозиторий:** [`gly-efhc/efhc`](https://github.com/gly-efhc/efhc) · **Область:** публичный исходный frontend, тесты, CI и публично безопасная документация.

## 1. Вход агента

1. Прочитать [AGENTS.md](AGENTS.md), этот документ, [KERNEL.md](KERNEL.md) **один раз за операционный контекст**, затем [INDEX.md](INDEX.md). `KERNEL.md` — текстовый диспетчер, не исполняемый скрипт.
2. Определить реальный `main`/ref и `CODE_HEAD`. Установить последнее прямое поручение OWNER, режим и точный перечень разрешённых путей. Не приписывать текущему `main` статус опубликованного релиза.
3. Если задание опирается на правила EFHC, получить действующие документы из приватного [`gly-efhc/efhc_archive`](https://github.com/gly-efhc/efhc_archive) посредством **авторизованного GitHub-коннектора**. Прочитать приватные `AGENTS → START_HERE → KERNEL` (однократно) `→ INDEX → 01_CANON/TERMS.md`, затем README на нужном маршруте и только предметные CANON/`05_SSOT`/`06_NORM`. Для документационных норм: `06_NORM/DOCUMENTATION/DOCUMENT_MANAGEMENT_RULES.md`.
4. Если OWNER передал локальный `Archive_vNNN.zip`, проверить имя, SHA-256, CRC, безопасность путей и нужные файлы. Не отождествлять локальный ZIP с `ARCHIVE_HEAD` без проверки; не загружать ZIP в GitHub автоматически.
5. Выбрать точный исходник, контракт или процедуру по [INDEX.md](INDEX.md). Фиксировать доказательства чтения, а не восстанавливать требования по памяти.

## 2. Разделение источников

| Источник | Что он подтверждает |
| --- | --- |
| `gly-efhc/efhc` | Проверенный на конкретном Git ref код frontend, тесты, workflows и публичные инструкции |
| Приватный `gly-efhc/efhc_archive` / утверждённый ZIP | Решения OWNER, CANON, SSOT, NORM, архитектуру, ТЗ и зарегистрированную документальную историю |
| CI, браузер, backend, on-chain, release artifact | Отдельно доказанный результат исполнения; их нельзя подменять документом или успешным локальным DEMO |

Приоритет нормативных решений: последнее распоряжение OWNER → приватный CANON → `05_SSOT` → `06_NORM` → архитектура/ТЗ; код — свидетельство реализации. `03_REPORTS` и `04_CYCLES` хранят подтверждённую историю, а не текущие альтернативные нормы.

## 3. Что читать по задаче

- **Frontend и UI:** [`site/frontend/src/`](site/frontend/src/), [`site/RECOVERY.md`](site/RECOVERY.md), [`site/frontend/tests/`](site/frontend/tests/); приватные `05_SSOT/FRONTEND/APPLICATION_RULES.md` и `10_FRONTEND/README.md`. React Admin требует восстановления по внешнему HTML v866; его общий визуальный freeze отменён, но новое изменение кода требует scope OWNER.
- **PWA и обновления:** исходники Serwist в frontend; приватные `05_SSOT/FRONTEND/EFHC_SERWIST_PWA_CACHE_STANDARD.md` и `05_SSOT/FRONTEND/EFHC_UNIFIED_CACHE_OWNER_SSOT.md`. Различать PWA CacheStorage, пользовательское состояние, сессии и чувствительные сетевые операции.
- **Wallet, TON, Identity, Admin, финансы:** только применимые `01_CANON`, `05_SSOT/CONTRACTS`, `06_NORM` и реальный frontend/backend код. Нельзя принимать клик или HTTP-ответ за подтверждение on-chain settlement.
- **ТЗ и эксплуатация:** приватные `13_PLANS/TECHNICAL_TASKS/README.md`, `12_RUNBOOKS/README.md`; не искать действующие нормы в старых разделах.
- **Отчёты и вопросы:** приватные `03_REPORTS/README.md`, `04_CYCLES/README.md`, `04_CYCLES/QUESTIONS_AND_ANSWERS_REGISTER.md`, `06_NORM/DOCUMENTATION/REPORTS_CYCLES_FORMAT_CONTROL.md`. Новый номер/цикл не открывается автоматически от изменения кода.

## 4. Исполнение и проверка

Сначала `SCOPE → PIN HEAD → targeted READ → EDIT`, затем релевантные `VERIFY → COMMIT → remote READBACK`. Не затрагивать неназванные файлы, публиковать приватные документы, менять secrets, backend, pipelines или production без разрешения. Для frontend команды из [`site/frontend/package.json`](site/frontend/package.json):

```bash
cd site/frontend
npm ci
npm run typecheck
npm run test:frontend-regression
npm run build
```

Выбирать проверки по фактическому изменению; `NOT_RUN` — не `PASS`. Результат передавать как `scope | CODE_HEAD | ARCHIVE_HEAD/ZIP (если применимо) | changed paths | checks | нерешённые зависимости`.

**Далее:** [KERNEL.md](KERNEL.md) (если ещё не прочитан) и [INDEX.md](INDEX.md).