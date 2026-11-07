import React, { useMemo, useState } from "react";

import {
  AdminDashboardGrid,
  AdminDashboardToolbar,
  AdminFilterBar,
  AdminFreshnessBadge,
  AdminKpiCard,
  AdminMiniBarChart,
  AdminPanelChrome,
  AdminProgressBar,
  AdminRefreshPicker,
  AdminStatusBadge,
} from "./AdminDashboardUiKit";


export type AdminDepositsRuntimeSummary = {
  ok?: boolean;
  release_mode?: string;
  automation_mode?: string;
  release_gate_note?: string;
  primary_path?: string;
  fallback_path?: string;
  pending_manual_count?: number;
  error_retry_count?: number;
  error_user_count?: number;
  auto_credited_count?: number;
  pending_intents_count?: number;
  total_count?: number;
  status_counters?: Record<string, number>;
  error_total?: number;
  retry_waiting_count?: number;
  unmatched_count?: number;
  last_reconcile_success_at?: string | null;
  last_watcher_at?: string | null;
  last_watcher_status?: string | null;
};

type DepositScope = "overview" | "attention" | "waiting" | "credited";

type DepositPoint = {
  id: string;
  label: string;
  value: number;
  tone?: "success" | "warning" | "info" | "neutral" | "danger";
};

export type AdminDepositsDashboardRuntimeProps = {
  summary: AdminDepositsRuntimeSummary | null;
  loading?: boolean;
  error?: string | null;
  formReadyFields: number;
  rawTxState: string;
  resultFieldCount: number;
  finalResultLabel: string;
  finalResultTone: "success" | "warning" | "neutral";
  updatedAt?: string;
  onRefresh: () => void;
};

function count(value: number | undefined): number {
  return Number.isFinite(value) ? Number(value) : 0;
}

function human(value: number): string {
  return value.toLocaleString("ru-RU");
}

function pct(part: number, total: number): number {
  if (!total) return 0;
  return Math.round((part / total) * 100);
}

function scopeLabel(scope: DepositScope): string {
  if (scope === "attention") return "Нужна помощь";
  if (scope === "waiting") return "Ожидают завершения";
  if (scope === "credited") return "Успешно завершено";
  return "Общий обзор";
}

function buildDepositPoints(
  summary: AdminDepositsRuntimeSummary | null,
): DepositPoint[] {
  return [
    {
      id: "credited",
      label: "Зачислено автоматически",
      value: count(summary?.auto_credited_count),
      tone: "success",
    },
    {
      id: "manual",
      label: "Нужно решение администратора",
      value: count(summary?.pending_manual_count),
      tone: "warning",
    },
    {
      id: "retry",
      label: "Готовы к повторной попытке",
      value: count(summary?.retry_waiting_count),
      tone: "info",
    },
    {
      id: "unmatched",
      label: "Не удалось определить",
      value: count(summary?.unmatched_count),
      tone: "danger",
    },
    {
      id: "waiting",
      label: "Ожидают оплаты",
      value: count(summary?.pending_intents_count),
      tone: "neutral",
    },
  ];
}

function freshnessLabel(props: AdminDepositsDashboardRuntimeProps): string {
  if (props.error) return "Не удалось обновить данные";
  if (props.loading) return "Обновляем данные";
  if (!props.summary) return "Данные ещё не загружены";
  return "Данные актуальны";
}

export function AdminDepositsDashboardRuntime(
  props: AdminDepositsDashboardRuntimeProps,
) {
  const [scope, setScope] = useState<DepositScope>("overview");
  const points = useMemo(() => buildDepositPoints(props.summary), [props.summary]);
  const total = count(props.summary?.total_count);
  const autoCredited = count(props.summary?.auto_credited_count);
  const manual = count(props.summary?.pending_manual_count);
  const errors = count(props.summary?.error_total);
  const retry = count(props.summary?.retry_waiting_count);
  const unmatched = count(props.summary?.unmatched_count);
  const waiting = count(props.summary?.pending_intents_count);
  const attention = manual + errors + unmatched;
  const automationPercent = pct(autoCredited, Math.max(total, autoCredited + attention));
  const freshness = props.error
    ? "stale"
    : props.loading
      ? "unknown"
      : props.summary
        ? "fresh"
        : "stale";

  return (
    <section
      className="efhc-admin-deposits-dashboard-runtime"
      data-admin-deposits-dashboard-runtime="human-v2"
      data-admin-deposits-no-synthetic="true"
    >
      <AdminDashboardToolbar
        title="Состояние входящих платежей"
        subtitle="Главное видно сразу: сколько операций прошло автоматически и где действительно нужна помощь."
        breadcrumb="Админ / Платежи"
        refresh={(
          <AdminRefreshPicker
            label="Обновление"
            onRefresh={props.onRefresh}
            refreshLabel="Обновить"
            value="manual"
          />
        )}
        updatedAt={props.updatedAt ? `Последняя работа системы: ${props.updatedAt}` : "Время последней работы пока неизвестно"}
        freshness={(
          <AdminFreshnessBadge
            freshness={freshness}
            label={freshnessLabel(props)}
            updatedAt={props.updatedAt || "—"}
          />
        )}
        filters={(
          <AdminFilterBar
            groups={[
              {
                key: "deposit-scope",
                label: "Показать",
                value: scope,
                queryKey: "deposit_scope",
                querySync: "safe_display_only",
                onChange: (value) => setScope(value as DepositScope),
                options: [
                  { key: "overview", label: "Общий обзор" },
                  { key: "attention", label: "Нужна помощь" },
                  { key: "waiting", label: "Ожидают завершения" },
                  { key: "credited", label: "Успешно завершено" },
                ],
              },
            ]}
            onReset={() => setScope("overview")}
            resetLabel="Сбросить"
          />
        )}
      />

      <AdminDashboardGrid>
        <AdminKpiCard
          label="Всего входящих операций"
          value={human(total)}
          hint="Все операции, которые система видит в журнале входящих платежей."
          tone="neutral"
        />
        <AdminKpiCard
          label="Зачислено автоматически"
          value={human(autoCredited)}
          hint="Операции, которые завершились без вмешательства администратора."
          tone="success"
        />
        <AdminKpiCard
          label="Нужно внимание"
          value={human(attention)}
          hint="Ручные решения, ошибки и операции, которые система не смогла определить."
          tone={attention ? "warning" : "success"}
        />
        <AdminKpiCard
          label="Ожидают оплаты"
          value={human(waiting)}
          hint="Созданные депозиты, по которым платёж ещё не завершён."
          tone={waiting ? "warning" : "neutral"}
        />
      </AdminDashboardGrid>

      <div className="efhc-admin-deposits-dashboard-grid">
        <AdminPanelChrome
          title="Что происходит с платежами"
          subtitle={`Выбранный раздел: ${scopeLabel(scope)}.`}
          status={props.summary ? "success" : "stale"}
          tone={attention ? "warning" : "success"}
          updatedAt={props.updatedAt || "—"}
        >
          <AdminMiniBarChart
            ariaLabel="Состояние входящих платежей"
            dataKind="derived"
            points={points}
          />
          <div className="efhc-admin-deposits-dashboard-status-grid">
            {points.map((point) => (
              <div
                className="efhc-admin-deposits-dashboard-status"
                data-deposit-pipeline-status={point.id}
                key={point.id}
              >
                <span>{point.label}</span>
                <strong>{human(point.value)}</strong>
              </div>
            ))}
          </div>
        </AdminPanelChrome>

        <AdminPanelChrome
          title="Насколько система справляется сама"
          subtitle="Чем выше показатель автоматической обработки, тем меньше ручной работы требуется."
          status={props.error ? "error" : props.summary ? "success" : "stale"}
          tone={attention ? "warning" : "success"}
          updatedAt={props.updatedAt || "—"}
        >
          <AdminProgressBar
            ariaLabel="Доля автоматической обработки"
            dataKind="derived"
            label="Автоматически завершено"
            value={automationPercent}
          />
          <div className="mt-3 flex flex-wrap gap-2">
            <AdminStatusBadge
              label={retry ? `Можно повторить: ${human(retry)}` : "Повторных попыток не требуется"}
              tone={retry ? "info" : "success"}
            />
            <AdminStatusBadge
              label={unmatched ? `Не определено: ${human(unmatched)}` : "Все операции определены"}
              tone={unmatched ? "warning" : "success"}
            />
            <AdminStatusBadge
              label={props.finalResultLabel}
              tone={props.finalResultTone}
            />
          </div>
          <p className="mt-3 text-xs text-[color:var(--tg-hint)]">
            Сначала найдите проблемную операцию в списке ниже. Повторная обработка безопаснее ручного ввода и должна использоваться первой.
          </p>
        </AdminPanelChrome>
      </div>
    </section>
  );
}
