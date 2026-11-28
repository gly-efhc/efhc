import React, { useCallback, useEffect, useMemo, useState } from "react";
import { formatD8ToHuman } from "../../lib/format";

import {
  ADMIN_REPORTS_BANK_PATH,
  ADMIN_REPORTS_DEPOSITS_PATH,
  ADMIN_REPORTS_PANELS_PATH,
  ADMIN_REPORTS_USERS_PATH,
  ADMIN_REPORTS_WITHDRAWALS_PATH,
  type AdminDomainReportResponse,
} from "../../lib/api/generated/adminSeams";
import { adminSafeLoadError } from "../../lib/adminError";
import { useAdminLinkedTransport } from "../../queries/useAdminLinkedTransport";
import {
  AdminAreaChart,
  AdminDashboardGrid,
  AdminDashboardToolbar,
  AdminErrorState,
  AdminFilterBar,
  AdminFreshnessBadge,
  AdminKpiCard,
  AdminPanelChrome,
  AdminRefreshPicker,
  AdminStatusBadge,
} from "./AdminDashboardUiKit";

type DomainKey = "users" | "bank" | "panels" | "withdrawals" | "deposits";
type BucketKey = "hour" | "day";
type KpiTone = "neutral" | "success" | "warning" | "danger" | "info";

type KpiConfig = {
  key: string;
  label: string;
  hint: string;
  tone: KpiTone;
};

type DomainConfig = {
  key: DomainKey;
  title: string;
  subtitle: string;
  path: string;
  trendLabel: string;
  unit: string;
  kpis: readonly KpiConfig[];
};

type LoadResult = {
  key: DomainKey;
  report: AdminDomainReportResponse | null;
  error: string | null;
};

const DOMAIN_CONFIGS: readonly DomainConfig[] = [
  {
    key: "users",
    title: "Пользователи",
    subtitle: "Аккаунты, активность, панели и привязанные TON-кошельки.",
    path: ADMIN_REPORTS_USERS_PATH,
    trendLabel: "Новые аккаунты",
    unit: "пользователи",
    kpis: [
      { key: "total_users", label: "Всего", hint: "Все зарегистрированные пользователи EFHC", tone: "info" },
      { key: "new_in_range", label: "Новые", hint: "Созданы за выбранный период", tone: "success" },
      { key: "active_today", label: "Активны сегодня", hint: "Пользователи, которые были активны сегодня", tone: "success" },
      { key: "with_panel", label: "С панелями", hint: "Пользователи, у которых есть хотя бы одна панель", tone: "info" },
      { key: "with_wallet", label: "С TON-кошельком", hint: "Есть привязанный кошелёк", tone: "neutral" },
    ],
  },
  {
    key: "bank",
    title: "Банк EFHC",
    subtitle: "Баланс банка и движение EFHC за выбранный период.",
    path: ADMIN_REPORTS_BANK_PATH,
    trendLabel: "Операции банка",
    unit: "операции",
    kpis: [
      { key: "bank_main_balance", label: "Баланс банка", hint: "Основной банковский баланс", tone: "info" },
      { key: "credits_in_range", label: "Приход в банк", hint: "Возврат EFHC в банк за выбранный период", tone: "success" },
      { key: "debits_in_range", label: "Расход банка", hint: "Выдача EFHC из банка за выбранный период", tone: "warning" },
      { key: "net_flow_in_range", label: "Чистый поток", hint: "Приход минус расход за период", tone: "neutral" },
      { key: "credit_events_in_range", label: "Операций возврата в банк", hint: "Только банковская сторона Банк EFHC", tone: "success" },
      { key: "debit_events_in_range", label: "Операций выдачи из банка", hint: "Только банковская сторона Банк EFHC", tone: "warning" },
      { key: "total_events_in_range", label: "Всего банковских операций", hint: "Все операции банка за выбранный период", tone: "info" },
    ],
  },
  {
    key: "panels",
    title: "Панели",
    subtitle: "Активность, архив, создание и фактическая продолжительность жизни.",
    path: ADMIN_REPORTS_PANELS_PATH,
    trendLabel: "Созданные панели",
    unit: "панели",
    kpis: [
      { key: "active_panels", label: "Активные", hint: "Панели, которые сейчас работают", tone: "success" },
      { key: "archived_panels", label: "Архив", hint: "Неактивные или архивные", tone: "neutral" },
      { key: "created_in_range", label: "Созданы", hint: "За выбранный период", tone: "info" },
      { key: "avg_lifetime_days", label: "Средняя жизнь", hint: "Среднее количество дней работы панели", tone: "neutral" },
    ],
  },
  {
    key: "withdrawals",
    title: "Выводы EFHCm",
    subtitle: "Очередь, результат обработки и объём подтверждённых выплат.",
    path: ADMIN_REPORTS_WITHDRAWALS_PATH,
    trendLabel: "Созданные заявки на вывод",
    unit: "заявки",
    kpis: [
      { key: "total_count", label: "Всего заявок", hint: "Все заявки на вывод", tone: "info" },
      { key: "pending_count", label: "В очереди", hint: "Все заявки, которые ждут решения", tone: "warning" },
      { key: "paid_count", label: "Выплачены", hint: "Все завершённые выплаты", tone: "success" },
      { key: "rejected_count", label: "Отклонены", hint: "Все отклонённые заявки", tone: "danger" },
      { key: "canceled_count", label: "Отменены", hint: "Все отменённые заявки", tone: "neutral" },
      { key: "total_amount_paid_in_range", label: "Выплачено EFHCm", hint: "Сумма подтверждённых выплат за период", tone: "info" },
    ],
  },
  {
    key: "deposits",
    title: "Пополнения",
    subtitle: "Входящие платежи: ожидание, успешная обработка, ручная проверка и ошибки.",
    path: ADMIN_REPORTS_DEPOSITS_PATH,
    trendLabel: "Созданные пополнения",
    unit: "операции",
    kpis: [
      { key: "pending_операции", label: "Ожидают", hint: "Ожидают завершения", tone: "warning" },
      { key: "auto_credited", label: "Подтверждены", hint: "Успешно подтверждены", tone: "success" },
      { key: "manual_review", label: "Ручная проверка", hint: "Операции, которым нужно решение администратора", tone: "warning" },
      { key: "error_count", label: "Ошибки", hint: "Операции с ошибкой", tone: "danger" },
      { key: "total_credited_in_range", label: "Зачислено EFHC", hint: "Успешно подтверждены за период", tone: "info" },
    ],
  },
] as const;

const RANGE_OPTIONS = [
  { key: "24", label: "24 часа" },
  { key: "168", label: "7 дней" },
  { key: "720", label: "1 месяц" },
  { key: "8760", label: "1 год" },
] as const;

const BUCKET_OPTIONS = [
  { key: "hour", label: "Час" },
  { key: "day", label: "День" },
] as const;

function reportPath(path: string, rangeHours: string, bucket: BucketKey): string {
  const params = new URLSearchParams({
    range_hours: rangeHours,
    bucket,
  });
  return `${path}?${params.toString()}`;
}

function formatMetric(value: string | number | undefined): string {
  if (typeof value === "string") return formatD8ToHuman(value);
  if (value === undefined || value === null || !Number.isFinite(value)) {
    return "—";
  }
  return new Intl.NumberFormat("ru-RU", {
    maximumFractionDigits: 8,
  }).format(value);
}

export function AdminDomainReportsDashboardRuntime() {
  const adminApiRequest = useAdminLinkedTransport();
  const [rangeHours, setRangeHours] = useState("168");
  const [bucket, setBucket] = useState<BucketKey>("day");
  const [reports, setReports] = useState<Partial<Record<DomainKey, AdminDomainReportResponse>>>({});
  const [errors, setErrors] = useState<Partial<Record<DomainKey, string>>>({});
  const [loading, setLoading] = useState(false);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    const results = await Promise.all(
      DOMAIN_CONFIGS.map(async (config): Promise<LoadResult> => {
        try {
          const report = await adminApiRequest<AdminDomainReportResponse>(
            reportPath(config.path, rangeHours, bucket),
            "GET",
          );
          return { key: config.key, report, error: null };
        } catch (error: unknown) {
          return {
            key: config.key,
            report: null,
            error: adminSafeLoadError(error),
          };
        }
      }),
    );

    const nextReports: Partial<Record<DomainKey, AdminDomainReportResponse>> = {};
    const nextErrors: Partial<Record<DomainKey, string>> = {};
    results.forEach((result) => {
      if (result.report) nextReports[result.key] = result.report;
      if (result.error) nextErrors[result.key] = result.error;
    });
    setReports(nextReports);
    setErrors(nextErrors);
    setUpdatedAt(new Date().toISOString());
    setLoading(false);
  }, [adminApiRequest, bucket, rangeHours]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const loadedCount = useMemo(
    () => DOMAIN_CONFIGS.filter((config) => reports[config.key]).length,
    [reports],
  );
  const errorCount = Object.keys(errors).length;

  return (
    <section
      className="efhc-admin-domain-reports efhc-dashboard-surface"
      data-admin-domain-reports="1719"
      data-admin-domain-reports-truth="Реальные данные по времени"
      data-admin-domain-reports-synthetic={"false"}
      data-admin-domain-reports-owner="global_id"
    >
      <AdminDashboardToolbar
        title="Доменные отчёты"
        subtitle="Пять основных отчётов: пользователи, банк, панели, выводы и входящие платежи."
        breadcrumb="Админ-панель / Отчёты"
        refresh={(
          <AdminRefreshPicker
            label="Обновить отчёты"
            onRefresh={() => void refresh()}
            refreshLabel={loading ? "Обновление" : "Обновить все"}
            disabled={loading}
          />
        )}
        freshness={(
          <AdminFreshnessBadge
            freshness={errorCount ? "stale" : loadedCount === DOMAIN_CONFIGS.length ? "fresh" : "unknown"}
            label={`${loadedCount}/${DOMAIN_CONFIGS.length} загружено`}
            updatedAt={updatedAt ?? undefined}
          />
        )}
        updatedAt={updatedAt ?? "ожидается первая загрузка"}
      />

      <AdminFilterBar
        groups={[
          {
            key: "admin-domain-reports-range",
            label: "Период",
            value: rangeHours,
            options: [...RANGE_OPTIONS],
            onChange: setRangeHours,
            querySync: "disabled",
          },
          {
            key: "admin-domain-reports-bucket",
            label: "Шаг",
            value: bucket,
            options: [...BUCKET_OPTIONS],
            onChange: (value) => setBucket(value as BucketKey),
            querySync: "disabled",
          },
        ]}
      />

      {DOMAIN_CONFIGS.map((config) => {
        const report = reports[config.key];
        const error = errors[config.key];
        const points = (report?.trend ?? []).map((point) => ({
          id: point.bucket,
          label: point.bucket,
          value: point.value,
        }));
        const status = error
          ? "error"
          : loading && !report
            ? "loading"
            : report
              ? "success"
              : "empty";

        return (
          <AdminPanelChrome
            key={config.key}
            title={config.title}
            subtitle={config.subtitle}
            source={config.path}
            status={status}
            tone={error ? "danger" : "neutral"}
            updatedAt={report?.generated_at ?? updatedAt ?? undefined}
            footer={`${rangeHours} ч · ${bucket}`}
          >
            {error ? (
              <AdminErrorState
                title={`Не удалось загрузить: ${config.title}`}
                text={error}
              />
            ) : (
              <>
                <AdminDashboardGrid>
                  {config.kpis.map((kpi) => (
                    <AdminKpiCard
                      key={kpi.key}
                      label={kpi.label}
                      value={formatMetric(report?.snapshot?.[kpi.key])}
                      hint={kpi.hint}
                      tone={kpi.tone}
                    />
                  ))}
                </AdminDashboardGrid>

                <AdminAreaChart
                  ariaLabel={`${config.title}: ${config.trendLabel}`}
                  dataKind="real_timeseries"
                  emptyLabel={report?.empty_reason ?? "Нет данных в выбранном периоде"}
                  label={config.trendLabel}
                  points={points}
                  source={config.path}
                  synthetic={false}
                  tone="info"
                  unit={config.unit}
                />

                <div className="mt-3 flex flex-wrap gap-2">
                  <AdminStatusBadge label="Данные обновлены" tone="success" />
                  
                  <AdminStatusBadge label="Только просмотр" tone="info" />
                  {config.key === "users" ? (
                    <AdminStatusBadge label="Пользователи определяются по ID EFHC" tone="success" />
                  ) : null}
                  {config.key === "bank" ? (
                    <>
                      <AdminStatusBadge label="Системный банк EFHC" tone="success" />
                      {report?.policy ? (
                        <>
                          <AdminStatusBadge label="Основной баланс банка" tone="info" />
                          <AdminStatusBadge label={`Начальный запас: ${report.policy.initial_balance} EFHC`} tone="info" />
                          <AdminStatusBadge label={`Отрицательный баланс: ${report.policy.negative_balance_allowed ? "разрешён" : "запрещён"}`} tone="warning" />
                          <AdminStatusBadge label={`Переводы между пользователями: ${report.policy.p2p_allowed ? "разрешены" : "запрещены"}`} tone="success" />
                          <AdminStatusBadge label={`Владелец пользовательского баланса: ID EFHC`} tone="success" />
                          <AdminStatusBadge label="Банк не является пользователем EFHC" tone="success" />
                          
                        </>
                      ) : null}
                    </>
                  ) : null}
                </div>
              </>
            )}
          </AdminPanelChrome>
        );
      })}
    </section>
  );
}
