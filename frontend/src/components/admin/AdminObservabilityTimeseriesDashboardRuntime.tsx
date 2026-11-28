import React, { useCallback, useEffect, useMemo, useState } from "react";

import {
  ADMIN_OBSERVABILITY_SUMMARY_PATH,
  ADMIN_OBSERVABILITY_TIMESERIES_PATH,
  type AdminObservabilitySummaryResponse,
  type AdminObservabilityTimeseriesResponse,
} from "../../lib/api/generated/adminSeams";
import {
  AdminAreaChart,
  AdminDashboardGrid,
  AdminDashboardToolbar,
  AdminFilterBar,
  AdminFreshnessBadge,
  AdminKpiCard,
  AdminPanelChrome,
  AdminRefreshPicker,
  AdminStatusBadge,
} from "./AdminDashboardUiKit";
import { adminSafeLoadError } from "../../lib/adminError";
import { useAdminLinkedTransport } from "../../queries/useAdminLinkedTransport";

const METRIC_OPTIONS = [
  {
    key: "efhc_transfer_count",
    label: "EFHC события",
    description: "Количество операций EFHC",
  },
  {
    key: "efhc_transfer_amount",
    label: "EFHC оборот",
    description: "Общий объём зачислений и списаний",
  },
  {
    key: "efhc_credit_amount",
    label: "EFHC зачисления",
    description: "Только направление зачисления",
  },
  {
    key: "efhc_debit_amount",
    label: "EFHC списания",
    description: "Только направление списания",
  },
  {
    key: "users_created",
    label: "Новые пользователи",
    description: "Количество новых пользователей",
  },
  {
    key: "panels_created",
    label: "Новые панели",
    description: "Количество новых панелей",
  },
  {
    key: "withdrawals_created",
    label: "Созданные выводы",
    description: "Количество созданных заявок",
  },
  {
    key: "payment_intents_created",
    label: "Платёжные намерения",
    description: "Количество созданных платежей",
  },
] as const;

const RANGE_OPTIONS = [
  { key: "24", label: "24 часа" },
  { key: "168", label: "7 дней" },
  { key: "720", label: "1 месяц" },
  { key: "8760", label: "1 год" },
] as const;

const BUCKET_OPTIONS = [
  { key: "hour", label: "час" },
  { key: "day", label: "день" },
] as const;

type MetricKey = typeof METRIC_OPTIONS[number]["key"];
type BucketKey = typeof BUCKET_OPTIONS[number]["key"];
type SnapshotState = {
  summary: AdminObservabilitySummaryResponse | null;
  series: AdminObservabilityTimeseriesResponse | null;
  loading: boolean;
  error: string | null;
  updatedAt: string | null;
};

function parseValue(value: string): number {
  const parsed = Number(String(value || "0").replace(",", "."));
  return Number.isFinite(parsed) ? parsed : 0;
}

function valueLabel(value: string | undefined): string {
  if (!value) return "0";
  return value;
}

function metricLabel(metric: string): string {
  return METRIC_OPTIONS.find((item) => item.key === metric)?.label ?? metric;
}

function queryPath(metric: MetricKey, bucket: BucketKey, rangeHours: string) {
  const params = new URLSearchParams({
    metric,
    bucket,
    range_hours: rangeHours,
  });
  return `${ADMIN_OBSERVABILITY_TIMESERIES_PATH}?${params.toString()}`;
}

function summaryValue(
  summary: AdminObservabilitySummaryResponse | null,
  key: string,
): string {
  return summary?.metrics.find((item) => item.key === key)?.value ?? "—";
}

export function AdminObservabilityTimeseriesDashboardRuntime() {
  const adminApiRequest = useAdminLinkedTransport();
  const [metric, setMetric] = useState<MetricKey>("efhc_transfer_count");
  const [bucket, setBucket] = useState<BucketKey>("hour");
  const [rangeHours, setRangeHours] = useState("24");
  const [snapshot, setSnapshot] = useState<SnapshotState>({
    summary: null,
    series: null,
    loading: false,
    error: null,
    updatedAt: null,
  });

  const refresh = useCallback(() => {
    setSnapshot((current) => ({ ...current, loading: true, error: null }));
    void Promise.all([
      adminApiRequest<AdminObservabilitySummaryResponse>(
        ADMIN_OBSERVABILITY_SUMMARY_PATH,
        "GET",
      ),
      adminApiRequest<AdminObservabilityTimeseriesResponse>(
        queryPath(metric, bucket, rangeHours),
        "GET",
      ),
    ])
      .then(([summary, series]) => {
        setSnapshot({
          summary,
          series,
          loading: false,
          error: null,
          updatedAt: new Date().toISOString(),
        });
      })
      .catch((error: unknown) => {
        const message = adminSafeLoadError(error);
        setSnapshot((current) => ({
          ...current,
          loading: false,
          error: message,
          updatedAt: new Date().toISOString(),
        }));
      });
  }, [adminApiRequest, bucket, metric, rangeHours]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const points = useMemo(() => {
    const rawPoints = Array.isArray(snapshot.series?.points)
      ? snapshot.series.points
      : [];
    return rawPoints.map((point) => ({
      id: point.ts,
      label: point.label ?? point.ts,
      value: parseValue(point.value),
    }));
  }, [snapshot.series]);

  const freshness = snapshot.error
    ? "stale"
    : snapshot.loading
      ? "unknown"
      : "fresh";
  const status = snapshot.error
    ? "error"
    : snapshot.loading
      ? "loading"
      : points.length
        ? "success"
        : "empty";

  return (
    <section
      className="efhc-admin-observability-timeseries efhc-dashboard-surface"
      data-admin-observability-timeseries-dashboard="1492"
      data-admin-observability-truth="real_timeseries"
      data-admin-observability-synthetic={"false"}
      data-admin-observability-no-fake-series="true"
      data-admin-observability-no-write-actions="true"
      data-admin-observability-no-idempotency-key="true"
    >
      <AdminDashboardToolbar
        title="Динамика показателей"
        subtitle="Динамика операционных показателей за выбранный период."
        breadcrumb="Админ / Отчёты / Динамика"
        refresh={(
          <AdminRefreshPicker
            label="Период"
            onRefresh={refresh}
            refreshLabel="Обновить"
          />
        )}
        freshness={(
          <AdminFreshnessBadge
            freshness={freshness}
            label={snapshot.error ? "ошибка" : "данные загружены"}
          />
        )}
        updatedAt={
          snapshot.updatedAt
            ? `Обновлено: ${snapshot.updatedAt}`
            : "ожидается первая загрузка"
        }
      />

      <AdminFilterBar
        groups={[
          {
            label: "Метрика",
            value: metric,
            options: [...METRIC_OPTIONS],
            onChange: (value) => setMetric(value as MetricKey),
            querySync: "disabled",
          },
          {
            label: "Шаг",
            value: bucket,
            options: [...BUCKET_OPTIONS],
            onChange: (value) => setBucket(value as BucketKey),
            querySync: "disabled",
          },
          {
            label: "Период",
            value: rangeHours,
            options: [...RANGE_OPTIONS],
            onChange: setRangeHours,
            querySync: "disabled",
          },
        ]}
      />

      <AdminDashboardGrid>
        <AdminKpiCard
          label="Операции EFHC"
          value={summaryValue(snapshot.summary, "efhc_transfer_events_total")}
          meta="Текущая сводка"
          hint="Количество операций за выбранный период"
          tone="info"
        />
        <AdminKpiCard
          label="Оборот EFHC"
          value={summaryValue(snapshot.summary, "efhc_transfer_amount_total")}
          meta="Зачисления + списания"
          hint="Это оборот, не чистый баланс."
          tone="warning"
        />
        <AdminKpiCard
          label="Точек на графике"
          value={String(points.length)}
          meta={snapshot.series?.unit ?? "единицы"}
          hint={snapshot.series?.empty_reason ?? "Данные за выбранный период"}
          tone={points.length ? "success" : "neutral"}
        />
        <AdminKpiCard
          label="Данные"
          value={snapshot.series?.data_kind ?? "—"}
          meta={snapshot.series ? "Фактические" : "Ожидание"}
          hint="График показывает фактическую динамику операционных показателей."
          tone="success"
        />
      </AdminDashboardGrid>

      <AdminPanelChrome
        title={`${metricLabel(metric)} · ${bucket}`}
        subtitle="Динамика ключевых показателей EFHC."
        status={status}
        source="История показателей"
      >
        <AdminAreaChart
          ariaLabel="Динамика показателей"
          dataKind="real_timeseries"
          emptyLabel={snapshot.series?.empty_reason ?? "Нет точек в диапазоне"}
          points={points}
          source="История показателей"
          synthetic={false}
          tone="info"
          unit={snapshot.series?.unit ?? "ед."}
        />
        <div className="mt-3 flex flex-wrap gap-2">
          <AdminStatusBadge label="История" tone="success" />
          <AdminStatusBadge label="Фактические данные" tone="success" />
          <AdminStatusBadge label="Только просмотр" tone="info" />
          <AdminStatusBadge label="Без прогнозной линии" tone="warning" />
        </div>
      </AdminPanelChrome>

      <AdminPanelChrome
        title="Правила отображения"
        subtitle="Показывается только доступная история показателей."
        status="success"
        source="История показателей"
      >
        <p className="text-sm text-slate-200">
          Показатели предназначены для просмотра и анализа. Показатель<strong> оборота EFHC </strong>
          показывает сумму зачислений и списаний; направления доступны отдельными показателями.
        </p>
      </AdminPanelChrome>

      {snapshot.error ? (
        <AdminPanelChrome
          title="Не удалось загрузить данные"
          subtitle="Не удалось загрузить историю показателей."
          status="error"
          tone="danger"
          source="Состояние загрузки"
        >
          <p className="text-sm text-red-200">{snapshot.error}</p>
        </AdminPanelChrome>
      ) : null}
    </section>
  );
}
