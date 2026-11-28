import React, { useEffect, useMemo, useState } from "react";

import { AdminPage } from "../../components/admin/AdminPage";
import { AdminSectionCard } from "../../components/admin/AdminSectionCard";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { TelegramEmptyState } from "../../components/ui/telegram/TelegramEmptyState";
import { TelegramInfoBlock } from "../../components/ui/telegram/TelegramInfoBlock";
import { TelegramSectionRow } from "../../components/ui/telegram/TelegramSectionRow";
import { useT } from "../../hooks/useT";
import {
  ADMIN_ADS_DASHBOARD_PATH,
  ADMIN_ADS_PROVIDER_PATH,
  ADMIN_ADS_PROVIDER_RESET_ERRORS_PATH,
  ADMIN_ADS_PROVIDER_SECRET_DELETE_PATH,
  ADMIN_ADS_PROVIDER_SECRET_REPLACE_PATH,
  ADMIN_ADS_PROVIDER_TEST_PATH,
  ADMIN_ADS_PROVIDERS_PATH,
  ADMIN_ADS_REVENUE_OPTIMIZER_APPLY_PATH,
  ADMIN_ADS_REVENUE_OPTIMIZER_PATH,
  adminPath,
} from "../../lib/api/generated/adminSeams";
import { adminSafeLoadError, adminUiErrorMessage } from "../../lib/adminError";
import { getClientAdProvider } from "../../lib/ads/providers";
import { WITHDRAW_REQUIRED_AD_PLACEMENT_CODE } from "../../lib/ads/systemPlacements";
import { useAdminLinkedTransport } from "../../queries/useAdminLinkedTransport";

type ConfigField = { name: string; secret: boolean; required: boolean };

type ProviderRow = {
  code: string;
  title: string;
  enabled: boolean;
  is_active: boolean;
  priority: number;
  miniapp_enabled: boolean;
  bot_enabled: boolean;
  rewarded_enabled: boolean;
  is_configured: boolean;
  configuration_status: string;
  verification_level: string;
  verification_mode: string;
  health: string;
  public_config: Record<string, unknown>;
  secret_masks: Record<string, string>;
  countries_allow: string[];
  countries_block: string[];
  languages_allow: string[];
  languages_block: string[];
  capabilities: string[];
  config_schema: ConfigField[];
  contract_status: string;
  source: string;
  note?: string;
  moderation_status?: string | null;
  last_success_at?: string | null;
  last_error_at?: string | null;
  last_error_code?: string | null;
};

type Dashboard = {
  period: string;
  overall: {
    ad_requests: number;
    impressions: number;
    completed_rewarded_views: number;
    rewarded_users: number;
    provider_no_fill: number;
    errors: number;
    fallback: number;
    efhcb_distributed: string;
    estimated_revenue_usd: string;
    confirmed_revenue_usd: string;
    revenue_per_1000_requests_usd: string;
    revenue_per_completed_ad_usd: string;
  };
  providers: Array<Record<string, unknown>>;
  geo: Array<Record<string, unknown>>;
  languages: Array<Record<string, unknown>>;
  tasks: Array<Record<string, unknown>>;
  timeline: Array<Record<string, unknown>>;
};

type Optimizer = {
  metric: string;
  min_requests: number;
  recommended_order: string[];
  ranked: Array<Record<string, unknown>>;
  insufficient_data: Array<Record<string, unknown>>;
  auto_apply_enabled: boolean;
};

type ProviderEdit = {
  enabled: boolean;
  priority: string;
  miniappEnabled: boolean;
  botEnabled: boolean;
  rewardedEnabled: boolean;
  publicConfig: Record<string, string>;
  countriesAllow: string;
  countriesBlock: string;
  languagesAllow: string;
  languagesBlock: string;
  moderationStatus: string;
};

const FIELD_LABELS: Record<string, string> = {
  reward_block_id: "Идентификатор блока награды",
  bot_block_id: "Идентификатор блока бота",
  bot_token: "Токен бота",
  rewarded_zone_id: "Идентификатор зоны с наградой",
  sdk_src: "Адрес SDK",
  ssp_id: "Идентификатор SSP",
  publisher_id: "Идентификатор издателя",
  widget_id: "Идентификатор виджета",
  bid_floor: "Минимальная ставка",
  script_src: "Адрес рекламного скрипта",
  api_key: "Ключ API",
  postback_secret: "Секрет обратного уведомления",
  min_view_sec: "Минимальное время просмотра",
  secret: "Технический секрет",
};

function csv(value: string): string[] {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function editFromProvider(provider: ProviderRow): ProviderEdit {
  const publicConfig: Record<string, string> = {};
  for (const field of provider.config_schema || []) {
    if (!field.secret) publicConfig[field.name] = String(provider.public_config?.[field.name] ?? "");
  }
  return {
    enabled: provider.enabled,
    priority: String(provider.priority ?? 100),
    miniappEnabled: provider.miniapp_enabled,
    botEnabled: provider.bot_enabled,
    rewardedEnabled: provider.rewarded_enabled,
    publicConfig,
    countriesAllow: (provider.countries_allow || []).join(", "),
    countriesBlock: (provider.countries_block || []).join(", "),
    languagesAllow: (provider.languages_allow || []).join(", "),
    languagesBlock: (provider.languages_block || []).join(", "),
    moderationStatus: provider.moderation_status || "",
  };
}

function fieldClass(): string {
  return "w-full rounded-xl border border-[color:var(--tg-section-separator-color)] bg-[color:var(--tg-secondary-bg-color)] px-3 py-2 text-sm text-[color:var(--tg-text-color)]";
}

function healthLabel(value: string): string {
  const map: Record<string, string> = {
    healthy: "Работает",
    degraded: "Есть ошибки",
    circuit_open: "Временно пропускается",
    probe: "Проверяется после паузы",
    unknown: "Ещё не проверен",
  };
  return map[String(value || "").toLowerCase()] || "Статус не определён";
}

function number(value: unknown): number {
  const parsed = Number(value || 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

export default function AdminAdsPage() {
  const adminApiRequest = useAdminLinkedTransport();
  const t = useT();
  const [providers, setProviders] = useState<ProviderRow[]>([]);
  const [selectedCode, setSelectedCode] = useState<string | null>(null);
  const [edit, setEdit] = useState<ProviderEdit | null>(null);
  const [secretValues, setSecretValues] = useState<Record<string, string>>({});
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [optimizer, setOptimizer] = useState<Optimizer | null>(null);
  const [period, setPeriod] = useState("7d");
  const [customFrom, setCustomFrom] = useState("");
  const [customTo, setCustomTo] = useState("");
  const [loading, setLoading] = useState(false);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const selected = useMemo(
    () => providers.find((provider) => provider.code === selectedCode) || null,
    [providers, selectedCode],
  );

  async function loadProviders() {
    const rows = await adminApiRequest<ProviderRow[]>(ADMIN_ADS_PROVIDERS_PATH, "GET");
    const sorted = [...(Array.isArray(rows) ? rows : [])].sort((a, b) => a.priority - b.priority);
    setProviders(sorted);
    const nextCode = selectedCode && sorted.some((row) => row.code === selectedCode)
      ? selectedCode
      : sorted[0]?.code || null;
    setSelectedCode(nextCode);
    const next = sorted.find((row) => row.code === nextCode) || null;
    setEdit(next ? editFromProvider(next) : null);
  }

  async function loadDashboard(nextPeriod = period) {
    const query = new URLSearchParams({ period: nextPeriod });
    if (nextPeriod === "custom") {
      if (!customFrom || !customTo) throw new Error("Укажите начало и окончание периода.");
      query.set("date_from", `${customFrom}T00:00:00Z`);
      query.set("date_to", `${customTo}T23:59:59Z`);
    }
    const data = await adminApiRequest<Dashboard>(`${ADMIN_ADS_DASHBOARD_PATH}?${query.toString()}`, "GET");
    setDashboard(data);
  }

  async function loadOptimizer() {
    const data = await adminApiRequest<Optimizer>(`${ADMIN_ADS_REVENUE_OPTIMIZER_PATH}?period=30d&min_requests=20`, "GET");
    setOptimizer(data);
  }

  async function load() {
    setLoading(true);
    setErrorMessage(null);
    try {
      await Promise.all([loadProviders(), loadDashboard(), loadOptimizer()]);
    } catch (e: unknown) {
      setErrorMessage(adminSafeLoadError(e, t));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  useEffect(() => {
    if (!selected) return;
    setEdit(editFromProvider(selected));
    setSecretValues({});
  }, [selectedCode]);

  async function action(name: string, fn: () => Promise<void>): Promise<void> {
    setBusyAction(name);
    setErrorMessage(null);
    setMessage(null);
    try {
      await fn();
      await Promise.all([loadProviders(), loadDashboard(), loadOptimizer()]);
    } catch (e: unknown) {
      setErrorMessage(adminUiErrorMessage(e, t));
    } finally {
      setBusyAction(null);
    }
  }

  async function saveProvider(): Promise<void> {
    if (!selected || !edit) return;
    await action(`save:${selected.code}`, async () => {
      const priority = Number(edit.priority);
      if (!Number.isInteger(priority) || priority < 0) throw new Error("Укажите корректный приоритет.");
      await adminApiRequest(
        adminPath(ADMIN_ADS_PROVIDER_PATH, { code: selected.code }),
        "PUT",
        {
          body: {
            enabled: edit.enabled,
            priority,
            miniapp_enabled: edit.miniappEnabled,
            bot_enabled: edit.botEnabled,
            rewarded_enabled: edit.rewardedEnabled,
            public_config: edit.publicConfig,
            countries_allow: csv(edit.countriesAllow).map((item) => item.toUpperCase()),
            countries_block: csv(edit.countriesBlock).map((item) => item.toUpperCase()),
            languages_allow: csv(edit.languagesAllow),
            languages_block: csv(edit.languagesBlock),
            moderation_status: edit.moderationStatus.trim() || null,
          },
        },
      );
      setMessage("Настройки рекламного сервиса сохранены.");
    });
  }

  async function replaceSecret(field: string): Promise<void> {
    if (!selected) return;
    const value = String(secretValues[field] || "").trim();
    if (!value) {
      setErrorMessage("Введите новое значение секрета.");
      return;
    }
    await action(`secret:${selected.code}:${field}`, async () => {
      await adminApiRequest(
        adminPath(ADMIN_ADS_PROVIDER_SECRET_REPLACE_PATH, { code: selected.code }),
        "POST",
        { body: { field, value } },
      );
      setSecretValues((current) => ({ ...current, [field]: "" }));
      setMessage("Секрет заменён. Сохранённое значение повторно не показывается.");
    });
  }

  async function deleteSecret(field: string): Promise<void> {
    if (!selected) return;
    if (!window.confirm("Удалить сохранённый секрет этого рекламного сервиса?")) return;
    await action(`delete-secret:${selected.code}:${field}`, async () => {
      await adminApiRequest(
        adminPath(ADMIN_ADS_PROVIDER_SECRET_DELETE_PATH, { code: selected.code }),
        "POST",
        { body: { field } },
      );
      setMessage("Секрет удалён.");
    });
  }

  async function testProvider(mode: "configuration" | "sdk" | "request"): Promise<void> {
    if (!selected) return;
    await action(`test:${selected.code}:${mode}`, async () => {
      const result = await adminApiRequest<Record<string, unknown>>(
        adminPath(ADMIN_ADS_PROVIDER_TEST_PATH, { code: selected.code }),
        "POST",
        { body: { mode } },
      );
      const status = String(result.status || (result.configured ? "READY" : "NOT_CONFIGURED"));
      if (mode === "sdk" && status === "READY_FOR_CLIENT_SDK_TEST") {
        const publicConfig = (result.public_config || {}) as Record<string, unknown>;
        const adapter = getClientAdProvider(selected.code);
        await adapter.show(publicConfig);
        setMessage("Тестовый рекламный SDK завершил показ. EFHCb не начислялся.");
        return;
      }
      setMessage(`Проверка завершена: ${status}. Награда EFHCb не создавалась.`);
    });
  }

  async function resetErrors(): Promise<void> {
    if (!selected) return;
    await action(`reset:${selected.code}`, async () => {
      await adminApiRequest(
        adminPath(ADMIN_ADS_PROVIDER_RESET_ERRORS_PATH, { code: selected.code }),
        "POST",
      );
      setMessage("История текущей ошибки сброшена. Следующий запрос заново определит состояние.");
    });
  }

  async function applyOptimizer(): Promise<void> {
    await action("optimizer", async () => {
      const result = await adminApiRequest<Optimizer>(ADMIN_ADS_REVENUE_OPTIMIZER_APPLY_PATH, "POST", {
        body: { period: "30d", min_requests: 20 },
      });
      setOptimizer(result);
      setMessage("Глобальный порядок обновлён по фактическому доходу на рекламный запрос.");
    });
  }

  const publicFields = selected?.config_schema.filter((field) => !field.secret) || [];
  const secretFields = selected?.config_schema.filter((field) => field.secret) || [];
  const maxTimelineRevenue = Math.max(
    0.00000001,
    ...(dashboard?.timeline || []).map((row) => number(row.confirmed_revenue_usd) || number(row.estimated_revenue_usd)),
  );

  const periodViews = dashboard?.overall.completed_rewarded_views || 0;
  const periodRevenue = dashboard?.overall.confirmed_revenue_usd || dashboard?.overall.estimated_revenue_usd || "0";

  return (
    <AdminPage title={t("admin.ads")} backHref="/admin">
      <div className="space-y-4" data-eam-family="EAM-ADMIN-023" data-admin-ads-surface="tasks-simple-v192" data-admin-ads-owner-correction="v354">
        {errorMessage ? <TelegramEmptyState title="Не удалось обновить рекламные сервисы" detail={errorMessage} /> : null}
        {message ? <TelegramInfoBlock title="Результат">{message}</TelegramInfoBlock> : null}

        <AdminSectionCard
          title="Карта рекламы"
          subtitle="Короткая сводка. Настройка конкретного сервиса находится ниже."
          actions={<Button variant="secondary" onClick={() => void load()} disabled={loading}>{loading ? "Обновление…" : "Обновить"}</Button>}
        >
          <div className="grid gap-2 sm:grid-cols-2" data-admin-ads-map="v192" data-admin-ads-period-metrics="v387">
            {[
              ["Успешных просмотров", String(periodViews), `За период ${period}`],
              ["Доход", `$${periodRevenue}`, `За период ${period}`],
            ].map(([label, value, note]) => (
              <div
                key={String(label)}
                className="efhc-admin-ads-summary-secondary-v354 grid gap-1 rounded-xl border px-3 py-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center"
              >
                <div><strong className="text-sm">{label}</strong><div className="text-xs efhc-text-muted">{note}</div></div>
                <strong className="efhc-admin-ads-summary-value-v354 text-sm tabular-nums sm:text-right">{value}</strong>
              </div>
            ))}
          </div>
        </AdminSectionCard>

        <Card title="Обязательная реклама при выводе">
          <div className="space-y-2 text-sm" data-admin-ads-system-placement="withdraw-required">
            <div>Каждая новая заявка на вывод проходит обязательный рекламный показ через общий ADS routing.</div>
            <div>Пользовательский бонус за этот показ: <strong>0 EFHCb</strong>. Если рекламный показ не подтверждён, заявка на вывод не создаётся.</div>
            <details className="text-xs efhc-text-muted"><summary className="cursor-pointer">Технический placement</summary><code>{WITHDRAW_REQUIRED_AD_PLACEMENT_CODE}</code></details>
          </div>
        </Card>

        <AdminSectionCard title="Рекламные сервисы" subtitle="Как в Заданиях: выберите сервис слева — настройте выбранный справа.">
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(20rem,1fr)]">
            <div className="efhc-admin-ads-provider-cards space-y-2" data-admin-ads-position-layout="withdrawal-cards-v354">
              {providers.map((provider) => (
                <TelegramSectionRow
                  key={provider.code}
                  compact
                  title={provider.title}
                  subtitle={`${provider.enabled ? "Включён" : "Выключен"} · ${provider.is_configured ? "настроен" : "нужна настройка"} · приоритет ${provider.priority}`}
                  onClick={() => setSelectedCode(provider.code)}
                  className={`efhc-admin-ads-provider-row ${selected?.code === provider.code ? "efhc-admin-ads-provider-row-active-v354" : ""}`}
                  rightSlot={<span className="text-xs efhc-text-muted">{healthLabel(provider.health)}</span>}
                />
              ))}
              {!providers.length && !loading ? <TelegramEmptyState title="Рекламные сервисы не найдены" /> : null}
            </div>

            <div className="efhc-admin-ads-editor-card rounded-2xl border p-3">
              {selected && edit ? (
                <div className="space-y-4" data-admin-ads-provider-editor={selected.code}>
                  <div>
                    <strong className="block">{selected.title}</strong>
                    <div className="text-xs efhc-text-muted">Состояние: {healthLabel(selected.health)} · приоритет {selected.priority}</div>
                  </div>

                  <div className="grid gap-3 md:grid-cols-2">
                    <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={edit.enabled} onChange={(e) => setEdit({ ...edit, enabled: e.target.checked })} />Включить сервис</label>
                    <label className="space-y-1 text-sm"><span>Порядок показа</span><input className={fieldClass()} inputMode="numeric" value={edit.priority} onChange={(e) => setEdit({ ...edit, priority: e.target.value })} /></label>
                    <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={edit.miniappEnabled} onChange={(e) => setEdit({ ...edit, miniappEnabled: e.target.checked })} />Разрешить в мини-приложении</label>
                    <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={edit.botEnabled} onChange={(e) => setEdit({ ...edit, botEnabled: e.target.checked })} />Разрешить в Telegram-боте</label>
                    <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={edit.rewardedEnabled} onChange={(e) => setEdit({ ...edit, rewardedEnabled: e.target.checked })} />Разрешить показы с наградой</label>
                    <label className="space-y-1 text-sm"><span>Статус аккаунта или модерации</span><input className={fieldClass()} value={edit.moderationStatus} onChange={(e) => setEdit({ ...edit, moderationStatus: e.target.value })} placeholder="например: одобрен" /></label>
                  </div>

                  {publicFields.length ? <div className="grid gap-3 md:grid-cols-2">{publicFields.map((field) => (
                    <label key={field.name} className="space-y-1 text-sm"><span>{FIELD_LABELS[field.name] || field.name}{field.required ? " *" : ""}</span><input className={fieldClass()} value={edit.publicConfig[field.name] || ""} onChange={(e) => setEdit({ ...edit, publicConfig: { ...edit.publicConfig, [field.name]: e.target.value } })} /></label>
                  ))}</div> : null}

                  <details className="efhc-admin-ads-inset rounded-xl border p-3">
                    <summary className="cursor-pointer text-sm font-semibold">Страны, языки и дополнительные настройки</summary>
                    <div className="mt-3 grid gap-3 md:grid-cols-2">
                      <label className="space-y-1 text-sm"><span>Разрешённые страны, ISO-2</span><input className={fieldClass()} value={edit.countriesAllow} onChange={(e) => setEdit({ ...edit, countriesAllow: e.target.value })} placeholder="пусто = все" /></label>
                      <label className="space-y-1 text-sm"><span>Заблокированные страны, ISO-2</span><input className={fieldClass()} value={edit.countriesBlock} onChange={(e) => setEdit({ ...edit, countriesBlock: e.target.value })} /></label>
                      <label className="space-y-1 text-sm"><span>Разрешённые языки</span><input className={fieldClass()} value={edit.languagesAllow} onChange={(e) => setEdit({ ...edit, languagesAllow: e.target.value })} placeholder="ru, uk, en…" /></label>
                      <label className="space-y-1 text-sm"><span>Заблокированные языки</span><input className={fieldClass()} value={edit.languagesBlock} onChange={(e) => setEdit({ ...edit, languagesBlock: e.target.value })} /></label>
                    </div>
                  </details>

                  <div className="efhc-admin-ads-api-flat-v354 space-y-3" data-admin-ads-api-connection-panel={selected.code} data-admin-flat-group="true">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div>
                        <strong className="block text-sm">Подключение API</strong>
                        <div className="mt-1 text-xs efhc-text-muted">
                          Ключи и секреты сохраняются на сервере. Сохранённые значения показываются только в маскированном виде.
                        </div>
                      </div>
                      <span className="text-xs efhc-text-muted">
                        {selected.is_configured ? "Настроено" : "Требуется настройка"}
                      </span>
                    </div>

                    <div className="mt-3 grid gap-2 md:grid-cols-2">
                      <div className="efhc-admin-ads-status-inset rounded-xl border p-2 text-xs">
                        <span className="efhc-text-muted">Последнее успешное подтверждение</span>
                        <strong className="mt-1 block">{selected.last_success_at || "ещё не было"}</strong>
                      </div>
                      <div className="efhc-admin-ads-status-inset rounded-xl border p-2 text-xs">
                        <span className="efhc-text-muted">Последняя ошибка</span>
                        <strong className="mt-1 block">{selected.last_error_at || "нет"}</strong>
                        {selected.last_error_code ? <span className="mt-1 block efhc-text-muted">{selected.last_error_code}</span> : null}
                      </div>
                    </div>

                    {secretFields.length ? (
                      <div className="mt-3 space-y-3">
                        {secretFields.map((field) => (
                          <div key={field.name} className="efhc-admin-ads-secret-inset rounded-xl border p-3">
                            <div className="text-sm">
                              <b>{FIELD_LABELS[field.name] || field.name}</b> · сохранено: {selected.secret_masks[field.name] || "нет"}
                            </div>
                            <div className="mt-2 flex flex-wrap gap-2">
                              <input
                                className={`${fieldClass()} min-w-[220px] flex-1`}
                                type="password"
                                autoComplete="new-password"
                                value={secretValues[field.name] || ""}
                                onChange={(e) => setSecretValues((current) => ({ ...current, [field.name]: e.target.value }))}
                                placeholder="Новое значение"
                              />
                              <Button onClick={() => void replaceSecret(field.name)} disabled={busyAction !== null}>Заменить</Button>
                              <Button
                                variant="secondary"
                                onClick={() => void deleteSecret(field.name)}
                                disabled={!selected.secret_masks[field.name] || busyAction !== null}
                              >
                                Удалить
                              </Button>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="mt-3 text-xs efhc-text-muted">Для этого сервиса секретные поля не требуются.</div>
                    )}
                  </div>

                  <div className="flex flex-wrap gap-2">
                    <Button onClick={() => void saveProvider()} disabled={busyAction !== null}>Сохранить</Button>
                    <Button variant="secondary" onClick={() => void testProvider("configuration")} disabled={busyAction !== null}>Проверить настройку</Button>
                    <Button variant="secondary" onClick={() => void testProvider("sdk")} disabled={busyAction !== null}>Проверить показ</Button>
                    <Button variant="secondary" onClick={() => void testProvider("request")} disabled={busyAction !== null}>Проверить запрос</Button>
                    <Button variant="secondary" onClick={() => void resetErrors()} disabled={busyAction !== null}>Сбросить ошибку</Button>
                  </div>
                </div>
              ) : <TelegramEmptyState title="Выберите рекламный сервис" />}
            </div>
          </div>
        </AdminSectionCard>

        <details className="efhc-admin-ads-analytics-card rounded-3xl border border-[color:var(--tg-hint)]/20 p-4" data-admin-ads-analytics="collapsed-v192">
          <summary className="cursor-pointer text-sm font-semibold">Статистика и оптимизация рекламы</summary>
          <div className="mt-4 space-y-4">
            <Card title="Период статистики">
              <div className="flex flex-wrap gap-2">{(["24h", "7d", "30d"] as const).map((value) => <Button key={value} variant={period === value ? "primary" : "secondary"} onClick={() => { setPeriod(value); void action(`period:${value}`, async () => { await loadDashboard(value); }); }}>{value}</Button>)}<Button variant={period === "custom" ? "primary" : "secondary"} onClick={() => setPeriod("custom")}>Свой период</Button></div>
              {period === "custom" ? <div className="mt-3 flex flex-wrap gap-2"><input className={fieldClass()} type="date" value={customFrom} onChange={(e) => setCustomFrom(e.target.value)} aria-label="Начало периода" /><input className={fieldClass()} type="date" value={customTo} onChange={(e) => setCustomTo(e.target.value)} aria-label="Окончание периода" /><Button onClick={() => void action("period:custom", async () => { await loadDashboard("custom"); })}>Применить период</Button></div> : null}
            </Card>

            <Card title="Эффективность по сервисам"><div className="efhc-admin-table-wrap"><table className="efhc-admin-table"><thead><tr><th>Сервис</th><th>Запросы</th><th>Заполнение</th><th>Показы</th><th>Завершение</th><th>Учтено</th><th>Клики</th><th>Доход</th><th>Доход на 1000</th><th>Нет рекламы</th><th>Резервные переходы</th></tr></thead><tbody>{(dashboard?.providers || []).map((row) => <tr key={String(row.provider)}><td>{String(row.provider)}</td><td>{String(row.requests || 0)}</td><td>{(number(row.fill_rate) * 100).toFixed(1)}%</td><td>{String(row.shows || 0)}</td><td>{(number(row.completion_rate) * 100).toFixed(1)}%</td><td>{(number(row.valued_rate) * 100).toFixed(1)}%</td><td>{String(row.clicks || 0)}</td><td>${String(row.confirmed_revenue_usd || row.estimated_revenue_usd || "0")}</td><td>${String(row.ecpm_usd || "0")} / ${String(row.erpm_usd || "0")}</td><td>{String(row.no_fill || 0)}</td><td>{String(row.fallback_out || 0)}</td></tr>)}</tbody></table></div></Card>

            <Card title="Автоматическая оптимизация дохода"><p className="text-sm efhc-text-muted">Рекомендация строится по фактическому доходу на рекламный запрос. Это общий порядок сервисов, а не персональный рейтинг по стране или языку.</p><div className="mt-3 rounded-xl border p-3 text-sm">Рекомендуемый порядок: <b>{optimizer?.recommended_order?.join(" → ") || "пока недостаточно данных"}</b></div><div className="mt-3 flex flex-wrap gap-2"><Button variant="secondary" onClick={() => void loadOptimizer()} disabled={busyAction !== null}>Пересчитать</Button><Button onClick={() => void applyOptimizer()} disabled={!optimizer?.recommended_order?.length || busyAction !== null}>Применить порядок</Button></div></Card>

            <Card title="Страны, языки и задания"><div className="grid gap-4 lg:grid-cols-3"><div><h3 className="mb-2 font-semibold">Страны</h3>{(dashboard?.geo || []).slice(0,20).map((row) => <div key={String(row.country)} className="mb-1 text-sm">{String(row.country)} · просмотров {String(row.successful_views || 0)} · лучший по статистике {String(row.best_provider || "—")}</div>)}</div><div><h3 className="mb-2 font-semibold">Языки</h3>{(dashboard?.languages || []).map((row) => <div key={String(row.language)} className="mb-1 text-sm">{String(row.language)} · просмотров {String(row.successful_views || 0)}</div>)}</div><div><h3 className="mb-2 font-semibold">Задания</h3>{(dashboard?.tasks || []).slice(0,20).map((row,index) => <div key={`${String(row.task)}:${index}`} className="mb-1 text-sm">{String(row.task)} · основной {String(row.primary_provider || "авто")} → фактический {String(row.actual_provider || "—")} · выполнено {String(row.completions || 0)}</div>)}</div></div></Card>
          </div>
        </details>
      </div>
    </AdminPage>
  );
}
