import React, { useMemo } from "react";
import type { GlobalId } from "../../types/identity";
import {
  AdminActionTable,
  AdminChartCard,
  AdminConfirmationBlock,
  AdminEmptyState,
  AdminErrorState,
  AdminFilterBar,
  AdminFlowMapCard,
  AdminKpiCard,
  AdminSectionHeader,
  AdminStatusBadge,
} from "./AdminDashboardUiKit";
import type { DbId } from "../../types/db-id";

type TaskLike = {
  id: DbId;
  title: string;
  description: string | null;
  is_active: boolean;
  bonus_efhc?: string;
  kind: string;
};

type SubmissionLike = {
  id: DbId;
  task_id: DbId;
  global_id: GlobalId;
  status: string;
  bonus_efhc?: string | null;
};

type Props = {
  tasks: TaskLike[];
  submissions: SubmissionLike[];
  selectedTaskId: DbId | null;
  selectedStatus: string;
  loadingTasks: boolean;
  loadingSubmissions: boolean;
  tasksError: string | null;
  submissionsError: string | null;
  operationMessage: string | null;
  taskCursor: string | null;
  submissionsCursor: string | null;
  onSelectTask: (taskId: DbId) => void;
  onStatusChange: (status: string) => void;
  onRefreshTasks: () => void;
  onRefreshSubmissions: () => void;
  onRefreshStatuses: () => void;
};

function countStatus(items: SubmissionLike[], status: string): number {
  return items.filter((item) => item.status === status).length;
}

function taskKindLabel(kind: string): string {
  const value = kind || "manual";
  if (value === "ad") return "Рекламное";
  if (value === "manual") return "С подтверждением";
  return value;
}

function taskTone(active: boolean): "success" | "neutral" {
  return active ? "success" : "neutral";
}

export function AdminTasksCatalogUxPanel(props: Props) {
  const activeTasks = props.tasks.filter((task) => task.is_active);
  const inactiveTasks = props.tasks.filter((task) => !task.is_active);
  const pending = countStatus(props.submissions, "PENDING");
  const approved = countStatus(props.submissions, "APPROVED");
  const rejected = countStatus(props.submissions, "REJECTED");
  const selectedTask = useMemo(
    () => props.tasks.find((task) => task.id === props.selectedTaskId) || null,
    [props.tasks, props.selectedTaskId],
  );
  const visibleTasks = useMemo(() => props.tasks.slice(0, 8), [props.tasks]);
  const activeShare = props.tasks.length
    ? Math.round((activeTasks.length / props.tasks.length) * 100)
    : 0;
  const moderationShare = props.submissions.length
    ? Math.round((pending / props.submissions.length) * 100)
    : 0;

  return (
    <section
      className="efhc-admin-tasks-catalog"
      data-admin-sandbox-source="ui-main data-table; section-cards; chart-area-interactive; MaterialM dashboard cards"
    >
      <AdminSectionHeader
        eyebrow="Задания"
        title="Мобильный каталог заданий и очередь модерации"
        subtitle={
          "Сначала администратор выбирает задание, затем работает " +
          "с очередью заявок пользователей."
        }
        actions={
          <button
            type="button"
            className="efhc-admin-live-dashboard_live"
            onClick={props.onRefreshTasks}
            disabled={props.loadingTasks}
          >
            {props.loadingTasks ? "Загрузка" : "Обновить каталог"}
          </button>
        }
      />

      <AdminFilterBar
        groups={[
          {
            label: "Очередь",
            value: props.selectedStatus,
            options: [
              { key: "PENDING", label: `Ожидает ${pending}` },
              { key: "APPROVED", label: `Одобрено ${approved}` },
              { key: "REJECTED", label: `Отклонено ${rejected}` },
              { key: "ALL", label: "Все" },
            ],
            onChange: props.onStatusChange,
          },
        ]}
      />

      <div className="efhc-admin-tasks-catalog_kpis">
        <AdminKpiCard
          label="Задания"
          value={props.tasks.length}
          meta={`${activeTasks.length} активно · ${inactiveTasks.length} неактивно`}
          hint="Управляемый каталог"
          tone="primary"
        />
        <AdminKpiCard
          label="Доля активных"
          value={`${activeShare}%`}
          meta="видимость каталога"
          hint="неактивные не удаляются"
          tone="success"
        />
        <AdminKpiCard
          label="Очередь"
          value={props.submissions.length}
          meta={`${pending} ожидает · ${approved} одобрено`}
          hint="проверка подтверждений"
          tone="warning"
        />
        <AdminKpiCard
          label="Выбрано"
          value={selectedTask ? `#${selectedTask.id}` : "нет"}
          meta={selectedTask ? taskKindLabel(selectedTask.kind) : "каталог заданий"}
          hint={selectedTask?.title || "выберите карточку"}
          tone="neutral"
        />
      </div>

      <AdminFlowMapCard
        title="Порядок модерации"
        nodes={[
          {
            label: "1. Задание",
            value: selectedTask ? `#${selectedTask.id}` : "нет",
            hint: selectedTask?.title || "выбор задания",
            active: Boolean(selectedTask),
          },
          {
            label: "2. Подтверждение пользователя",
            value: props.selectedStatus,
            hint: "Текст или ссылка подтверждения",
            active: true,
          },
          {
            label: "3. Решение модератора",
            value: "Одобрить / отклонить",
            hint: "требуется подтверждение операции",
            active: true,
          },
          {
            label: "4. Результат начисления",
            value: "Бонус EFHCb",
            hint: "Начисление отражается в балансе и истории",
            active: approved > 0,
          },
        ]}
      />

      <div className="efhc-admin-tasks-catalog_grid">
        <AdminChartCard
          title="Каталог заданий"
          subtitle="Удобное отображение на мобильных устройствах"
          meta={<AdminStatusBadge label="Каталог" tone="primary" />}
        >
          {props.tasksError ? (
            <AdminErrorState title="Ошибка каталога" text={props.tasksError} />
          ) : visibleTasks.length ? (
            <div className="efhc-admin-tasks-catalog_deck">
              {visibleTasks.map((task) => {
                const selected = task.id === props.selectedTaskId;
                return (
                  <button
                    key={task.id}
                    type="button"
                    className="efhc-admin-tasks-catalog_card"
                    data-selected={selected ? "true" : "false"}
                    onClick={() => props.onSelectTask(task.id)}
                  >
                    <strong>{task.title}</strong>
                    <span>
                      #{task.id} · {taskKindLabel(task.kind)}
                    </span>
                    <small>
                      {task.bonus_efhc || "0"} EFHC ·{" "}
                      {task.is_active ? "Активно" : "Неактивно"}
                    </small>
                    <AdminStatusBadge
                      label={task.is_active ? "Активно" : "Неактивно"}
                      tone={taskTone(task.is_active)}
                    />
                  </button>
                );
              })}
            </div>
          ) : (
            <AdminEmptyState
              title="Заданий нет"
              text="Каталог пуст или ещё не загружен."
            />
          )}
        </AdminChartCard>

        <AdminChartCard
          title="Состояние очереди"
          subtitle="Интерактивная сводка по текущему фильтру"
          meta={<AdminStatusBadge label="Модерация" tone="warning" />}
        >
          {props.submissionsError ? (
            <AdminErrorState
              title="Ошибка очереди"
              text={props.submissionsError}
            />
          ) : (
            <div
              className="efhc-admin-tasks-catalog_bars"
              aria-label="Состояние очереди модерации"
            >
              <span style={{ height: `${Math.max(10, moderationShare)}%` }}>
                ожидает {pending}
              </span>
              <span style={{ height: `${Math.max(10, approved * 15)}%` }}>
                одобрено {approved}
              </span>
              <span style={{ height: `${Math.max(10, rejected * 15)}%` }}>
                отклонено {rejected}
              </span>
            </div>
          )}
        </AdminChartCard>
      </div>

      <AdminActionTable
        title="Административные действия"
        rows={[
          {
            label: "Обновление каталога",
            value: props.loadingTasks ? "загрузка" : "доступно",
            hint: props.taskCursor
              ? "есть следующая страница"
              : "первая страница",
          },
          {
            label: "Обновление очереди",
            value: props.loadingSubmissions ? "загрузка" : "доступно",
            hint: props.submissionsCursor
              ? "есть следующая страница"
              : "текущий фильтр",
          },
          {
            label: "Контроль повторных начислений",
            value: "ручная проверка",
            hint: "Обрабатывает только завершённые старые записи",
          },
        ]}
      />

      <div className="efhc-admin-tasks-catalog_actions">
        <button type="button" onClick={props.onRefreshSubmissions}>
          Обновить очередь
        </button>
        <button type="button" onClick={props.onRefreshStatuses}>
          Контроль повторных начислений
        </button>
      </div>

      {props.operationMessage ? (
        <AdminConfirmationBlock
          title="Статус операции"
          text={props.operationMessage}
          confirmed
        />
      ) : null}
    </section>
  );
}
