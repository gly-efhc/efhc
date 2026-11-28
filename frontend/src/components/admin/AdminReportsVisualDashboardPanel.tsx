import React, { useMemo, useState } from "react";

import {
  AdminActionTable,
  AdminAreaChart,
  AdminDashboardGrid,
  AdminDashboardToolbar,
  AdminEmptyState,
  AdminErrorState,
  AdminFilterBar,
  AdminFreshnessBadge,
  AdminHeatStrip,
  AdminMiniBarChart,
  AdminPanelChrome,
  AdminPanelInspectorDrawer,
  AdminProgressBar,
  AdminRefreshPicker,
  AdminStatusCard,
  AdminTimeRangePicker,
  AdminTrendCard,
} from "./AdminDashboardUiKit";

type Overview = {
  ok: boolean;
  ts: string;
  counters: Record<string, number>;
  facts?: Record<string, string>;
  notes?: string | null;
};

type ReportScope = "economy" | "users" | "panels";
type ReportMode = "snapshot" | "counters" | "facts";

type MetricPoint = {
  key: string;
  label: string;
  value: number;
  display: string;
};

type Props = {
  overview: Overview | null;
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
};

const SANDBOX_SOURCE = [
  "ui-main chart-area-interactive",
  "section-cards",
  "data-table",
  "MaterialM EarningReports",
].join("; ");

const SCOPE_LABELS: Record<ReportScope, string> = {
  economy: "Экономика",
  users: "Пользователи",
  panels: "Панели",
};

const MODE_LABELS: Record<ReportMode, string> = {
  snapshot: "Сводка",
  counters: "Показатели",
  facts: "Факты",
};

function numberFrom(value: string | number | undefined): number {
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : 0;
  }
  const clean = String(value || "0")
    .replace(/\s/g, "")
    .replace(/,/g, ".");
  const parsed = Number(clean);
  return Number.isFinite(parsed) ? parsed : 0;
}

function displayFrom(value: string | number | undefined): string {
  if (value === undefined || value === null || value === "") return "0";
  return String(value);
}

function metric(
  key: string,
  label: string,
  value: string | number | undefined,
): MetricPoint {
  return {
    key,
    label,
    value: numberFrom(value),
    display: displayFrom(value),
  };
}

function buildMetrics(
  overview: Overview | null,
  scope: ReportScope,
): MetricPoint[] {
  const counters = overview?.counters || {};
  const facts = overview?.facts || {};

  if (scope === "users") {
    return [
      metric("users_total", "Всего", counters.users_total),
      metric("users_active", "Активные", counters.users_active),
      metric("users_inactive", "Неактивные", counters.users_inactive),
      metric("users_total_efhc", "EFHC", facts.users_total_efhc),
      metric(
        "users_total_generated_kwh",
        "kWh сгенерировано",
        facts.users_total_generated_kwh,
      ),
    ];
  }

  if (scope === "panels") {
    return [
      metric(
        "panels_total_bought",
        "Куплено",
        facts.panels_total_bought,
      ),
      metric(
        "panels_total_active",
        "Активные",
        facts.panels_total_active,
      ),
      metric(
        "panels_total_archived",
        "Архив",
        facts.panels_total_archived,
      ),
      metric(
        "panels_total_paid_efhc",
        "Списано EFHC",
        facts.panels_total_paid_efhc,
      ),
    ];
  }

  return [
    metric("bank_total_efhc", "Банк EFHC", facts.bank_total_efhc),
    metric("users_total_efhc", "Users EFHC", facts.users_total_efhc),
    metric(
      "users_total_exchanged_kwh",
      "kWh → EFHCm",
      facts.users_total_exchanged_kwh,
    ),
    metric(
      "referrals_total_bonus_paid_efhc",
      "Реф. бонусы",
      facts.referrals_total_bonus_paid_efhc,
    ),
    metric(
      "bank_users_balance_diff_efhc",
      "Bank/User diff",
      facts.bank_users_balance_diff_efhc,
    ),
  ];
}

function chartPoints(metrics: MetricPoint[]) {
  return metrics.map((item) => ({
    id: item.key,
    label: item.label,
    value: Math.abs(item.value),
  }));
}

function metricPercent(metricValue: number, total: number): number {
  if (!total) return 0;
  return Math.round((Math.abs(metricValue) / total) * 100);
}

function freshnessLabel(overview: Overview | null): string {
  if (!overview) return "ожидание данных";
  if (!overview.ok) return "данные с предупреждением";
  return "данные обновлены";
}

export function AdminReportsVisualDashboardPanel(props: Props) {
  const [scope, setScope] = useState<ReportScope>("economy");
  const [mode, setMode] = useState<ReportMode>("snapshot");
  const [selectedPoint, setSelectedPoint] = useState(0);
  const metrics = useMemo(
    () => buildMetrics(props.overview, scope),
    [props.overview, scope],
  );
  const points = useMemo(() => chartPoints(metrics), [metrics]);
  const selectedIndex = selectedPoint % Math.max(metrics.length, 1);
  const selectedMetric = metrics[selectedIndex];
  const totalValue = metrics.reduce(
    (sum, item) => sum + Math.abs(item.value),
    0,
  );
  const countersCount = Object.keys(
    props.overview?.counters || {},
  ).length;
  const factsCount = Object.keys(props.overview?.facts || {}).length;
  const primaryValue = metrics[0]?.display || "0";
  const secondaryValue = metrics[1]?.display || "0";
  const selectedPercent = metricPercent(
    selectedMetric?.value ?? 0,
    totalValue,
  );

  return (
    <section
      className="efhc-admin-reports-visual"
      data-admin-reports-grafana-like="1482"
      data-admin-reports-no-debug-json="true"
      data-admin-reports-no-raw-payload="true"
      data-admin-reports-no-synthetic="true"
      data-admin-reports-no-write-actions="true"
      data-admin-reports-truth="raw-derived"
      data-admin-sandbox-source={SANDBOX_SOURCE}
    >
      <AdminDashboardToolbar
        actions={(
          <AdminRefreshPicker
            disabled={props.loading}
            label="Интервал"
            onRefresh={props.onRefresh}
            refreshLabel={props.loading ? "Обновление" : "Обновить"}
            value="manual"
          />
        )}
        breadcrumb="Админ / Отчёты"
        freshness={(
          <AdminFreshnessBadge
            freshness={props.overview ? "fresh" : "unknown"}
            label={freshnessLabel(props.overview)}
            updatedAt={props.overview?.ts ?? "нет данных"}
          />
        )}
        subtitle={
          "Сводные показатели по экономике, пользователям и панелям "
          + "с удобным просмотром деталей."
        }
        timeRange={(
          <AdminTimeRangeControl mode={mode} onChange={setMode} />
        )}
        title="Отчёты"
        updatedAt={props.overview?.ts ?? "ожидание данных"}
      />

      <AdminFilterBar
        groups={[
          {
            key: "admin-reports-scope",
            label: "Срез",
            value: scope,
            options: [
              { key: "economy", label: "Экономика" },
              { key: "users", label: "Пользователи" },
              { key: "panels", label: "Панели" },
            ],
            onChange: (value) => {
              setScope(value as ReportScope);
              setSelectedPoint(0);
            },
            querySync: "disabled",
          },
        ]}
      />

      {props.error ? (
        <AdminErrorState title="Ошибка отчёта" text={props.error} />
      ) : null}

      <AdminDashboardGrid>
        <AdminStatusCard
          hint="Текущая сводка отчётов."
          label="Общая сводка"
          status={props.overview?.ok ? "success" : "stale"}
          tone={props.overview?.ok ? "success" : "warning"}
          value={props.overview?.ok ? "OK" : "ожидание"}
        />
        <AdminTrendCard
          hint="Выбранный раздел отчёта."
          label="Срез"
          tone="info"
          value={SCOPE_LABELS[scope]}
        />
        <AdminTrendCard
          hint={metrics[0]?.label || "нет метрики"}
          label="Главная метрика"
          tone="success"
          value={primaryValue}
        />
        <AdminTrendCard
          hint="Ключевые показатели и факты."
          label="Поля отчёта"
          tone="neutral"
          value={`${countersCount}/${factsCount}`}
        />
      </AdminDashboardGrid>

      <div className="efhc-admin-reports-visual_grid">
        <AdminPanelChrome
          footer={
            "График построен по текущим значениям сводки."
          }
          source="Сводка отчётов"
          status={props.overview ? "success" : "stale"}
          title="График текущих показателей"
          tone="info"
          updatedAt={props.overview?.ts ?? "нет данных"}
        >
          {props.overview ? (
            <>
              <AdminAreaChart
                ariaLabel="График показателей отчёта"
                emptyLabel="Нет данных"
                label={`${SCOPE_LABELS[scope]} · ${MODE_LABELS[mode]}`}
                points={points}
                source="Расчётные показатели"
                unit="Текущие данные"
              />
              <AdminMiniBarChart
                ariaLabel="Сравнение показателей отчёта"
                emptyLabel="Нет данных"
                label="Метрики среза"
                points={points}
                source="Показатели отчёта"
                unit="значение"
              />
            </>
          ) : (
            <AdminEmptyState
              title="Нет отчёта"
              text="Нажмите «Обновить», чтобы загрузить данные."
            />
          )}
        </AdminPanelChrome>

        <AdminPanelChrome
          footer="Выберите показатель, чтобы посмотреть его детали."
          source="Детали показателя"
          status={selectedMetric ? "success" : "empty"}
          title="Детали показателя"
          tone="neutral"
        >
          <AdminPanelInspectorDrawer
            open={Boolean(selectedMetric)}
            source="Выбранный показатель"
            title="Выбранный показатель"
          >
            <AdminActionTable
              rows={[
                {
                  label: "Метрика",
                  value: selectedMetric?.label || "—",
                  hint: selectedMetric?.key || "нет ключа",
                },
                {
                  label: "Значение",
                  value: selectedMetric?.display || "0",
                  hint: "Текущее значение",
                },
                {
                  label: "Доля",
                  value: `${selectedPercent}%`,
                  hint: "Расчётное отображение",
                },
              ]}
              title="Детали показателя"
            />
          </AdminPanelInspectorDrawer>
        </AdminPanelChrome>
      </div>

      <AdminPanelChrome
        footer="Показаны основные значения отчёта."
        source="Показатели отчёта"
        status={metrics.length ? "success" : "empty"}
        title="Показатели"
        tone="success"
      >
        {metrics.length ? (
          <div className="efhc-admin-reports-visual_deck">
            {metrics.map((item, index) => (
              <button
                className="efhc-admin-reports-visual_metric"
                data-selected={
                  index === selectedPoint % metrics.length
                }
                key={item.key}
                onClick={() => setSelectedPoint(index)}
                type="button"
              >
                <span>{item.label}</span>
                <strong>{item.display}</strong>
              </button>
            ))}
          </div>
        ) : (
          <AdminEmptyState title="Показателей нет" text="Данные отсутствуют." />
        )}
      </AdminPanelChrome>

      <AdminPanelChrome
        footer="Отчёт предназначен для просмотра."
        source="Правила отчёта"
        status="success"
        title="Правила безопасности"
        tone="warning"
      >
        <div className="efhc-admin-reports-grafana-boundary">
          <span>Текущие и расчётные показатели</span>
          <span>Только доступные показатели</span>
          <span>Без прогнозной истории</span>
          <span>Только основные данные</span>
          <span>Изменения выполняются только через подтверждённые действия</span>
        </div>
        <AdminHeatStrip
          ariaLabel="Правила отчёта"
          label="Состояние отчёта"
          points={[
            {
              id: "truth",
              label: "Проверено",
              tone: "success",
              value: 1,
            },
            {
              id: "synthetic",
              label: "Фактические показатели",
              tone: "warning",
              value: 1,
            },
            {
              id: "write",
              label: "Только просмотр",
              tone: "info",
              value: 1,
            },
          ]}
          source="Проверка отчёта"
        />
      </AdminPanelChrome>

      <AdminProgressBar
        ariaLabel="Доля выбранного показателя"
        label="Доля выбранного показателя"
        max={100}
        showValue
        source="Расчёт по показанным значениям"
        value={selectedPercent}
      />
    </section>
  );
}

function AdminTimeRangeControl(props: {
  mode: ReportMode;
  onChange: (value: ReportMode) => void;
}) {
  return (
    <AdminTimeRangePicker
      label="Режим"
      onChange={(value) => props.onChange(value as ReportMode)}
      options={[
        {
          key: "snapshot",
          label: "Сводка",
          description: "Текущая сводка",
        },
        {
          key: "counters",
          label: "Показатели",
          description: "Основные счётчики",
        },
        {
          key: "facts",
          label: "Факты",
          description: "Факты за текущий период",
        },
      ]}
      value={props.mode}
    />
  );
}

