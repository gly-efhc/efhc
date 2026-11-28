import React, { useMemo, useState } from "react";
import type { GlobalId } from "../../types/identity";

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


export type AdminTaskDashboardItem = {
  id: DbId;
  title: string;
  description: string | null;
  is_active: boolean;
  bonus_efhc?: string | null;
  kind: string;
  created_at: string;
  updated_at: string;
};

export type AdminSubmissionDashboardItem = {
  id: DbId;
  task_id: DbId;
  global_id: GlobalId;
  status: string;
  proof_text: string | null;
  proof_url: string | null;
  submitted_at: string;
  reviewed_at: string | null;
  bonus_efhc?: string | null;
  moderator_global_id: GlobalId | null;
  moderator_note: string | null;
};

export type AdminTaskTraceDashboardItem = {
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

export type AdminReferralDashboardItem = {
  inviter_global_id: string;
  active_count: number;
  inactive_count: number;
  total_bonus_efhc: string;
  last_invited_at: string | null;
};

export type AdminTasksDashboardRuntimeProps = {
  tasks: AdminTaskDashboardItem[];
  submissions: AdminSubmissionDashboardItem[];
  traces: AdminTaskTraceDashboardItem[];
  selectedTaskId: DbId | null;
  selectedTaskTitle?: string | null;
  selectedStatus: string;
  loadingTasks?: boolean;
  loadingSubmissions?: boolean;
  loadingTrace?: boolean;
  tasksError?: string | null;
  submissionsError?: string | null;
  traceError?: string | null;
  updatedAt?: string;
  onRefreshTasks: () => void;
  onRefreshSubmissions: () => void;
  onRefreshTrace: () => void;
};

export type AdminReferralsDashboardRuntimeProps = {
  items: AdminReferralDashboardItem[];
  selectedInviter?: string | null;
  loading?: boolean;
  error?: string | null;
  updatedAt?: string;
  hasNextPage?: boolean;
  onRefresh: () => void;
};

type TaskScope = "all" | "active" | "inactive" | "moderation" | "attention";
type ReferralScope = "all" | "active" | "inactive" | "bonus" | "recent";

type DashboardPoint = {
  id: string;
  label: string;
  value: number;
  tone?: "success" | "warning" | "info" | "neutral" | "danger";
};

const DAY_MS = 24 * 60 * 60 * 1000;

function humanInt(value: number): string {
  return value.toLocaleString("ru-RU");
}

function pct(part: number, total: number): number {
  if (!total) return 0;
  return Math.round((part / total) * 100);
}

function parseTime(value: string | null | undefined): number | null {
  if (!value) return null;
  const ts = Date.parse(value);
  return Number.isFinite(ts) ? ts : null;
}

function ageDays(value: string | null | undefined): number | null {
  const ts = parseTime(value);
  if (ts === null) return null;
  return Math.max(0, Math.floor((Date.now() - ts) / DAY_MS));
}

function countSubmissionStatus(
  items: AdminSubmissionDashboardItem[],
  status: string,
): number {
  return items.filter((item) => String(item.status).toUpperCase() === status)
    .length;
}

function statusLabel(status: string): string {
  const normalized = String(status || "PENDING").toUpperCase();
  if (normalized === "PENDING") return "Ожидает";
  if (normalized === "APPROVED") return "Одобрено";
  if (normalized === "REJECTED") return "Отклонено";
  if (normalized === "ALL") return "Все";
  return status;
}

function taskStateLabel(active: boolean): string {
  return active ? "Активно" : "Неактивно";
}

function taskKindLabel(kind: string): string {
  const value = String(kind || "").toLowerCase();
  if (value === "join_channel") return "Вступить в канал";
  if (value === "subscribe") return "Подписаться";
  if (value === "visit") return "Перейти по ссылке";
  if (value === "daily") return "Ежедневное задание";
  if (value === "watch_ad") return "Просмотр рекламы";
  return "Обычное задание";
}

function taskScopeLabel(scope: TaskScope): string {
  if (scope === "active") return "Активные";
  if (scope === "inactive") return "Неактивные";
  if (scope === "moderation") return "Модерация";
  if (scope === "attention") return "Внимание";
  return "Все задачи";
}

function referralScopeLabel(scope: ReferralScope): string {
  if (scope === "active") return "С активными";
  if (scope === "inactive") return "С неактивными";
  if (scope === "bonus") return "С бонусами";
  if (scope === "recent") return "Недавние";
  return "Все пригласившие";
}

function sumTaskBonuses(items: AdminTaskDashboardItem[]): string {
  return items.reduce(
    (acc, item) => sumScaledDown(acc, String(item.bonus_efhc || "0"), 8),
    "0",
  );
}

function sumTraceCredits(items: AdminTaskTraceDashboardItem[]): string {
  return items
    .filter((item) => String(item.direction).toUpperCase() === "CREDIT")
    .reduce(
      (acc, item) => sumScaledDown(acc, String(item.amount || "0"), 8),
      "0",
    );
}

function sumReferralBonuses(items: AdminReferralDashboardItem[]): string {
  return items.reduce(
    (acc, item) => sumScaledDown(acc, String(item.total_bonus_efhc || "0"), 8),
    "0",
  );
}

function buildTaskPoints(
  active: number,
  inactive: number,
  pending: number,
  approved: number,
  rejected: number,
): DashboardPoint[] {
  return [
    { id: "active", label: "активные", value: active, tone: "success" },
    { id: "inactive", label: "неактивные", value: inactive, tone: "neutral" },
    { id: "pending", label: "ожидают", value: pending, tone: "warning" },
    { id: "approved", label: "одобрено", value: approved, tone: "success" },
    { id: "rejected", label: "отклонено", value: rejected, tone: "neutral" },
  ];
}

function buildReferralPoints(
  inviters: number,
  active: number,
  inactive: number,
  withBonus: number,
  recent: number,
): DashboardPoint[] {
  return [
    { id: "inviters", label: "инвайтеры", value: inviters, tone: "info" },
    { id: "active", label: "активные", value: active, tone: "success" },
    { id: "inactive", label: "неактивные", value: inactive, tone: "neutral" },
    { id: "with-bonus", label: "с бонусом", value: withBonus, tone: "warning" },
    { id: "recent", label: "недавние", value: recent, tone: "info" },
  ];
}

function tasksFreshnessLabel(props: AdminTasksDashboardRuntimeProps): string {
  if (props.tasksError || props.submissionsError || props.traceError) {
    return "ошибка загрузки заданий";
  }
  if (props.loadingTasks || props.loadingSubmissions || props.loadingTrace) {
    return "обновление";
  }
  if (!props.tasks.length) return "заданий нет";
  return "данные заданий загружены";
}

function referralsFreshnessLabel(
  props: AdminReferralsDashboardRuntimeProps,
): string {
  if (props.error) return "ошибка загрузки рефералов";
  if (props.loading) return "обновление";
  if (!props.items.length) return "рефералов нет";
  return "данные рефералов загружены";
}

function safeInviterLabel(index: number): string {
  return `inviter #${index + 1}`;
}

export function AdminTasksDashboardRuntime(
  props: AdminTasksDashboardRuntimeProps,
) {
  const [scope, setScope] = useState<TaskScope>("all");
  const activeTasks = props.tasks.filter((task) => task.is_active).length;
  const inactiveTasks = props.tasks.length - activeTasks;
  const pending = countSubmissionStatus(props.submissions, "PENDING");
  const approved = countSubmissionStatus(props.submissions, "APPROVED");
  const rejected = countSubmissionStatus(props.submissions, "REJECTED");
  const selectedQueueTotal = props.submissions.length;
  const proofMissing = props.submissions.filter(
    (item) => !item.proof_text && !item.proof_url,
  ).length;
  const stalePending = props.submissions.filter((item) => {
    if (String(item.status).toUpperCase() !== "PENDING") return false;
    const days = ageDays(item.submitted_at);
    return days !== null && days >= 1;
  }).length;
  const approvedTraceCredits = props.traces.filter(
    (item) => String(item.direction).toUpperCase() === "CREDIT",
  ).length;
  const selectedBonusTotal = props.submissions.reduce(
    (acc, item) => sumScaledDown(acc, String(item.bonus_efhc || "0"), 8),
    "0",
  );
  const taskBonusTotal = formatD8ToHuman(sumTaskBonuses(props.tasks));
  const traceCreditAmount = formatD8ToHuman(sumTraceCredits(props.traces));
  const points = useMemo(
    () =>
      buildTaskPoints(activeTasks, inactiveTasks, pending, approved, rejected),
    [activeTasks, inactiveTasks, pending, approved, rejected],
  );
  const scopedTasks = props.tasks.filter((task) => {
    if (scope === "active") return task.is_active;
    if (scope === "inactive") return !task.is_active;
    if (scope === "moderation") return selectedQueueTotal > 0;
    if (scope === "attention") return proofMissing > 0 || stalePending > 0;
    return true;
  });
  const recentTasks = scopedTasks.slice(0, 8);
  const freshness =
    props.tasksError || props.submissionsError || props.traceError
      ? "stale"
      : props.loadingTasks || props.loadingSubmissions || props.loadingTrace
        ? "unknown"
        : props.tasks.length
          ? "fresh"
          : "stale";

  return (
    <section
      className="efhc-admin-tasks-referrals-dashboard-runtime efhc-admin-tasks-dashboard-runtime"
      data-admin-tasks-dashboard-runtime="1488"
      data-admin-tasks-referrals-dashboard-runtime="1488"
      data-admin-tasks-truth="raw-derived"
      data-admin-tasks-no-synthetic="true"
      data-admin-tasks-no-write-actions="true"
      data-admin-tasks-no-post-put-patch-delete="true"
      data-admin-tasks-no-idempotency-key="true"
      data-admin-tasks-no-raw-payload="true"
      data-admin-tasks-no-debug-json="true"
      data-admin-tasks-no-secrets="true"
      data-admin-tasks-no-fake-timeseries="true"
      data-admin-tasks-vis04-closed="true"
    >
      <AdminDashboardToolbar
        title="Задания и модерация"
        subtitle="Сводка заданий и заявок на модерацию."
        breadcrumb="Админ-панель / Задания"
        refresh={
          <AdminRefreshPicker
            disabled={
              props.loadingTasks ||
              props.loadingSubmissions ||
              props.loadingTrace
            }
            label="Обновление"
            onRefresh={() => {
              props.onRefreshTasks();
              props.onRefreshSubmissions();
              props.onRefreshTrace();
            }}
            refreshLabel="Обновить задания"
            value="manual"
          />
        }
        updatedAt={props.updatedAt || "Данные заданий"}
        freshness={
          <AdminFreshnessBadge
            freshness={freshness}
            label={tasksFreshnessLabel(props)}
            updatedAt={props.updatedAt || "Текущие данные"}
          />
        }
        filters={
          <AdminFilterBar
            groups={[
              {
                key: "tasks-scope",
                label: "Срез",
                value: scope,
                queryKey: "tasks_scope",
                querySync: "safe_display_only",
                onChange: (value) => setScope(value as TaskScope),
                options: [
                  { key: "all", label: "Все" },
                  { key: "active", label: "Активные" },
                  { key: "inactive", label: "Неактивные" },
                  { key: "moderation", label: "Модерация" },
                  { key: "attention", label: "Внимание" },
                ],
              },
            ]}
            onReset={() => setScope("all")}
            resetLabel="Сбросить"
          />
        }
      />

      <AdminDashboardGrid>
        <AdminKpiCard
          label="Всего задач"
          value={humanInt(props.tasks.length)}
          meta={`${activeTasks} активных / ${inactiveTasks} неактивных`}
          hint="Текущий каталог заданий."
          tone="info"
        />
        <AdminKpiCard
          label="Очередь выбранной задачи"
          value={humanInt(selectedQueueTotal)}
          meta={
            props.selectedTaskId
              ? `Задание №${props.selectedTaskId}`
              : "Задание не выбрано"
          }
          hint="Заявки считаются только по текущему выбранному заданию."
          tone={pending ? "warning" : "neutral"}
        />
        <AdminKpiCard
          label="Ожидают проверки"
          value={humanInt(pending)}
          meta={`${pct(pending, selectedQueueTotal)}%`}
          hint="Заявки, ожидающие решения."
          tone={pending ? "warning" : "success"}
        />
        <AdminKpiCard
          label="Начисления"
          value={`${traceCreditAmount} EFHCb`}
          meta={`${approvedTraceCredits} начислений`}
          hint="Последние начисления за задания."
          tone="success"
        />
      </AdminDashboardGrid>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <AdminPanelChrome
          title="Состояние заданий"
          subtitle="Каталог заданий и выбранная очередь модерации."
          status={props.tasks.length ? "success" : "empty"}
          tone="info"
          source="Задания и заявки"
          updatedAt={props.updatedAt || "Текущие данные"}
        >
          <AdminMiniBarChart
            ariaLabel="Распределение задач и заявок"
            emptyLabel="нет данных"
            points={points}
            source="Расчёт по текущим данным"
            unit="записи"
          />
          <div className="mt-4 space-y-3">
            <AdminProgressBar
              label="Активные задачи"
              max={Math.max(props.tasks.length, 1)}
              showValue
              source="активные / всего заданий"
              tone="success"
              value={activeTasks}
            />
            <AdminProgressBar
              label="Очередь ожидает"
              max={Math.max(selectedQueueTotal, 1)}
              showValue
              source="ожидают проверки / заявки выбранного задания"
              tone="warning"
              value={pending}
            />
            <AdminProgressBar
              label="Недостаточно подтверждения"
              max={Math.max(selectedQueueTotal, 1)}
              showValue
              source="Заявки без подтверждения"
              tone={proofMissing ? "danger" : "neutral"}
              value={proofMissing}
            />
          </div>
        </AdminPanelChrome>

        <AdminPanelChrome
          title="Требуют внимания"
          subtitle="Маяки не заменяют модерацию и не принимают решений за администратора."
          status={stalePending || proofMissing ? "stale" : "success"}
          tone={stalePending || proofMissing ? "warning" : "success"}
          source="По времени отправки заявок"
          updatedAt={props.updatedAt || "Текущие данные"}
        >
          <AdminHeatStrip
            ariaLabel="Заявки, требующие внимания"
            emptyLabel="нет маяков"
            points={[
              {
                id: "pending",
                label: "ожидают",
                value: pending,
                tone: "warning",
              },
              {
                id: "stale",
                label: "старше 1д",
                value: stalePending,
                tone: "danger",
              },
              {
                id: "missing-proof",
                label: "без подтверждения",
                value: proofMissing,
                tone: "danger",
              },
              {
                id: "approved",
                label: "одобрено",
                value: approved,
                tone: "success",
              },
              {
                id: "rejected",
                label: "отклонено",
                value: rejected,
                tone: "neutral",
              },
            ]}
            source="Распределение текущих заявок"
          />
          <AdminActionTable
            title="Доступные действия"
            rows={[
              {
                label: "Обзор",
                value: "Просмотр",
                hint: "Показывает состояние выбранной очереди.",
              },
              {
                label: "Подтверждаемое действие",
                value: "ниже страницы",
                hint: "Используйте кнопки модерации ниже на странице.",
              },
              {
                label: "Статусы",
                value: "На русском языке",
                hint: "Все состояния показаны понятными названиями.",
              },
            ]}
          />
        </AdminPanelChrome>
      </div>

      <AdminPanelChrome
        title="Порядок выполнения заданий"
        subtitle="Связи между заданиями и заявками пользователей."
        status="success"
        tone="neutral"
        source="Задания"
        updatedAt={props.updatedAt || "Текущие данные"}
      >
        <AdminFlowMapCard
          title="Порядок модерации"
          nodes={[
            {
              label: "1. Каталог",
              value: humanInt(props.tasks.length),
              hint: `${taskBonusTotal} EFHCb всего`,
              active: props.tasks.length > 0,
            },
            {
              label: "2. Выбор задачи",
              value: props.selectedTaskId ? `#${props.selectedTaskId}` : "—",
              hint: props.selectedTaskTitle || "выберите задачу",
              active: Boolean(props.selectedTaskId),
            },
            {
              label: "3. Очередь",
              value: humanInt(selectedQueueTotal),
              hint: statusLabel(props.selectedStatus),
              active: selectedQueueTotal > 0,
            },
            {
              label: "4. Решение администратора",
              value: "Одобрить / отклонить",
              hint: "Решение выполняется после подтверждения",
              active: pending > 0,
            },
            {
              label: "5. Начисление бонуса",
              value: `${formatD8ToHuman(selectedBonusTotal)} EFHCb`,
              hint: "Начисления выбранной очереди",
              active: approvedTraceCredits > 0,
            },
          ]}
        />
      </AdminPanelChrome>

      <AdminPanelChrome
        title={`Последние задания — ${taskScopeLabel(scope)}`}
        subtitle="Краткая сводка каталога заданий."
        status={recentTasks.length ? "success" : "empty"}
        tone="neutral"
        source="Задания"
        updatedAt={props.updatedAt || "Текущие данные"}
      >
        <div className="space-y-2">
          {recentTasks.length ? (
            recentTasks.map((task) => (
              <div
                className="rounded-2xl border p-3 text-sm"
                data-admin-tasks-dashboard-row="1488"
                key={task.id}
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <strong>
                      #{task.id} · {task.title}
                    </strong>
                    <div className="mt-1 text-xs efhc-text-muted">
                      {taskKindLabel(task.kind)} · {formatD8ToHuman(task.bonus_efhc || "0")}{" "}
                      EFHCb
                    </div>
                  </div>
                  <AdminStatusBadge
                    label={taskStateLabel(task.is_active)}
                    tone={task.is_active ? "success" : "neutral"}
                  />
                </div>
              </div>
            ))
          ) : (
            <div className="text-sm efhc-text-muted">
              Для выбранного среза задач нет.
            </div>
          )}
        </div>
      </AdminPanelChrome>
    </section>
  );
}

export function AdminReferralsDashboardRuntime(
  props: AdminReferralsDashboardRuntimeProps,
) {
  const [scope, setScope] = useState<ReferralScope>("all");
  const totalInviters = props.items.length;
  const totalActive = props.items.reduce(
    (sum, item) => sum + Number(item.active_count || 0),
    0,
  );
  const totalInactive = props.items.reduce(
    (sum, item) => sum + Number(item.inactive_count || 0),
    0,
  );
  const withBonus = props.items.filter(
    (item) => Number(item.total_bonus_efhc || 0) > 0,
  ).length;
  const recent = props.items.filter((item) => {
    const days = ageDays(item.last_invited_at);
    return days !== null && days <= 30;
  }).length;
  const totalBonus = formatD8ToHuman(sumReferralBonuses(props.items));
  const selected =
    props.items.find((item) => item.inviter_global_id === props.selectedInviter) ||
    null;
  const points = useMemo(
    () =>
      buildReferralPoints(
        totalInviters,
        totalActive,
        totalInactive,
        withBonus,
        recent,
      ),
    [totalInviters, totalActive, totalInactive, withBonus, recent],
  );
  const scopedItems = props.items.filter((item) => {
    if (scope === "active") return Number(item.active_count || 0) > 0;
    if (scope === "inactive") return Number(item.inactive_count || 0) > 0;
    if (scope === "bonus") return Number(item.total_bonus_efhc || 0) > 0;
    if (scope === "recent") {
      const days = ageDays(item.last_invited_at);
      return days !== null && days <= 30;
    }
    return true;
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
      className="efhc-admin-tasks-referrals-dashboard-runtime efhc-admin-referrals-dashboard-runtime"
      data-admin-referrals-dashboard-runtime="1488"
      data-admin-tasks-referrals-dashboard-runtime="1488"
      data-admin-referrals-truth="raw-derived"
      data-admin-referrals-no-synthetic="true"
      data-admin-referrals-no-write-actions="true"
      data-admin-referrals-no-post-put-patch-delete="true"
      data-admin-referrals-no-idempotency-key="true"
      data-admin-referrals-no-raw-payload="true"
      data-admin-referrals-no-debug-json="true"
      data-admin-referrals-no-secrets="true"
      data-admin-referrals-no-fake-growth-timeseries="true"
      data-admin-referrals-vis04-closed="true"
    >
      <AdminDashboardToolbar
        title="Реферальная сводка"
        subtitle="Сводка по рефералам и доступным действиям администратора."
        breadcrumb="Админ-панель / Рефералы"
        refresh={
          <AdminRefreshPicker
            disabled={props.loading}
            label="Обновление"
            onRefresh={props.onRefresh}
            refreshLabel="Обновить рефералов"
            value="manual"
          />
        }
        updatedAt={props.updatedAt || "Данные рефералов"}
        freshness={
          <AdminFreshnessBadge
            freshness={freshness}
            label={referralsFreshnessLabel(props)}
            updatedAt={props.updatedAt || "Текущие данные"}
          />
        }
        filters={
          <AdminFilterBar
            groups={[
              {
                key: "referrals-scope",
                label: "Срез",
                value: scope,
                queryKey: "referrals_scope",
                querySync: "safe_display_only",
                onChange: (value) => setScope(value as ReferralScope),
                options: [
                  { key: "all", label: "Все" },
                  { key: "active", label: "С активными" },
                  { key: "inactive", label: "С неактивными" },
                  { key: "bonus", label: "С бонусами" },
                  { key: "recent", label: "Недавние" },
                ],
              },
            ]}
            onReset={() => setScope("all")}
            resetLabel="Сбросить"
          />
        }
      />

      <AdminDashboardGrid>
        <AdminKpiCard
          label="Пригласившие"
          value={humanInt(totalInviters)}
          meta={props.hasNextPage ? "есть следующая страница" : "текущая страница"}
          hint="Текущая сводка рефералов."
          tone="info"
        />
        <AdminKpiCard
          label="Активные приглашённые"
          value={humanInt(totalActive)}
          meta={`${pct(totalActive, totalActive + totalInactive)}%`}
          hint="Количество активных рефералов."
          tone={totalActive ? "success" : "neutral"}
        />
        <AdminKpiCard
          label="Неактивные приглашённые"
          value={humanInt(totalInactive)}
          meta={`${pct(totalInactive, totalActive + totalInactive)}%`}
          hint="Количество неактивных рефералов."
          tone={totalInactive ? "warning" : "neutral"}
        />
        <AdminKpiCard
          label="Реферальные бонусы"
          value={`${totalBonus} EFHCb`}
          meta={`${withBonus} пригласивших с бонусом`}
          hint="Сводка не изменяет начисления."
          tone="success"
        />
      </AdminDashboardGrid>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <AdminPanelChrome
          title="Состояние рефералов"
          subtitle="Распределение рефералов по текущему состоянию."
          status={props.items.length ? "success" : "empty"}
          tone="info"
          source="Рефералы"
          updatedAt={props.updatedAt || "Текущие данные"}
        >
          <AdminMiniBarChart
            ariaLabel="Распределение рефералов"
            emptyLabel="нет данных"
            points={points}
            source="Расчёт по текущим данным"
            unit="записи"
          />
          <div className="mt-4 space-y-3">
            <AdminProgressBar
              label="Активные приглашённые"
              max={Math.max(totalActive + totalInactive, 1)}
              showValue
              source="активные / все приглашённые"
              tone="success"
              value={totalActive}
            />
            <AdminProgressBar
              label="Неактивные приглашённые"
              max={Math.max(totalActive + totalInactive, 1)}
              showValue
              source="неактивные / все приглашённые"
              tone={totalInactive ? "warning" : "neutral"}
              value={totalInactive}
            />
            <AdminProgressBar
              label="Пригласившие с бонусом"
              max={Math.max(totalInviters, 1)}
              showValue
              source="с бонусом / инвайтеры"
              tone="info"
              value={withBonus}
            />
          </div>
        </AdminPanelChrome>

        <AdminPanelChrome
          title="Управление рефералами"
          subtitle="Сводка показывает состояние рефералов без изменения связей и начислений."
          status="success"
          tone="neutral"
          source="Действия с рефералами"
          updatedAt={props.updatedAt || "Текущие данные"}
        >
          <AdminFlowMapCard
            title="Порядок действий с рефералами"
            nodes={[
              {
                label: "1. Сводка",
                value: humanInt(totalInviters),
                hint: "Просмотр списка",
                active: totalInviters > 0,
              },
              {
                label: "2. Выбор пользователя",
                value: selected ? "выбран" : "—",
                hint: selected ? "Подробности показаны ниже" : "Выберите запись ниже",
                active: Boolean(selected),
              },
              {
                label: "3. Ручной бонус",
                value: "Требует подтверждения",
                hint: "выполняется после подтверждения",
                active: false,
              },
              {
                label: "4. Переназначение",
                value: "Требует подтверждения",
                hint: "требует комментарий и подтверждение",
                active: false,
              },
            ]}
          />
          <AdminActionTable
            title="Безопасность действий"
            rows={[
              {
                label: "Обзор",
                value: "Просмотр",
                hint: "Раздел предназначен для просмотра.",
              },
              {
                label: "Распределение",
                value: "Текущее",
                hint: "Показывается текущее распределение рефералов.",
              },
              {
                label: "Названия состояний",
                value: "Понятные",
                hint: "Состояния показаны понятными названиями.",
              },
            ]}
          />
        </AdminPanelChrome>
      </div>

      <AdminPanelChrome
        title={`Реферальная сводка — ${referralScopeLabel(scope)}`}
        subtitle="Краткая сводка рефералов."
        status={scopedItems.length ? "success" : "empty"}
        tone="neutral"
        source="Рефералы"
        updatedAt={props.updatedAt || "Текущие данные"}
      >
        <div className="space-y-2">
          {scopedItems.slice(0, 8).map((item, index) => (
            <div
              className="rounded-2xl border p-3 text-sm"
              data-admin-referrals-dashboard-row="1488"
              key={item.inviter_global_id}
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <strong>{safeInviterLabel(index)}</strong>
                  <div className="mt-1 text-xs efhc-text-muted">
                    Активные: {item.active_count} · Неактивные:{" "}
                    {item.inactive_count} · Бонус:{" "}
                    {formatD8ToHuman(item.total_bonus_efhc)} EFHCb
                  </div>
                </div>
                <AdminStatusBadge
                  label={item.last_invited_at ? "Есть приглашения" : "Нет даты"}
                  tone={item.last_invited_at ? "success" : "neutral"}
                />
              </div>
            </div>
          ))}
          {!scopedItems.length ? (
            <div className="text-sm efhc-text-muted">
              Для выбранного среза referral summary пустой.
            </div>
          ) : null}
        </div>
      </AdminPanelChrome>
    </section>
  );
}
