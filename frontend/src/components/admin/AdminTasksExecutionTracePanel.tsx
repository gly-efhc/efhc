import React, { useMemo } from "react";
import {
  AdminActionTable,
  AdminChartCard,
  AdminConfirmationBlock,
  AdminEmptyState,
  AdminErrorState,
  AdminFlowMapCard,
  AdminKpiCard,
  AdminSectionHeader,
  AdminStatusBadge,
} from "./AdminDashboardUiKit";
import { AdminCompactOperationList } from "./AdminCompactOperationList";
import type { DbId } from "../../types/db-id";

type TraceLike = {
  id: DbId;
  global_id: string | null;
  system_entity: string | null;
  amount: string;
  direction: string;
  balance_type: string;
  reason: string;
  idempotency_key: string;
  created_at: string;
};

type Props = {
  traces: TraceLike[];
  loading: boolean;
  error: string | null;
  cursor: string | null;
  selectedTaskTitle: string | null;
  onRefresh: () => void;
  onLoadMore: () => void;
};

function shortKey(value: string): string {
  const raw = String(value || "").trim();
  if (!raw) return "no-key";
  if (raw.length <= 14) return raw;
  return `${raw.slice(0, 8)}…${raw.slice(-4)}`;
}

function taskReason(value: string): string {
  const raw = String(value || "").trim();
  if (!raw) return "task trace";
  if (raw.startsWith("task_bonus:")) {
    return raw.replace("task_bonus:", "task:");
  }
  return raw;
}

export function AdminTasksExecutionTracePanel(props: Props) {
  const creditCount = props.traces.filter(
    (item) => item.direction === "credit",
  ).length;
  const bonusCount = props.traces.filter(
    (item) => item.balance_type === "bonus",
  ).length;
  const latestTrace = props.traces[0] || null;
  const visible = useMemo(() => props.traces.slice(0, 8), [props.traces]);

  return (
    <section
      className="efhc-admin-tasks-trace"
      data-admin-tasks-execution-trace-boundary="1342"
    >
      <AdminSectionHeader
        eyebrow="Начисления за задания"
        title="История начислений за задания"
        subtitle={
          "Здесь показаны последние начисления EFHCb за подтверждённые задания."
        }
        actions={
          <button type="button" onClick={props.onRefresh}>
            Обновить историю
          </button>
        }
      />

      <div className="efhc-admin-tasks-trace_kpis">
        <AdminKpiCard
          label="Записи"
          value={props.traces.length}
          meta="Начисления за задания"
          hint="История начислений EFHCb."
          tone="primary"
        />
        <AdminKpiCard
          label="Начислено"
          value={creditCount}
          meta="EFHCb"
          hint="Начисления после подтверждения выполнения."
          tone="success"
        />
        <AdminKpiCard
          label="Бонусный баланс"
          value={bonusCount}
          meta="EFHCb"
          hint="Основной баланс EFHCm не изменяется."
          tone="warning"
        />
        <AdminKpiCard
          label="Задание"
          value={props.selectedTaskTitle || "общий"}
          meta="Текущий выбор"
          hint="Показаны начисления по выбранному заданию."
          tone="neutral"
        />
      </div>

      <AdminFlowMapCard
        title="Порядок начисления бонуса"
        nodes={[
          {
            label: "1. Выполнение",
            value: "подтверждение",
            hint: "результат пользователя",
            active: true,
          },
          {
            label: "2. Проверка",
            value: "одобрить / отклонить",
            hint: "решение администратора",
            active: true,
          },
          {
            label: "3. Начисление",
            value: "EFHCb",
            hint: "бонусный баланс",
            active: creditCount > 0,
          },
          {
            label: "4. История",
            value: "записано",
            hint: "только основные сведения события",
            active: props.traces.length > 0,
          },
        ]}
      />

      <AdminChartCard
        title="Начисления EFHCb"
        subtitle="История начислений за выполненные задания."
        meta={<AdminStatusBadge label="Администратор" tone="warning" />}
      >
        {props.error ? (
          <AdminErrorState title="История недоступна" text={props.error} />
        ) : visible.length ? (
          <AdminCompactOperationList
            rows={visible.map((item) => ({
              id: item.id,
              operation: `${item.direction === "credit" ? "Начисление" : "Списание"} · ${taskReason(item.reason)}`,
              amount: `${item.amount} EFHC`,
              subject: `Global ID ${item.global_id || item.system_entity || "—"}`,
              time: item.created_at,
            }))}
          />
        ) : (
          <AdminEmptyState
            title="История пуста"
            text="Начислений за задания пока нет или они ещё не загружены."
          />
        )}
      </AdminChartCard>

      <AdminActionTable
        title="Сводка истории"
        rows={[
          {
            label: "Операции",
            value: "Начисления за задания",
            hint: "Подтверждённые начисления EFHCb",
          },
          {
            label: "Последняя операция",
            value: latestTrace ? `#${latestTrace.id}` : "нет",
            hint: latestTrace ? latestTrace.created_at : "нет событий",
          },
          {
            label: "Продолжение истории",
            value: props.cursor ? "Доступно" : "Нет",
            hint: "доступна последовательная загрузка истории",
          },
        ]}
      />

      <div className="efhc-admin-tasks-trace_actions">
        <button type="button" onClick={props.onRefresh}>
          Обновить историю
        </button>
        <button
          type="button"
          onClick={props.onLoadMore}
          disabled={!props.cursor || props.loading}
        >
          Загрузить ещё
        </button>
      </div>

      <AdminConfirmationBlock
        title="Доступ"
        text={
          "История начислений доступна администраторам. Пользователь видит собственный результат задания и изменение своего баланса."
        }
        confirmed
      />
    </section>
  );
}
