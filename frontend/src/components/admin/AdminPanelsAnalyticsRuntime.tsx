import React, { useCallback, useEffect, useMemo, useState } from "react";

import {
  ADMIN_REPORTS_PANELS_PATH,
  type AdminDomainReportResponse,
} from "../../lib/api/generated/adminSeams";
import { adminSafeLoadError } from "../../lib/adminError";
import { useAdminLinkedTransport } from "../../queries/useAdminLinkedTransport";
import {
  AdminAreaChart,
  AdminChartCard,
  AdminDashboardGrid,
  AdminFilterBar,
  AdminKpiCard,
  AdminMiniBarChart,
  AdminStatusBadge,
} from "./AdminDashboardUiKit";

type RangeKey = "24" | "168" | "720" | "2160";
type BucketKey = "hour" | "day";

const RANGE_OPTIONS = [
  { key: "24", label: "24 часа" },
  { key: "168", label: "7 дней" },
  { key: "720", label: "30 дней" },
  { key: "2160", label: "90 дней" },
] as const;

function numberMetric(
  report: AdminDomainReportResponse | null,
  key: string,
): number {
  const value = report?.snapshot?.[key];
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function metricLabel(value: number, maximumFractionDigits = 2): string {
  return new Intl.NumberFormat("ru-RU", { maximumFractionDigits }).format(value);
}

function rangeLabel(value: RangeKey): string {
  return RANGE_OPTIONS.find((item) => item.key === value)?.label ?? value;
}

function trendLabel(value: string, bucket: BucketKey): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  if (bucket === "hour") {
    return parsed.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
  }
  return parsed.toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit" });
}

export function AdminPanelsAnalyticsRuntime() {
  const adminApiRequest = useAdminLinkedTransport();
  const [rangeHours, setRangeHours] = useState<RangeKey>("720");
  const [report, setReport] = useState<AdminDomainReportResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const bucket: BucketKey = rangeHours === "24" ? "hour" : "day";

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        range_hours: rangeHours,
        bucket,
      });
      const response = await adminApiRequest<AdminDomainReportResponse>(
        `${ADMIN_REPORTS_PANELS_PATH}?${params.toString()}`,
        "GET",
      );
      setReport(response);
    } catch (err: unknown) {
      setReport(null);
      setError(adminSafeLoadError(err));
    } finally {
      setLoading(false);
    }
  }, [adminApiRequest, bucket, rangeHours]);

  useEffect(() => {
    void load();
  }, [load]);

  const total = numberMetric(report, "total_panels");
  const active = numberMetric(report, "active_panels");
  const archived = numberMetric(report, "archived_panels");
  const created = numberMetric(report, "created_in_range");
  const expiring7 = numberMetric(report, "expiring_7d");
  const expiring30 = numberMetric(report, "expiring_30d");
  const expiredActive = numberMetric(report, "expired_but_active");
  const missingExpiry = numberMetric(report, "missing_expiry");
  const avgLifetime = numberMetric(report, "avg_lifetime_days");
  const generated = numberMetric(report, "generated_kwh_total");
  const baseRate = numberMetric(report, "active_base_rate_total");

  const statusPoints = useMemo(
    () => [
      { id: "active", label: "Активные", value: active, tone: "success" as const },
      { id: "archive", label: "Архив", value: archived, tone: "neutral" as const },
      { id: "created", label: "Созданы", value: created, tone: "info" as const },
      { id: "expiring", label: "Завершатся ≤30д", value: expiring30, tone: "warning" as const },
    ],
    [active, archived, created, expiring30],
  );

  const agePoints = useMemo(
    () => [
      { id: "under30", label: "<30 дней", value: numberMetric(report, "active_age_under_30d") },
      { id: "30to119", label: "30–119 дней", value: numberMetric(report, "active_age_30_119d") },
      { id: "120plus", label: "120+ дней", value: numberMetric(report, "active_age_120d_plus") },
    ],
    [report],
  );

  const trendPoints = useMemo(
    () => (report?.trend ?? []).map((point, index) => ({
      id: `${point.bucket}-${index}`,
      label: trendLabel(point.bucket, bucket),
      value: point.value,
    })),
    [bucket, report?.trend],
  );

  return (
    <section
      className="space-y-4"
      data-admin-panels-analytics="v174.32"
      data-admin-panels-analytics-source="admin-reports-panels"
      data-admin-panels-analytics-synthetic={"false"}
    >
      <AdminFilterBar
        groups={[
          {
            key: "panel-analytics-range",
            label: "Период аналитики",
            value: rangeHours,
            options: RANGE_OPTIONS.map((item) => ({ key: item.key, label: item.label })),
            onChange: (value) => setRangeHours(value as RangeKey),
            querySync: "disabled",
          },
        ]}
      >
        <AdminStatusBadge
          label={loading ? "Обновление" : error ? "Ошибка данных" : "Данные сервера"}
          tone={error ? "danger" : loading ? "warning" : "success"}
        />
      </AdminFilterBar>

      <AdminDashboardGrid>
        <AdminKpiCard label="Всего панелей" value={metricLabel(total, 0)} hint="Все панели в базе." tone="info" />
        <AdminKpiCard label="Активные" value={metricLabel(active, 0)} hint="Работают сейчас." tone="success" />
        <AdminKpiCard label="Архив" value={metricLabel(archived, 0)} hint="Неактивные или архивные." tone="neutral" />
        <AdminKpiCard label={`Созданы · ${rangeLabel(rangeHours)}`} value={metricLabel(created, 0)} hint="Новые панели за выбранный период." tone="info" />
        <AdminKpiCard label="Завершатся ≤7 дней" value={metricLabel(expiring7, 0)} hint="Активные панели рядом с окончанием срока." tone={expiring7 ? "warning" : "success"} />
        <AdminKpiCard label="Завершатся ≤30 дней" value={metricLabel(expiring30, 0)} hint="Планируемое завершение в ближайшие 30 дней." tone={expiring30 ? "warning" : "success"} />
        <AdminKpiCard label="Средняя жизнь" value={`${metricLabel(avgLifetime, 1)} д`} hint="Фактическая средняя продолжительность панели." tone="neutral" />
        <AdminKpiCard label="Сгенерировано" value={`${metricLabel(generated, 4)} kWh`} hint="Суммарная генерация всех панелей." tone="info" />
      </AdminDashboardGrid>

      <div className="grid gap-4 lg:grid-cols-2">
        <AdminChartCard
          title="Панели по состоянию"
          subtitle={`Активные, архив, новые и близкие к завершению · ${rangeLabel(rangeHours)}.`}
        >
          <AdminMiniBarChart ariaLabel="Панели по состоянию" points={statusPoints} unit="панели" />
        </AdminChartCard>

        <AdminChartCard
          title="Возраст активных панелей"
          subtitle="Распределение активных панелей по сроку с момента активации."
        >
          <AdminMiniBarChart ariaLabel="Возраст активных панелей" points={agePoints} unit="панели" />
        </AdminChartCard>
      </div>

      <AdminChartCard
        title="Создание панелей во времени"
        subtitle={`Реальный временной ряд за ${rangeLabel(rangeHours)}. Никаких demo/synthetic данных.`}
        meta={<AdminStatusBadge label={`Базовая скорость: ${metricLabel(baseRate, 8)} kWh/с`} tone="info" />}
      >
        <AdminAreaChart
          ariaLabel="Создание панелей во времени"
          emptyLabel={error || report?.empty_reason || "Нет созданных панелей за период"}
          label="Создано панелей"
          points={trendPoints}
          unit="панели"
        />
        <div className="mt-3 flex flex-wrap gap-2 text-xs">
          <AdminStatusBadge label={`Просрочены, но active: ${metricLabel(expiredActive, 0)}`} tone={expiredActive ? "danger" : "success"} />
          <AdminStatusBadge label={`Без expires_at: ${metricLabel(missingExpiry, 0)}`} tone={missingExpiry ? "warning" : "success"} />
        </div>
      </AdminChartCard>
    </section>
  );
}
