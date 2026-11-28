import React, { useEffect, useMemo, useState } from "react";

import { AdminPage } from "../../components/admin/AdminPage";
import { AdminListExpandControl, useAdminListWindow } from "../../components/admin/AdminListWindow";
import { AdminKpiCard } from "../../components/admin/AdminDashboardUiKit";
import {
  AdminTasksEditorPanel,
  type AdminTaskEditorItem,
  type AdminTaskEditorPayload,
} from "../../components/admin/AdminTasksEditorPanel";
import { Button } from "../../components/ui/Button";
import { TelegramEmptyState } from "../../components/ui/telegram/TelegramEmptyState";
import { TelegramStatusBadge } from "../../components/ui/telegram/TelegramStatusBadge";
import {
  taskTemplateForRecord,
  taskTemplateIdFromMeta,
  taskTemplateTarget,
} from "../../lib/tasks/templates";
import {
  adminPath,
  ADMIN_ADS_PROVIDERS_PATH,
  ADMIN_TASKS_PATH,
  ADMIN_TASKS_TASK_ID_PATH,
} from "../../lib/api/generated/adminSeams";
import { adminSafeLoadError, adminUiErrorMessage } from "../../lib/adminError";
import { useAdminLinkedTransport } from "../../queries/useAdminLinkedTransport";
import type { DbId } from "../../types/db-id";

type AdminTasksListOut = {
  items: AdminTaskEditorItem[];
  next_cursor: string | null;
};

type ProviderRow = {
  code: string;
  enabled: boolean;
  is_configured: boolean;
  rewarded_enabled?: boolean;
};

const PAGE_SIZE = 20;

type EditorMode = "create" | "edit" | null;

function taskFingerprint(kind: string, meta: Record<string, unknown> | null): string | null {
  const templateId = taskTemplateIdFromMeta(meta);
  if (!templateId) return null;
  if (kind === "watch_ad" || kind === "ads") {
    const ads = meta?.ads;
    const provider = ads && typeof ads === "object" && !Array.isArray(ads)
      ? String((ads as Record<string, unknown>).primary_provider || "").trim().toLowerCase()
      : "";
    return provider ? `${templateId}:provider:${provider}` : null;
  }
  const target = taskTemplateTarget(meta).trim().toLowerCase();
  return target ? `${templateId}:target:${target}` : null;
}

function taskExhausted(task: AdminTaskEditorItem): boolean {
  return task.kind !== "watch_ad" && task.kind !== "ads" && task.total_limit != null && task.performed_count >= task.total_limit;
}

function taskProvider(task: AdminTaskEditorItem): string {
  const ads = task.meta?.ads;
  if (!ads || typeof ads !== "object" || Array.isArray(ads)) return "";
  return String((ads as Record<string, unknown>).primary_provider || "").trim();
}

export default function AdminTasksPage() {
  const adminApiRequest = useAdminLinkedTransport();
  const [tasks, setTasks] = useState<AdminTaskEditorItem[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [selectedTaskId, setSelectedTaskId] = useState<DbId | null>(null);
  const [editorMode, setEditorMode] = useState<EditorMode>(null);
  const [loading, setLoading] = useState(false);
  const [queryText, setQueryText] = useState("");
  const [activeFilter, setActiveFilter] = useState<"all" | "active" | "inactive">("all");
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const taskWindow = useAdminListWindow(tasks, "admin-tasks");

  const selectedTask = useMemo(
    () => tasks.find((task) => task.id === selectedTaskId) || null,
    [selectedTaskId, tasks],
  );
  const activeCount = useMemo(() => tasks.filter((task) => task.is_active && !taskExhausted(task)).length, [tasks]);
  const completedTotal = useMemo(
    () => tasks.reduce((total, task) => total + Math.max(0, task.performed_count || 0), 0),
    [tasks],
  );
  const exhaustedCount = useMemo(() => tasks.filter(taskExhausted).length, [tasks]);

  async function loadTasks(nextCursor?: string | null, overrides?: { q?: string; active?: "all" | "active" | "inactive" }): Promise<void> {
    setLoading(true);
    setLoadError(null);
    try {
      const query = new URLSearchParams({ limit: String(PAGE_SIZE) });
      const qValue = (overrides?.q ?? queryText).trim();
      const activeValue = overrides?.active ?? activeFilter;
      if (qValue) query.set("q", qValue);
      if (activeValue !== "all") query.set("active", String(activeValue === "active"));
      if (nextCursor) query.set("cursor", nextCursor);
      const out = await adminApiRequest<AdminTasksListOut>(
        `${ADMIN_TASKS_PATH}?${query.toString()}`,
        "GET",
      );
      const rows = Array.isArray(out.items) ? out.items : [];
      setTasks((current) => nextCursor ? [...current, ...rows] : rows);
      setCursor(out.next_cursor || null);
      if (nextCursor) taskWindow.revealServerPage();
      else taskWindow.collapse();
    } catch (error) {
      setLoadError(adminSafeLoadError(error));
    } finally {
      setLoading(false);
    }
  }

  async function refreshTask(taskId: DbId): Promise<void> {
    const detail = await adminApiRequest<AdminTaskEditorItem>(
      adminPath(ADMIN_TASKS_TASK_ID_PATH, { task_id: taskId }),
      "GET",
    );
    setTasks((current) => current.map((task) => task.id === detail.id ? detail : task));
  }

  async function createTask(payload: AdminTaskEditorPayload): Promise<void> {
    setSaving(true);
    setMessage(null);
    try {
      const wanted = taskFingerprint(payload.kind, payload.meta);
      if (wanted) {
        let nextCursor: string | null = null;
        let pageCount = 0;
        do {
          const query = new URLSearchParams({ limit: String(PAGE_SIZE) });
          if (nextCursor) query.set("cursor", nextCursor);
          const page = await adminApiRequest<AdminTasksListOut>(`${ADMIN_TASKS_PATH}?${query.toString()}`, "GET");
          const duplicate = (page.items || []).find((task) => taskFingerprint(task.kind, task.meta) === wanted);
          if (duplicate) {
            throw new Error(`Такое задание уже существует: ${taskTemplateForRecord(duplicate.kind, duplicate.meta)?.adminLabel || duplicate.title}. Откройте существующую запись вместо создания дубликата.`);
          }
          nextCursor = page.next_cursor || null;
          pageCount += 1;
        } while (nextCursor && pageCount < 100);
        if (nextCursor) throw new Error("Проверка дубликатов не завершилась: каталог слишком большой. Уточните фильтр или повторите позже.");
      }
      const created = await adminApiRequest<AdminTaskEditorItem>(ADMIN_TASKS_PATH, "POST", { body: payload });
      setTasks((current) => [created, ...current.filter((task) => task.id !== created.id)]);
      setSelectedTaskId(created.id);
      setMessage("Задание создано.");
    } catch (error) {
      setMessage(adminUiErrorMessage(error));
      throw error;
    } finally {
      setSaving(false);
    }
  }

  async function updateTask(taskId: DbId, payload: Partial<AdminTaskEditorPayload>): Promise<void> {
    setSaving(true);
    setMessage(null);
    try {
      await adminApiRequest(
        adminPath(ADMIN_TASKS_TASK_ID_PATH, { task_id: taskId }),
        "PATCH",
        { body: payload },
      );
      await refreshTask(taskId);
      setMessage("Изменения сохранены.");
    } catch (error) {
      setMessage(adminUiErrorMessage(error));
      throw error;
    } finally {
      setSaving(false);
    }
  }

  async function deleteTask(taskId: DbId): Promise<void> {
    setSaving(true);
    setMessage(null);
    try {
      await adminApiRequest(
        adminPath(ADMIN_TASKS_TASK_ID_PATH, { task_id: taskId }),
        "DELETE",
      );
      setTasks((current) => current.filter((task) => task.id !== taskId));
      setSelectedTaskId((current) => current === taskId ? null : current);
      setMessage("Задание удалено.");
    } catch (error) {
      setMessage(adminUiErrorMessage(error));
      throw error;
    } finally {
      setSaving(false);
    }
  }

  async function toggleTask(task: AdminTaskEditorItem): Promise<void> {
    const next = !task.is_active;
    try {
      if (next && taskExhausted(task)) throw new Error("Нельзя включить задание: общий лимит уже исчерпан.");
      if (next) {
        const template = taskTemplateForRecord(task.kind, task.meta);
        if (template) {
          if (!template.advertising) {
            throw new Error("Включить задание пока нельзя: текущий сервер не публикует маршрут завершения и проверки для этого шаблона.");
          }
          const providerCode = taskProvider(task);
          const providers = await adminApiRequest<ProviderRow[]>(ADMIN_ADS_PROVIDERS_PATH, "GET");
          const provider = (Array.isArray(providers) ? providers : []).find((row) => row.code === providerCode);
          if (!providerCode || providerCode === "builtin_timer" || !provider?.enabled || !provider.is_configured || provider.rewarded_enabled === false) {
            throw new Error("Включить рекламное задание нельзя: выбранный production provider не готов к rewarded-проверке.");
          }
        }
      }
      await updateTask(task.id, { is_active: next });
      setMessage(next ? "Задание включено." : "Задание отключено.");
    } catch (error) {
      setMessage(adminUiErrorMessage(error));
    }
  }

  function openCreate(): void {
    setSelectedTaskId(null);
    setEditorMode("create");
  }

  function openEdit(taskId: DbId): void {
    setSelectedTaskId(taskId);
    setEditorMode("edit");
  }

  function closeEditor(): void {
    if (saving) return;
    setEditorMode(null);
  }

  async function confirmDelete(taskId: DbId): Promise<void> {
    if (!window.confirm("Удалить задание? Если у задания уже есть история, backend запретит удаление — тогда оставьте его выключенным.")) return;
    try {
      await deleteTask(taskId);
    } catch {
      // deleteTask already exposes the backend-safe message.
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadTasks(null, { q: queryText, active: activeFilter });
    }, queryText || activeFilter !== "all" ? 250 : 0);
    return () => window.clearTimeout(timer);
  }, [queryText, activeFilter]);

  useEffect(() => {
    if (!message) return;
    const timer = window.setTimeout(() => setMessage(null), 2200);
    return () => window.clearTimeout(timer);
  }, [message]);

  useEffect(() => {
    if (!editorMode) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !saving) setEditorMode(null);
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previous;
    };
  }, [editorMode, saving]);

  return (
    <AdminPage title="Задания" backHref="/admin">
      <div className="space-y-[14px]" data-admin-tasks-surface="minimal-v368" data-eam-family="EAM-ADMIN-018">
        <div
          className="efhc-admin-task-summary-kpis-v366"
          data-admin-task-summary="withdrawals-compact-v366"
          data-admin-task-summary-reference="EAM-ADMIN-015"
        >
          <AdminKpiCard instanceId="tasks-summary-total" eamFamily="EAM-ADMIN-018" visualPrimitive="ADMIN_SUMMARY_KPI" label="Заданий" value={tasks.length.toLocaleString("ru-RU")} tone="neutral" />
          <AdminKpiCard instanceId="tasks-summary-active" eamFamily="EAM-ADMIN-018" visualPrimitive="ADMIN_SUMMARY_KPI" label="Активных" value={activeCount.toLocaleString("ru-RU")} tone="neutral" />
          <AdminKpiCard instanceId="tasks-summary-completed" eamFamily="EAM-ADMIN-018" visualPrimitive="ADMIN_SUMMARY_KPI" label="Выполнено" value={completedTotal.toLocaleString("ru-RU")} tone="neutral" />
          <AdminKpiCard instanceId="tasks-summary-exhausted" eamFamily="EAM-ADMIN-018" visualPrimitive="ADMIN_SUMMARY_KPI" label="Лимит исчерпан" value={exhaustedCount.toLocaleString("ru-RU")} tone="neutral" />
        </div>

        <section className="efhc-admin-task-minimal-section" data-admin-primitive="section" data-admin-task-minimal-section>
          <div className="efhc-admin-task-minimal-head">
            <div className="efhc-admin-task-minimal-title">Задания</div>
            <Button onClick={openCreate}>Создать</Button>
          </div>

          <div className="efhc-admin-task-minimal-filters" data-admin-task-filters>
            <input
              className="efhc-admin-task-minimal-control"
              type="search"
              value={queryText}
              onChange={(event) => setQueryText(event.target.value)}
              placeholder="Поиск"
              aria-label="Поиск заданий"
            />
            <select
              className="efhc-admin-task-minimal-control"
              value={activeFilter}
              onChange={(event) => setActiveFilter(event.target.value as "all" | "active" | "inactive")}
              aria-label="Фильтр статуса заданий"
            >
              <option value="all">Все</option>
              <option value="active">Активные</option>
              <option value="inactive">Выключенные</option>
            </select>
          </div>

          {loadError ? <TelegramEmptyState title="Не удалось загрузить задания" detail={loadError} actionLabel="Повторить" onAction={() => void loadTasks(null)} /> : null}
          {!loadError && loading && !tasks.length ? <TelegramEmptyState title="Загрузка…" /> : null}
          {!loadError && !loading && !tasks.length ? <div className="efhc-admin-task-minimal-empty">Заданий нет</div> : null}

          <div className="efhc-admin-task-minimal-list" data-admin-task-catalog>
            {taskWindow.visibleItems.map((task) => {
              const exhausted = taskExhausted(task);
              const statusLabel = exhausted ? "Лимит" : task.is_active ? "Активно" : "Выключено";
              const statusTone = exhausted ? "warning" : task.is_active ? "active" : "inactive";
              return (
                <article className="efhc-admin-task-minimal-row" key={String(task.id)} data-admin-task-row={String(task.id)} data-admin-primitive="card">
                  <div className="efhc-admin-task-minimal-copy">
                    <div className="efhc-admin-task-minimal-name">{taskTemplateForRecord(task.kind, task.meta)?.adminLabel || task.title}</div>
                    <div className="efhc-admin-task-minimal-meta">{task.bonus_efhc} EFHCb · выполнено {task.performed_count.toLocaleString("ru-RU")}</div>
                  </div>
                  <div className="efhc-admin-task-minimal-status">
                    <TelegramStatusBadge label={statusLabel} tone={statusTone} dataStatus={exhausted ? "limit" : task.is_active ? "active" : "inactive"} />
                  </div>
                  <div className="efhc-admin-task-minimal-actions">
                    <Button variant="secondary" className="efhc-admin-task-minimal-edit" onClick={() => openEdit(task.id)} disabled={saving}>Изменить</Button>
                    <details className="efhc-admin-task-more">
                      <summary className="efhc-admin-task-more-button" aria-label="Действия">⋮</summary>
                      <div className="efhc-admin-task-more-menu">
                        <button type="button" onClick={() => void toggleTask(task)} disabled={saving}>{task.is_active ? "Отключить" : "Включить"}</button>
                        <button className="danger" type="button" onClick={() => void confirmDelete(task.id)} disabled={saving}>Удалить</button>
                      </div>
                    </details>
                  </div>
                </article>
              );
            })}
          </div>

          <AdminListExpandControl
            shown={taskWindow.visibleCount}
            total={taskWindow.totalCount}
            hasServerMore={Boolean(cursor)}
            loadingMore={loading}
            onExpand={() => {
              if (taskWindow.hasMore) taskWindow.expand();
              else if (cursor) void loadTasks(cursor);
            }}
            onCollapse={taskWindow.collapse}
          />
        </section>
      </div>

      {editorMode ? (
        <div
          className="efhc-admin-task-modal-overlay"
          data-admin-task-modal-overlay
          onMouseDown={(event) => { if (event.target === event.currentTarget) closeEditor(); }}
          aria-hidden="false"
        >
          <section className="efhc-admin-task-modal" data-admin-primitive="modal" role="dialog" aria-modal="true" aria-labelledby="adminTaskModalTitle">
            <header className="efhc-admin-task-modal-head">
              <div className="efhc-admin-task-modal-title" id="adminTaskModalTitle">{editorMode === "create" ? "Новое задание" : "Изменить задание"}</div>
              <button className="efhc-admin-task-modal-close" type="button" onClick={closeEditor} aria-label="Закрыть" disabled={saving}>×</button>
            </header>
            <div className="efhc-admin-task-modal-body">
              <AdminTasksEditorPanel
                key={`${editorMode}-${String(selectedTask?.id ?? "new")}`}
                mode={editorMode}
                task={editorMode === "edit" ? selectedTask : null}
                busy={saving}
                onCreate={createTask}
                onUpdate={updateTask}
                onDone={closeEditor}
              />
            </div>
          </section>
        </div>
      ) : null}

      {message ? <div className="efhc-admin-task-toast" role="status" aria-live="polite">{message}</div> : null}
    </AdminPage>
  );
}
