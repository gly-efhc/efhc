import React, { useMemo, useState } from "react";
import { AdminCompactOperationList } from "./AdminCompactOperationList";

import { formatD8ToHuman, sumScaledDown } from "../../lib/format";
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


type AdminWithdrawalDashboardStatus =
  | "PENDING"
  | "PAID"
  | "REJECTED"
  | "CANCELED"
  | string;

export type AdminWithdrawalsDashboardItem = {
  id: DbId;
  global_id: string;
  amount_efhc: string;
  status: AdminWithdrawalDashboardStatus;
  external_address: string | null;
  tx_hash: string | null;
  created_at: string;
  processed_at: string | null;
  error_message: string | null;
  is_vip: boolean;
  payout_asset?: string | null;
  tonconnect_transport_kind?: string | null;
};

export type AdminWithdrawalsDashboardRuntimeProps = {
  items: AdminWithdrawalsDashboardItem[];
  statusSnapshot?: Record<string, string | number> | null;
  currentItems: AdminWithdrawalsDashboardItem[];
  selected?: AdminWithdrawalsDashboardItem | null;
  activeStatus: string;
  vipOnly: boolean;
  loading?: boolean;
  error?: string | null;
  updatedAt?: string;
  onRefresh: () => void;
};

type WithdrawalScope = "queue" | "final" | "attention" | "vip";

type WithdrawalPoint = {
  id: string;
  label: string;
  value: number;
  tone?: "success" | "warning" | "info" | "neutral" | "danger";
};

const DAY_MS = 24 * 60 * 60 * 1000;
const HOUR_MS = 60 * 60 * 1000;

function countStatus(
  items: AdminWithdrawalsDashboardItem[],
  status: string,
): number {
  return items.filter((item) => item.status === status).length;
}

function humanInt(value: number): string {
  return value.toLocaleString("ru-RU");
}

function sumAmount(items: AdminWithdrawalsDashboardItem[]): string {
  return items.reduce(
    (acc, item) => sumScaledDown(acc, String(item.amount_efhc || "0"), 8),
    "0",
  );
}

function parseTime(value: string | null | undefined): number | null {
  if (!value) return null;
  const ts = Date.parse(value);
  return Number.isFinite(ts) ? ts : null;
}

function ageHours(item: AdminWithdrawalsDashboardItem): number | null {
  const created = parseTime(item.created_at);
  if (created === null) return null;
  return Math.max(0, (Date.now() - created) / HOUR_MS);
}

function humanAge(item: AdminWithdrawalsDashboardItem): string {
  const hours = ageHours(item);
  if (hours === null) return "возраст неизвестен";
  if (hours < 1) return "меньше 1 часа";
  if (hours < 24) return `${Math.floor(hours)} ч`;
  return `${Math.floor(hours / 24)} д`;
}

function averageHandlingHours(
  items: AdminWithdrawalsDashboardItem[],
): number | null {
  const durations = items
    .map((item) => {
      const created = parseTime(item.created_at);
      const processed = parseTime(item.processed_at);
      if (created === null || processed === null) return null;
      if (processed < created) return null;
      return (processed - created) / HOUR_MS;
    })
    .filter((value): value is number => value !== null);
  if (!durations.length) return null;
  const total = durations.reduce((acc, value) => acc + value, 0);
  return total / durations.length;
}

function humanHandling(hours: number | null): string {
  if (hours === null) return "нет данных о времени";
  if (hours < 1) return "< 1 ч";
  if (hours < 24) return `${Math.round(hours)} ч`;
  return `${Math.round(hours / 24)} д`;
}

function pct(part: number, total: number): number {
  if (!total) return 0;
  return Math.round((part / total) * 100);
}

function shortAddress(value: string | null): string {
  if (!value) return "адрес не задан";
  if (value.length <= 18) return value;
  return `${value.slice(0, 8)}…${value.slice(-8)}`;
}

function statusLabel(status: string): string {
  if (status === "PENDING") return "Ожидает";
  if (status === "PAID") return "Выплачено";
  if (status === "REJECTED") return "Отклонено";
  if (status === "CANCELED") return "Отменено";
  return status;
}

function statusTone(status: string) {
  if (status === "PAID") return "success" as const;
  if (status === "PENDING") return "warning" as const;
  if (status === "REJECTED" || status === "CANCELED") {
    return "neutral" as const;
  }
  return "danger" as const;
}

function scopeLabel(scope: WithdrawalScope): string {
  if (scope === "final") return "Финальные";
  if (scope === "attention") return "Внимание";
  if (scope === "vip") return "VIP";
  return "Очередь";
}

function buildStatusPoints(
  pending: number,
  paid: number,
  rejected: number,
  canceled: number,
  attention: number,
): WithdrawalPoint[] {
  return [
    { id: "pending", label: "Ожидает решения", value: pending, tone: "warning" },
    { id: "paid", label: "Выплачено", value: paid, tone: "success" },
    { id: "rejected", label: "Отклонено и возвращено", value: rejected, tone: "neutral" },
    { id: "canceled", label: "Отменено", value: canceled, tone: "neutral" },
    { id: "attention", label: "Нужно внимание", value: attention, tone: "danger" },
  ];
}

function freshnessLabel(props: AdminWithdrawalsDashboardRuntimeProps): string {
  if (props.error) return "ошибка очереди выводов";
  if (props.loading) return "обновление";
  if (!props.items.length) return "Список заявок пуст";
  return "Список заявок загружен";
}

export function AdminWithdrawalsDashboardRuntime(
  props: AdminWithdrawalsDashboardRuntimeProps,
) {
  const [scope, setScope] = useState<WithdrawalScope>("queue");
  const pending = Number(props.statusSnapshot?.pending_count
    ?? countStatus(props.items, "PENDING"));
  const paid = Number(props.statusSnapshot?.paid_count
    ?? countStatus(props.items, "PAID"));
  const rejected = Number(props.statusSnapshot?.rejected_count
    ?? countStatus(props.items, "REJECTED"));
  const canceled = Number(props.statusSnapshot?.canceled_count
    ?? countStatus(props.items, "CANCELED"));
  const queueTotal = Number(props.statusSnapshot?.total_count ?? props.items.length);
  const finalTotal = paid + rejected + canceled;
  const attention = props.items.filter(
    (item) => Boolean(item.error_message) || item.status === "ERROR",
  ).length;
  const vip = props.items.filter((item) => item.is_vip).length;
  const pendingAmount = formatD8ToHuman(
    sumAmount(props.items.filter((item) => item.status === "PENDING")),
  );
  const finalPercent = pct(finalTotal, queueTotal);
  const attentionPercent = pct(attention, queueTotal);
  const handling = averageHandlingHours(
    props.items.filter((item) => item.status !== "PENDING"),
  );
  const pendingUnder24 = props.items.filter((item) => {
    if (item.status !== "PENDING") return false;
    const created = parseTime(item.created_at);
    return created !== null && Date.now() - created < DAY_MS;
  }).length;
  const pending24to72 = props.items.filter((item) => {
    if (item.status !== "PENDING") return false;
    const created = parseTime(item.created_at);
    if (created === null) return false;
    const age = Date.now() - created;
    return age >= DAY_MS && age < DAY_MS * 3;
  }).length;
  const pendingOver72 = props.items.filter((item) => {
    if (item.status !== "PENDING") return false;
    const created = parseTime(item.created_at);
    return created !== null && Date.now() - created >= DAY_MS * 3;
  }).length;
  const selectedLabel = props.selected ? `#${props.selected.id}` : "нет";
  const statusPoints = useMemo(
    () => buildStatusPoints(pending, paid, rejected, canceled, attention),
    [pending, paid, rejected, canceled, attention],
  );
  const recentQueue = props.currentItems.slice(0, 8);
  const scopedItems = props.items.filter((item) => {
    if (scope === "final") return item.status !== "PENDING";
    if (scope === "attention") {
      return Boolean(item.error_message) || item.status === "ERROR";
    }
    if (scope === "vip") return item.is_vip;
    return item.status === "PENDING";
  });
  const freshness = props.error
    ? "stale"
    : props.loading
      ? "unknown"
      : props.items.length
        ? "fresh"
        : "stale";

  return (
    <section
      className="efhc-admin-withdrawals-dashboard-runtime"
      data-admin-withdrawals-dashboard-runtime="1486"
      data-admin-withdrawals-truth="raw-derived"
      data-admin-withdrawals-no-synthetic="true"
      data-admin-withdrawals-no-write-actions="true"
      data-admin-withdrawals-no-raw-payload="true"
      data-admin-withdrawals-no-debug-json="true"
      data-admin-withdrawals-no-secrets="true"
      data-admin-withdrawals-final-status-safe="true"
      data-admin-withdrawals-money-path="read-only"
    >
      <AdminDashboardToolbar
        title="Заявки на вывод"
        subtitle="Общий обзор заявок: что ждёт решения, что завершено и где требуется внимание."
        breadcrumb="Админ · Заявки на вывод"
        refresh={
          <AdminRefreshPicker
            disabled={props.loading}
            label="Обновление"
            onRefresh={props.onRefresh}
            refreshLabel="Обновить данные"
            value="manual"
          />
        }
        updatedAt={props.updatedAt || "—"}
        freshness={
          <AdminFreshnessBadge
            freshness={freshness}
            label={freshnessLabel(props)}
            updatedAt={props.updatedAt || "—"}
          />
        }
        filters={
          <AdminFilterBar
            groups={[
              {
                key: "withdrawal-scope",
                label: "Срез",
                value: scope,
                queryKey: "withdrawal_scope",
                querySync: "safe_display_only",
                onChange: (value) => setScope(value as WithdrawalScope),
                options: [
                  { key: "queue", label: "Очередь" },
                  { key: "final", label: "Финальные" },
                  { key: "attention", label: "Внимание" },
                  { key: "vip", label: "VIP" },
                ],
              },
            ]}
            onReset={() => setScope("queue")}
            resetLabel="Сбросить"
          />
        }
      />

      <AdminDashboardGrid>
        <AdminKpiCard
          label="Ожидают решения"
          value={humanInt(pending)}
          meta={`${pendingAmount} EFHC`}
          hint="Количество всех заявок, которые ещё ждут обработки. Сумма показана по текущему списку."
          tone={pending ? "warning" : "neutral"}
        />
        <AdminKpiCard
          label="Завершено"
          value={humanInt(finalTotal)}
          meta={`${paid} выплачено · ${rejected} отклонено · ${canceled} отменено`}
          hint="Завершённые заявки остаются в истории и не меняются обзором."
          tone={finalTotal ? "success" : "neutral"}
        />
        <AdminKpiCard
          label="Нужно внимание"
          value={humanInt(attention)}
          meta={`${attentionPercent}% заявок`}
          hint="Заявки с ошибкой или состоянием, требующим проверки администратора."
          tone={attention ? "danger" : "neutral"}
        />
        <AdminKpiCard
          label="Среднее время обработки"
          value={humanHandling(handling)}
          meta={handling === null ? "нет данных" : "от создания до решения"}
          hint="Рассчитывается только по заявкам с известным временем создания и завершения."
          tone={handling === null ? "neutral" : "info"}
        />
      </AdminDashboardGrid>

      <div className="efhc-admin-withdrawals-dashboard-grid">
        <AdminPanelChrome
          title="Состояние всех заявок"
          subtitle="Счётчики охватывают всю базу заявок, а не только открытый список."
          status={props.items.length ? "success" : "stale"}
          tone={attention ? "warning" : "success"}
          source="Общая история заявок"
          updatedAt={props.updatedAt || "—"}
        >
          <AdminMiniBarChart
            ariaLabel="Распределение заявок на вывод по состояниям"
            dataKind="derived"
            points={statusPoints}
          />
          <div className="efhc-admin-withdrawals-dashboard-status-grid">
            {statusPoints.map((point) => (
              <div
                className="efhc-admin-withdrawals-dashboard-status"
                data-withdrawal-pipeline-status={point.id}
                key={point.id}
              >
                <span>{point.label}</span>
                <strong>{humanInt(point.value)}</strong>
              </div>
            ))}
          </div>
        </AdminPanelChrome>

        <AdminPanelChrome
          title="Сколько времени ждут"
          subtitle="Показывает, как долго текущие заявки ждут решения."
          status={pending ? "success" : "empty"}
          tone={pendingOver72 ? "danger" : pending24to72 ? "warning" : "info"}
          source="Время создания заявок"
          updatedAt={props.updatedAt || "—"}
        >
          <AdminHeatStrip
            ariaLabel="Сколько времени заявки ждут решения"
            dataKind="derived"
            points={[
              {
                id: "under-24h",
                label: "< 24h",
                value: pendingUnder24,
                tone: "success",
              },
              {
                id: "24-72h",
                label: "24–72h",
                value: pending24to72,
                tone: "warning",
              },
              {
                id: "over-72h",
                label: "> 72h",
                value: pendingOver72,
                tone: "danger",
              },
            ]}
          />
          <AdminProgressBar
            ariaLabel="Доля завершённых заявок"
            dataKind="derived"
            label="Доля завершённых заявок"
            max={100}
            showValue
            source="Сводка завершённых заявок"
            tone={finalPercent >= 70 ? "success" : "info"}
            value={finalPercent}
          />
        </AdminPanelChrome>
      </div>

      <div className="efhc-admin-withdrawals-dashboard-grid">
        <AdminPanelChrome
          title="Порядок обработки"
          subtitle="Сначала проверка заявки, затем решение и только потом подтверждение выплаты."
          status="success"
          tone="info"
          source="Порядок обработки заявок"
          updatedAt={props.updatedAt || "—"}
        >
          <AdminFlowMapCard
            title="Безопасный порядок выплаты"
            nodes={[
              {
                label: "1. Очередь",
                value: `${pending} ждут решения`,
                hint: props.vipOnly ? "показаны только VIP" : "показаны все заявки",
                active: pending > 0,
              },
              {
                label: "2. Проверка",
                value: selectedLabel,
                hint: "проверка заявки и результата для пользователя",
                active: Boolean(props.selected),
              },
              {
                label: "3. Решение",
                value: "подтвердить или отклонить",
                hint: "действия доступны после проверки заявки",
                active: Boolean(props.selected),
              },
              {
                label: "4. Финал",
                value: `${finalTotal} завершено`,
                hint: "выплачено, отклонено или отменено",
                active: finalTotal > 0,
              },
            ]}
          />
          <p className="efhc-admin-withdrawals-dashboard-boundary">
            Этот обзор не меняет деньги сам по себе. Выплата, одобрение,
            отклонение и восстановление состояния выполняются только отдельными
            подтверждаемыми действиями по выбранной заявке.
          </p>
        </AdminPanelChrome>

        <AdminPanelChrome
          title={`Выбранный срез: ${scopeLabel(scope)}`}
          subtitle="Фильтр влияет только на отображение и не меняет данные заявки."
          status={scopedItems.length ? "success" : "empty"}
          tone={
            scope === "attention" && scopedItems.length ? "danger" : "neutral"
          }
          source="Текущий выбранный список"
          updatedAt={props.updatedAt || "—"}
        >
          <AdminActionTable
            title="Сводка выбранной группы"
            rows={[
              {
                label: "Заявок",
                value: humanInt(scopedItems.length),
                hint: "только отображение",
              },
              {
                label: "Сумма",
                value: `${formatD8ToHuman(sumAmount(scopedItems))} EFHC`,
                hint: "сумма выбранных заявок",
              },
              {
                label: "VIP",
                value: humanInt(vip),
                hint: "VIP-заявки",
              },
              {
                label: "Текущий фильтр страницы",
                value: props.activeStatus || "—",
                hint: props.vipOnly ? "только VIP" : "все пользователи",
              },
            ]}
          />
        </AdminPanelChrome>
      </div>

      <AdminPanelChrome
        title="Последние заявки"
        subtitle="Короткий список последних заявок без лишних служебных данных."
        status={recentQueue.length ? "success" : "empty"}
        tone="neutral"
        source="Текущий список заявок"
        updatedAt={props.updatedAt || "—"}
      >
        {props.error ? (
          <div className="efhc-admin-withdrawals-dashboard-empty">
            Ошибка чтения очереди: {props.error}
          </div>
        ) : recentQueue.length ? (
          <AdminCompactOperationList
            rows={recentQueue.map((item) => ({
              id: item.id,
              operation: `#${item.id} · ${statusLabel(item.status)}`,
              amount: `${formatD8ToHuman(item.amount_efhc)} EFHC`,
              subject: `Global ID ${item.global_id}`,
              time: humanAge(item),
            }))}
          />
        ) : (
          <div className="efhc-admin-withdrawals-dashboard-empty">
            В выбранном фильтре нет заявок.
          </div>
        )}
      </AdminPanelChrome>
    </section>
  );
}
