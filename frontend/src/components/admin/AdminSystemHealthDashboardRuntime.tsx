import React, { useCallback, useEffect, useMemo, useState } from "react";

import type { ApiRequestOptions, HttpMethod } from "../../lib/api";
import { adminSafeLoadError, adminUiErrorMessage } from "../../lib/adminError";
import { useAdminLinkedTransport } from "../../queries/useAdminLinkedTransport";
import { Button } from "../ui/Button";
import { TelegramEmptyState } from "../ui/telegram/TelegramEmptyState";
import { TelegramSectionRow } from "../ui/telegram/TelegramSectionRow";
import { TelegramStatusBadge } from "../ui/telegram/TelegramStatusBadge";
import { AdminSectionCard } from "./AdminSectionCard";


type BasicHealth = { status?: string; ok?: boolean };
type DbHealth = {
  ok?: boolean;
  db?: { ok?: boolean; error?: string };
  schema?: { ok?: boolean; status?: string; missing?: string[]; schema?: string };
};
type RuntimeHealth = {
  ok?: boolean;
  backend?: { ok?: boolean };
  db?: { ok?: boolean; error?: string };
  watcher?: {
    ok?: boolean;
    status?: string;
    task_name?: string;
    last_heartbeat?: string | null;
    heartbeat_age_sec?: number | null;
    stale_after_sec?: number | null;
    error?: string;
  };
};
type HealthSnapshot = {
  basic: BasicHealth | null;
  db: DbHealth | null;
  runtime: RuntimeHealth | null;
  updatedAt: string | null;
  error: string | null;
  loading: boolean;
};
type LinkedRequest = <T>(path: string, method: HttpMethod, options?: ApiRequestOptions) => Promise<T>;

type HealthRow = {
  key: string;
  label: string;
  ok: boolean | undefined;
  detail: string;
};

const initialSnapshot: HealthSnapshot = {
  basic: null,
  db: null,
  runtime: null,
  updatedAt: null,
  error: null,
  loading: true,
};

function isOk(value: unknown): boolean {
  return value === true || value === "ok";
}

function humanStatus(ok: boolean | undefined): string {
  if (ok === true) return "Работает";
  if (ok === false) return "Требует внимания";
  return "Нет данных";
}

function secondsLabel(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "время не получено";
  return `${Math.round(value)} сек. назад`;
}

async function loadHealthSnapshot(apiRequest: LinkedRequest): Promise<Omit<HealthSnapshot, "loading">> {
  const [basic, db, runtime] = await Promise.allSettled([
    apiRequest<BasicHealth>("/api/health", "GET"),
    apiRequest<DbHealth>("/api/health/db", "GET"),
    apiRequest<RuntimeHealth>("/api/health/runtime", "GET"),
  ]);
  const failed = [basic, db, runtime]
    .filter((item): item is PromiseRejectedResult => item.status === "rejected")
    .map((item) => adminUiErrorMessage(item.reason));
  return {
    basic: basic.status === "fulfilled" ? basic.value : null,
    db: db.status === "fulfilled" ? db.value : null,
    runtime: runtime.status === "fulfilled" ? runtime.value : null,
    updatedAt: new Date().toISOString(),
    error: failed.length ? failed.join("; ") : null,
  };
}

export function AdminSystemHealthDashboardRuntime() {
  const apiRequest = useAdminLinkedTransport();
  const [snapshot, setSnapshot] = useState<HealthSnapshot>(initialSnapshot);

  const refresh = useCallback(() => {
    setSnapshot((current) => ({ ...current, loading: true, error: null }));
    void loadHealthSnapshot(apiRequest)
      .then((next) => setSnapshot({ ...next, loading: false }))
      .catch((error: unknown) => {
        setSnapshot({ basic: null, db: null, runtime: null, updatedAt: new Date().toISOString(), error: adminSafeLoadError(error), loading: false });
      });
  }, [apiRequest]);

  useEffect(() => { refresh(); }, [refresh]);

  const rows = useMemo<HealthRow[]>(() => {
    const appOk = isOk(snapshot.basic?.status) || snapshot.runtime?.backend?.ok === true;
    const dbOk = snapshot.db?.db?.ok === true || snapshot.runtime?.db?.ok === true;
    const schemaMissing = snapshot.db?.schema?.missing || [];
    const watcher = snapshot.runtime?.watcher;
    return [
      { key: "app", label: "Приложение", ok: appOk, detail: "Можно ли открыть и использовать основные функции Admin." },
      { key: "db", label: "База данных", ok: dbOk, detail: "Доступны ли актуальные данные пользователей, операций и настроек." },
      { key: "schema", label: "Структура базы", ok: snapshot.db?.schema?.ok, detail: schemaMissing.length ? `Не хватает объектов: ${schemaMissing.length}.` : "Ожидаемая структура базы на месте." },
      { key: "watcher", label: "Фоновая обработка", ok: watcher?.ok, detail: `Последний служебный сигнал: ${secondsLabel(watcher?.heartbeat_age_sec)}.` },
    ];
  }, [snapshot]);

  const problemCount = rows.filter((row) => row.ok === false).length;
  const unknownCount = rows.filter((row) => row.ok === undefined).length;
  const overall = snapshot.loading ? "Проверяем…" : problemCount ? "Нужно проверить" : unknownCount ? "Данных недостаточно" : "Можно работать";

  return (
    <div className="space-y-4" data-admin-system-health-dashboard-runtime="simple-v192" data-admin-system-owner-correction="v354">
      <AdminSectionCard
        title="Карта состояния"
        subtitle="Четыре проверки, которые отвечают на вопрос: можно ли сейчас безопасно работать в Admin."
        actions={<Button variant="secondary" onClick={refresh} disabled={snapshot.loading}>{snapshot.loading ? "Проверка…" : "Проверить снова"}</Button>}
      >
        <div className="mb-3 flex items-center justify-between gap-3 rounded-xl border px-3 py-2" data-admin-system-overall-summary data-admin-primitive="inset" data-owner-highlight="theme03-violet-v352">
          <span className="text-sm efhc-text-muted">Итог</span>
          <strong>{overall}</strong>
        </div>
        <div className="efhc-admin-system-health-cards space-y-2" data-admin-primitive="list" data-admin-system-card-layout="withdrawal-positions-v354">
          {rows.map((row) => (
            <TelegramSectionRow
              key={row.key}
              compact
              className="efhc-admin-system-health-row"
              title={row.label}
              subtitle={row.detail}
              rightSlot={<TelegramStatusBadge label={humanStatus(row.ok)} tone={row.ok === true ? "connected" : row.ok === false ? "warning" : "neutral"} />}
            />
          ))}
        </div>
        <div className="mt-3 text-xs efhc-text-muted">Последняя проверка: {snapshot.updatedAt ? new Date(snapshot.updatedAt).toLocaleString() : "—"}</div>
      </AdminSectionCard>

      <AdminSectionCard title="Что делать при проблеме" subtitle="Не повторяйте финансовые операции вслепую.">
        <div className="space-y-2 text-sm">
          <p><b>1.</b> Откройте «Отчёты и журналы» и скачайте журнал за нужный период.</p>
          <p><b>2.</b> Передайте журнал разработчику, если причина не очевидна.</p>
          <p><b>3.</b> Admin API Workbench используйте только для точечной технической проверки конкретного API.</p>
        </div>
      </AdminSectionCard>

      {snapshot.error ? <TelegramEmptyState title="Часть проверок не ответила" detail={snapshot.error} /> : null}
    </div>
  );
}
