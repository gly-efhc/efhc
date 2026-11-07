import React, { useMemo, useState } from "react";
import { format8 } from "../../lib/format";

import {
  SimActivityStrip,
  SimDashboardGrid,
  SimDashboardSection,
  SimDashboardToolbar,
  SimFilterBar,
  SimFreshnessBadge,
  SimMiniBarChart,
  SimPanelChrome,
  SimSegmentedProgress,
  SimStatCard,
} from "./SimulationDashboardUiKit";

export type TasksDashboardVisualState = "ready" | "wait" | "done";

export type TasksDashboardTask = {
  code: string;
  title: string;
  kindLabel: string;
  statusLabel: string;
  visualState: TasksDashboardVisualState;
  bonusEfhc: number;
  canClaim: boolean;
  nextAvailableAt?: string | null;
};

type TasksDashboardLabels = {
  title: string;
  subtitle: string;
  fresh: string;
  source: string;
  rawData: string;
  derivedDisplay: string;
  total: string;
  ready: string;
  waiting: string;
  completed: string;
  availableReward: string;
  progressTitle: string;
  progressSubtitle: string;
  rewardTitle: string;
  rewardSubtitle: string;
  groupsTitle: string;
  groupsSubtitle: string;
  filterLabel: string;
  filterAll: string;
  filterReady: string;
  filterWaiting: string;
  filterDone: string;
  reset: string;
  emptyTitle: string;
  emptyDetail: string;
  loading: string;
  error: string;
  publicBoundary: string;
  noHistory: string;
  actionBoundary: string;
};

type TasksDashboardRuntimeProps = {
  tasks: TasksDashboardTask[];
  labels: TasksDashboardLabels;
  loading?: boolean;
  error?: boolean;
  updatedAt?: string | null;
};

type TaskFilter = "all" | TasksDashboardVisualState;

type TaskTotals = {
  total: number;
  ready: number;
  wait: number;
  done: number;
  availableReward: number;
  completedPct: number;
};

function sumTasks(tasks: TasksDashboardTask[]): TaskTotals {
  const ready = tasks.filter((task) => task.visualState === "ready").length;
  const wait = tasks.filter((task) => task.visualState === "wait").length;
  const done = tasks.filter((task) => task.visualState === "done").length;
  const availableReward = tasks
    .filter((task) => task.canClaim)
    .reduce((acc, task) => acc + task.bonusEfhc, 0);
  const total = tasks.length;
  const completedPct = total > 0 ? (done / total) * 100 : 0;
  return { availableReward, completedPct, done, ready, total, wait };
}

function formatReward(value: number): string {
  if (!Number.isFinite(value)) return "0.00000000";
  try {
    return format8(String(value));
  } catch {
    // Invalid reward is not a zero and must not silently be displayed as one.
    return "—";
  }
}

function filterTasks(
  tasks: TasksDashboardTask[],
  statusFilter: TaskFilter,
): TasksDashboardTask[] {
  if (statusFilter === "all") return tasks;
  return tasks.filter((task) => task.visualState === statusFilter);
}

export function TasksDashboardRuntime(props: TasksDashboardRuntimeProps) {
  const [statusFilter, setStatusFilter] = useState<TaskFilter>("all");
  const totals = useMemo(() => sumTasks(props.tasks), [props.tasks]);
  const filteredTasks = useMemo(
    () => filterTasks(props.tasks, statusFilter),
    [props.tasks, statusFilter],
  );

  const statusLabel = props.error
    ? props.labels.error
    : props.loading
      ? props.labels.loading
      : props.labels.fresh;

  const freshness = props.error || props.loading ? "unknown" : "fresh";
  const panelStatus = props.error ? "error" : props.loading ? "loading" : "success";

  return (
    <section
      className="efhc-tasks-dashboard-runtime"
      data-dashboard-contract="tasks-dashboard-runtime"
      data-tasks-dashboard-runtime="1477"
      data-tasks-dashboard-no-public-history="true"
      data-tasks-dashboard-no-write-bypass="true"
      data-tasks-dashboard-truth="raw-derived"
    >
      <SimDashboardToolbar
        freshness={
          <SimFreshnessBadge freshness={freshness} label={statusLabel} />
        }
        subtitle={props.labels.subtitle}
        title={props.labels.title}
        updatedAt={props.updatedAt ?? props.labels.source}
      />

      <SimFilterBar
        groups={[
          {
            key: "tasks-status",
            kind: "task_status",
            label: props.labels.filterLabel,
            onChange: (value) => setStatusFilter(value as TaskFilter),
            options: [
              { key: "all", label: props.labels.filterAll },
              { key: "ready", label: props.labels.filterReady },
              { key: "wait", label: props.labels.filterWaiting },
              { key: "done", label: props.labels.filterDone },
            ],
            querySync: "disabled",
            value: statusFilter,
          },
        ]}
        onReset={() => setStatusFilter("all")}
        resetLabel={props.labels.reset}
      />

      <SimDashboardGrid>
        <SimStatCard
          label={props.labels.total}
          value={totals.total}
          hint={props.labels.rawData}
          tone="info"
        />
        <SimStatCard
          label={props.labels.ready}
          value={totals.ready}
          hint={props.labels.derivedDisplay}
          tone="success"
        />
        <SimStatCard
          label={props.labels.waiting}
          value={totals.wait}
          hint={props.labels.derivedDisplay}
          tone="warning"
        />
        <SimStatCard
          label={props.labels.completed}
          value={totals.done}
          hint={props.labels.derivedDisplay}
          tone="neutral"
        />
      </SimDashboardGrid>

      <SimDashboardGrid>
        <SimPanelChrome
          source={props.labels.source}
          status={panelStatus}
          statusLabel={statusLabel}
          title={props.labels.progressTitle}
          subtitle={props.labels.progressSubtitle}
          tone="info"
        >
          <SimSegmentedProgress
            dataKind="derived"
            label={props.labels.progressTitle}
            segments={[
              {
                id: "ready",
                label: props.labels.ready,
                max: totals.total || 1,
                tone: "success",
                value: totals.ready,
              },
              {
                id: "wait",
                label: props.labels.waiting,
                max: totals.total || 1,
                tone: "warning",
                value: totals.wait,
              },
              {
                id: "done",
                label: props.labels.completed,
                max: totals.total || 1,
                tone: "info",
                value: totals.done,
              },
            ]}
            source={props.labels.derivedDisplay}
            synthetic={false}
          />
        </SimPanelChrome>

        <SimPanelChrome
          source={props.labels.source}
          status={panelStatus}
          statusLabel={statusLabel}
          title={props.labels.rewardTitle}
          subtitle={props.labels.rewardSubtitle}
          tone="success"
        >
          <div className="efhc-tasks-dashboard-runtime__reward">
            <strong>{formatReward(totals.availableReward)} EFHC</strong>
            <span>{props.labels.availableReward}</span>
          </div>
          <SimMiniBarChart
            ariaLabel={props.labels.rewardTitle}
            dataKind="derived"
            emptyLabel={props.labels.emptyDetail}
            points={[
              { id: "ready", label: props.labels.ready, value: totals.ready },
              { id: "wait", label: props.labels.waiting, value: totals.wait },
              { id: "done", label: props.labels.completed, value: totals.done },
            ]}
            source={props.labels.derivedDisplay}
            synthetic={false}
            tone="success"
            unit="tasks"
          />
        </SimPanelChrome>
      </SimDashboardGrid>

      <SimDashboardSection
        title={props.labels.groupsTitle}
        subtitle={props.labels.groupsSubtitle}
      >
        <div className="efhc-tasks-dashboard-runtime__groups">
          {filteredTasks.length === 0 ? (
            <div className="efhc-tasks-dashboard-runtime__empty">
              <strong>{props.labels.emptyTitle}</strong>
              <span>{props.labels.emptyDetail}</span>
            </div>
          ) : (
            filteredTasks.slice(0, 6).map((task) => (
              <article
                aria-label={`${task.title}: ${task.statusLabel}`}
                className={`efhc-tasks-dashboard-runtime__task is-${task.visualState}`}
                data-task-dashboard-card="1477"
                data-task-dashboard-status={task.visualState}
                key={task.code}
              >
                <div>
                  <strong>{task.title}</strong>
                  <span>{task.kindLabel}</span>
                </div>
                <div>
                  <span>{task.statusLabel}</span>
                  <b>{formatReward(task.bonusEfhc)} EFHC</b>
                </div>
              </article>
            ))
          )}
        </div>
      </SimDashboardSection>

      <SimActivityStrip
        dataKind="derived"
        emptyLabel={props.labels.emptyDetail}
        label={props.labels.publicBoundary}
        points={[
          { id: "raw", label: props.labels.rawData, value: totals.total },
          { id: "derived", label: props.labels.derivedDisplay, value: totals.done },
          { id: "history", label: props.labels.noHistory, value: 0 },
          { id: "actions", label: props.labels.actionBoundary, value: totals.ready },
        ]}
        source={props.labels.source}
        synthetic={false}
        tone="info"
      />
    </section>
  );
}

