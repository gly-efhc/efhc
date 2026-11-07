import React, { useMemo, useState } from "react";

import { format8, sumScaledDown } from "../../lib/format";
import {
  AdminActionTable,
  AdminDashboardGrid,
  AdminDashboardToolbar,
  AdminFilterBar,
  AdminFlowMapCard,
  AdminFreshnessBadge,
  AdminHeatStrip,
  AdminKpiCard,
  AdminMiniBarChart,
  AdminPanelChrome,
  AdminProgressBar,
  AdminRefreshPicker,
  AdminStatusBadge,
} from "./AdminDashboardUiKit";
import type { DbId } from "../../types/db-id";


export type AdminPanelsDashboardItem = {
  id: DbId;
  is_active: boolean;
  created_at: string;
  expires_at?: string | null;
  archived_at?: string | null;
  last_generated_at?: string | null;
  base_gen_per_sec?: string | null;
  generated_kwh: string;
};

export type AdminPanelsDashboardRuntimeProps = {
  items: AdminPanelsDashboardItem[];
  currentItems: AdminPanelsDashboardItem[];
  activeOnly: boolean;
  filterApplied: boolean;
  loading?: boolean;
  error?: string | null;
  updatedAt?: string;
  onRefresh: () => void;
};

type PanelScope = "all" | "active" | "archive" | "attention";

type PanelPoint = {
  id: string;
  label: string;
  value: number;
  tone?: "success" | "warning" | "info" | "neutral" | "danger";
};

const DAY_MS = 24 * 60 * 60 * 1000;
const PANEL_LIFECYCLE_DAYS = 180;
const PANEL_LIFECYCLE_MS = PANEL_LIFECYCLE_DAYS * DAY_MS;

function humanInt(value: number): string {
  return value.toLocaleString("ru-RU");
}

function parseTime(value: string | null | undefined): number | null {
  if (!value) return null;
  const ts = Date.parse(value);
  return Number.isFinite(ts) ? ts : null;
}

function pct(part: number, total: number): number {
  if (!total) return 0;
  return Math.round((part / total) * 100);
}

function sumDecimal(
  items: AdminPanelsDashboardItem[],
  field: "generated_kwh" | "base_gen_per_sec",
): string {
  return items.reduce(
    (acc, item) => sumScaledDown(acc, String(item[field] || "0"), 8),
    "0",
  );
}

function daysUntil(value: string | null | undefined): number | null {
  const ts = parseTime(value);
  if (ts === null) return null;
  return Math.ceil((ts - Date.now()) / DAY_MS);
}

function panelAgeDays(item: AdminPanelsDashboardItem): number | null {
  const created = parseTime(item.created_at);
  if (created === null) return null;
  return Math.max(0, Math.floor((Date.now() - created) / DAY_MS));
}

function lifecyclePercent(item: AdminPanelsDashboardItem): number | null {
  const created = parseTime(item.created_at);
  const expires = parseTime(item.expires_at);
  if (created === null || expires === null || expires <= created) return null;
  const elapsed = Date.now() - created;
  const total = expires - created;
  return Math.min(100, Math.max(0, Math.round((elapsed / total) * 100)));
}

function averageLifecyclePercent(items: AdminPanelsDashboardItem[]): number | null {
  const values = items
    .filter((item) => item.is_active)
    .map(lifecyclePercent)
    .filter((value): value is number => value !== null);
  if (!values.length) return null;
  return Math.round(values.reduce((acc, value) => acc + value, 0) / values.length);
}

function nextExpiryLabel(items: AdminPanelsDashboardItem[]): string {
  const activeDates = items
    .filter((item) => item.is_active)
    .map((item) => parseTime(item.expires_at))
    .filter((value): value is number => value !== null)
    .sort((a, b) => a - b);
  if (!activeDates.length) return "нет даты";
  const days = Math.ceil((activeDates[0] - Date.now()) / DAY_MS);
  if (days < 0) return "просрочено";
  if (days === 0) return "сегодня";
  return `${days} д`;
}

function scopeLabel(scope: PanelScope): string {
  if (scope === "active") return "Активные";
  if (scope === "archive") return "Архив";
  if (scope === "attention") return "Внимание";
  return "Все панели";
}

function buildPanelPoints(
  active: number,
  archived: number,
  expiringSoon: number,
  missingExpiry: number,
): PanelPoint[] {
  return [
    { id: "active", label: "active", value: active, tone: "success" },
    { id: "archive", label: "Архив", value: archived, tone: "neutral" },
    {
      id: "expiring-soon",
      label: "expiring soon",
      value: expiringSoon,
      tone: "warning",
    },
    {
      id: "missing-expiry",
      label: "missing expiry",
      value: missingExpiry,
      tone: "danger",
    },
  ];
}

function freshnessLabel(props: AdminPanelsDashboardRuntimeProps): string {
  if (props.error) return "ошибка загрузки панелей";
  if (props.loading) return "обновление";
  if (!props.items.length) return "панелей нет";
  return "данные панелей загружены";
}

export function AdminPanelsDashboardRuntime(
  props: AdminPanelsDashboardRuntimeProps,
) {
  const [scope, setScope] = useState<PanelScope>("all");
  const active = props.items.filter((item) => item.is_active).length;
  const archived = props.items.filter((item) => !item.is_active).length;
  const total = props.items.length;
  const activePercent = pct(active, total);
  const archivePercent = pct(archived, total);
  const expiringSoon = props.items.filter((item) => {
    if (!item.is_active) return false;
    const days = daysUntil(item.expires_at);
    return days !== null && days >= 0 && days <= 14;
  }).length;
  const missingExpiry = props.items.filter(
    (item) => item.is_active && !item.expires_at,
  ).length;
  const attentionTotal = expiringSoon + missingExpiry;
  const generatedTotal = format8(sumDecimal(props.items, "generated_kwh"));
  const baseRateTotal = format8(sumDecimal(props.items, "base_gen_per_sec"));
  const lifecycle = averageLifecyclePercent(props.items);
  const lifecycleLabel = lifecycle === null ? "нет дат" : `${lifecycle}%`;
  const hasSnapshot = Boolean(props.items.length);
  const points = useMemo(
    () => buildPanelPoints(active, archived, expiringSoon, missingExpiry),
    [active, archived, expiringSoon, missingExpiry],
  );
  const under30 = props.items.filter((item) => {
    const age = panelAgeDays(item);
    return item.is_active && age !== null && age < 30;
  }).length;
  const midLifecycle = props.items.filter((item) => {
    const age = panelAgeDays(item);
    return item.is_active && age !== null && age >= 30 && age < 120;
  }).length;
  const lateLifecycle = props.items.filter((item) => {
    const age = panelAgeDays(item);
    return item.is_active && age !== null && age >= 120;
  }).length;
  const freshness = props.error
    ? "stale"
    : props.loading
      ? "unknown"
      : hasSnapshot
        ? "fresh"
        : "stale";

  return (
    <section
      className="efhc-admin-panels-dashboard-runtime"
      data-admin-panels-dashboard-runtime="1487"
      data-admin-panels-truth="raw-derived"
      data-admin-panels-no-synthetic="true"
      data-admin-panels-no-write-actions="true"
      data-admin-panels-no-raw-payload="true"
      data-admin-panels-no-debug-json="true"
      data-admin-panels-no-secrets="true"
      data-admin-panels-no-fake-activation-trends="true"
      data-admin-panels-lifecycle-safe="true"
      data-admin-panels-economy="read-only"
    >
      <AdminDashboardToolbar
        title="Обзор панелей"
        subtitle="Обзор состояния и срока действия панелей."
        breadcrumb="Admin / Panels"
        refresh={(
          <AdminRefreshPicker
            disabled={props.loading}
            label="Обновление"
            onRefresh={props.onRefresh}
            refreshLabel="Обновить panels"
            value="manual"
          />
        )}
        updatedAt={props.updatedAt || "Данные панелей"}
        freshness={(
          <AdminFreshnessBadge
            freshness={freshness}
            label={freshnessLabel(props)}
            updatedAt={props.updatedAt || "Текущие данные"}
          />
        )}
        filters={(
          <AdminFilterBar
            groups={[
              {
                key: "panel-scope",
                label: "Срез",
                value: scope,
                queryKey: "panel_scope",
                querySync: "safe_display_only",
                onChange: (value) => setScope(value as PanelScope),
                options: [
                  { key: "all", label: "Все" },
                  { key: "active", label: "Активные" },
                  { key: "archive", label: "Архив" },
                  { key: "attention", label: "Внимание" },
                ],
              },
            ]}
            onReset={() => setScope("all")}
            resetLabel="Сбросить"
          />
        )}
      />

      <AdminDashboardGrid>
        <AdminKpiCard
          label="Всего панелей"
          value={humanInt(total)}
          meta={props.filterApplied ? "Результат фильтра" : "Все панели"}
          hint="Количество панелей в текущей выборке."
          tone="info"
        />
        <AdminKpiCard
          label="Активные"
          value={humanInt(active)}
          meta={`${activePercent}%`}
          hint="Количество активных панелей."
          tone={active ? "success" : "neutral"}
        />
        <AdminKpiCard
          label="Архив"
          value={humanInt(archived)}
          meta={`${archivePercent}%`}
          hint="Количество неактивных панелей."
          tone={archived ? "neutral" : "info"}
        />
        <AdminKpiCard
          label="Внимание"
          value={humanInt(attentionTotal)}
          meta={`${expiringSoon} скоро завершатся · ${missingExpiry} без даты завершения`}
          hint="Панели, срок которых требует внимания."
          tone={attentionTotal ? "warning" : "success"}
        />
      </AdminDashboardGrid>

      <div className="efhc-admin-panels-dashboard-grid">
        <AdminPanelChrome
          title="Состояние панелей"
          subtitle="Распределение панелей по текущему состоянию."
          status={props.error ? "error" : hasSnapshot ? "success" : "stale"}
          tone={attentionTotal ? "warning" : "success"}
          source="Панели"
          updatedAt={props.updatedAt || "Текущие данные"}
        >
          <AdminMiniBarChart
            ariaLabel="Срок действия панелей"
            dataKind="derived"
            points={points}
          />
          <div className="efhc-admin-panels-dashboard-status-grid">
            {points.map((point) => (
              <div
                className="efhc-admin-panels-dashboard-status"
                data-admin-panel-lifecycle-status={point.id}
                key={point.id}
              >
                <span>{point.label}</span>
                <strong>{humanInt(point.value)}</strong>
              </div>
            ))}
          </div>
        </AdminPanelChrome>

        <AdminPanelChrome
          title="Срок действия панелей"
          subtitle={`Выбранный раздел: ${scopeLabel(scope)}.`}
          status={props.error ? "error" : hasSnapshot ? "success" : "stale"}
          tone={attentionTotal ? "warning" : "info"}
          source="Срок действия панелей"
          updatedAt={props.updatedAt || "Текущие данные"}
        >
          <AdminProgressBar
            ariaLabel="Доля активных панелей"
            dataKind="derived"
            label="Активные панели"
            value={activePercent}
          />
          <AdminProgressBar
            ariaLabel="Доля архивных панелей"
            dataKind="derived"
            label="Архивные панели"
            tone="neutral"
            value={archivePercent}
          />
          <AdminProgressBar
            ariaLabel="Средний срок действия панелей"
            dataKind="derived"
            label="Средний срок"
            tone={lifecycle === null ? "neutral" : "warning"}
            value={lifecycle ?? 0}
          />
          <div className="efhc-admin-panels-dashboard-readiness">
            <AdminStatusBadge label={`Срок: ${lifecycleLabel}`} tone="info" />
            <AdminStatusBadge label={`Ближайшее завершение: ${nextExpiryLabel(props.items)}`} tone="warning" />
            <AdminStatusBadge label="Срок панели — 180 дней" tone="success" />
          </div>
        </AdminPanelChrome>
      </div>

      <div className="efhc-admin-panels-dashboard-grid">
        <AdminPanelChrome
          title="Возраст панелей"
          subtitle="Распределение по датам создания."
          status={hasSnapshot ? "success" : "empty"}
          tone="neutral"
          source="По дате создания"
          updatedAt={props.updatedAt || "Текущие данные"}
        >
          <AdminHeatStrip
            ariaLabel="Возраст панелей"
            points={[
              { id: "under-30", label: "до 30 дней", value: under30 },
              { id: "middle", label: "30–119 дней", value: midLifecycle },
              { id: "late", label: "120 дней и более", value: lateLifecycle },
              { id: "archive", label: "Архив", value: archived },
            ]}
          />
          <AdminActionTable
            title="Итоговые значения"
            rows={[
              {
                label: "Сгенерировано",
                value: `${generatedTotal} kWh`,
                hint: "Сумма генерации по текущей выборке.",
              },
              {
                label: "Базовая скорость",
                value: `${baseRateTotal} kWh/с`,
                hint: "Суммарная базовая скорость генерации.",
              },
            ]}
          />
        </AdminPanelChrome>

      </div>

      <AdminPanelChrome
        title="Правила управления панелями"
        subtitle="Сводка показывает состояние и срок действия панелей."
        status="success"
        tone="info"
        source="Действия управления панелями"
        updatedAt="Состояние панели"
      >
        <AdminFlowMapCard
          title="Порядок работы с панелями"
          nodes={[
            {
              label: "Текущие данные",
              value: "Только просмотр",
              active: true,
              hint: "Сначала проверьте текущее состояние панели.",
            },
            {
              label: "Требуют внимания",
              value: humanInt(attentionTotal),
              hint: "Панели с близкой датой завершения или без даты завершения.",
            },
            {
              label: "Журнал",
              value: "JSON / CSV / XLSX",
              hint: "Полный реестр созданных панелей скачивается отдельной кнопкой на странице.",
            },
            {
              label: "Проверено",
              value: "Текущие данные",
              hint: "Срок действия панелей — 180 дней; показатели генерации не меняются.",
            },
          ]}
        />
        <p className="efhc-admin-panels-dashboard-boundary">
          Постоянный список отдельных панелей на аналитической странице не показывается.</p>
      </AdminPanelChrome>
    </section>
  );
}
