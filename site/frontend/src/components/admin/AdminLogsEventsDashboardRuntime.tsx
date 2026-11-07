import React, { useCallback, useEffect, useMemo, useState } from "react";

import { useLargeAdminFilter } from "../../hooks/admin/useLargeAdminFilter";
import {
  ADMIN_LOGS_TRANSFERS_PATH,
} from "../../lib/api/generated/adminSeams";

import {
  AdminActionTable,
  AdminDashboardGrid,
  AdminDashboardToolbar,
  AdminFilterBar,
  AdminFreshnessBadge,
  AdminHeatStrip,
  AdminKpiCard,
  AdminMiniBarChart,
  AdminPanelChrome,
  AdminRefreshPicker,
  AdminStatusBadge,
} from "./AdminDashboardUiKit";
import { adminSafeLoadError } from "../../lib/adminError";
import { useAdminLinkedTransport } from "../../queries/useAdminLinkedTransport";
import { isAdminVisualProofMode } from "../../proof/visualProofMode";
import { formatFixedDown, fromScaledBigint, toScaledBigintDown } from "../../lib/format";
import { buildSimpleXlsx, downloadBlob } from "../../lib/export/simpleXlsx";
import type { DbId } from "../../types/db-id";
import type { GlobalId } from "../../types/identity";


type AdminLogTone = "success" | "warning" | "danger" | "neutral" | "info";
type SeverityFilter = "all" | "attention" | "success" | "info";
type SourceFilter =
  | "all"
  | "task"
  | "bank"
  | "withdraw"
  | "deposit"
  | "referral"
  | "ads"
  | "panel"
  | "exchange"
  | "shop"
  | "admin_manual";
type TimeFilter = "latest" | "hour" | "day" | "month" | "year";

type TransferLogItem = {
  id: DbId;
  global_id?: string | null;
  amount: string;
  direction: string;
  balance_type: string;
  reason: string;
  created_at: string;
};

type TransferLogsOut = {
  ok: boolean;
  items: TransferLogItem[];
  next_cursor: string | null;
};

type EventPoint = {
  id: string;
  label: string;
  value: number;
  tone: AdminLogTone;
};

type DashboardEvent = {
  id: string;
  title: string;
  description: string;
  severity: "success" | "attention" | "info";
  source: SourceFilter;
  amountD8: string;
  amountLabel: string;
  balanceLabel: string;
  directionLabel: string;
  createdAt: string;
  redactedFields: number;
};

const EMPTY_RESPONSE: TransferLogsOut = {
  ok: false,
  items: [],
  next_cursor: null,
};

const VISUAL_PROOF_RESPONSE: TransferLogsOut = {
  ok: true,
  items: [
    {
      id: "156801" as DbId,
      amount: "100.00000000",
      direction: "user_credit",
      balance_type: "main",
      reason: "deposit credited · signature [REDACTED]",
      created_at: "2026-07-21T10:30:00Z",
    },
    {
      id: "156802" as DbId,
      amount: "25.00000000",
      direction: "user_debit",
      balance_type: "main",
      reason: "withdraw review · proof <redacted>",
      created_at: "2026-07-21T10:31:00Z",
    },
    {
      id: "156803" as DbId,
      amount: "5.00000000",
      direction: "user_credit",
      balance_type: "bonus",
      reason: "task bonus · safe summary",
      created_at: "2026-07-21T10:32:00Z",
    },
  ],
  next_cursor: null,
};

const SOURCE_OPTIONS: Array<{ key: SourceFilter; label: string }> = [
  { key: "all", label: "Все источники" },
  { key: "task", label: "Задачи" },
  { key: "bank", label: "Банк" },
  { key: "withdraw", label: "Выводы" },
  { key: "deposit", label: "Депозиты" },
  { key: "referral", label: "Рефералы" },
  { key: "ads", label: "Реклама" },
  { key: "panel", label: "Панели" },
  { key: "exchange", label: "Обмен" },
  { key: "shop", label: "Магазин" },
  { key: "admin_manual", label: "Ручные Admin-операции" },
];

const SEVERITY_OPTIONS: Array<{ key: SeverityFilter; label: string }> = [
  { key: "all", label: "Все статусы" },
  { key: "attention", label: "Внимание" },
  { key: "success", label: "Успешные" },
  { key: "info", label: "Инфо" },
];

const TIME_OPTIONS: Array<{ key: TimeFilter; label: string }> = [
  { key: "latest", label: "Последние" },
  { key: "hour", label: "За час" },
  { key: "day", label: "За сутки" },
  { key: "month", label: "За месяц" },
  { key: "year", label: "За год" },
];


function scopedLogErrorMessage(error: unknown): string {
  const code = error instanceof Error ? error.message : "";
  if (code === "admin_logs_selected_global_id_scope_unproven" || code === "admin_logs_export_scope_violation") {
    return "Операция заблокирована: сервер не подтвердил, что журнал ограничен выбранным Global ID.";
  }
  if (code === "admin_logs_scoped_export_unavailable_in_visual_proof") {
    return "Выгрузка по Global ID недоступна без подтверждённого server scope.";
  }
  return adminSafeLoadError(error);
}

function safeText(value: unknown): string {
  const text = String(value ?? "").trim();
  return text || "—";
}

function amountLabel(value: string): string {
  return formatFixedDown(value, 8);
}

function absoluteD8(value: string): bigint {
  const scaled = toScaledBigintDown(value, 8);
  return scaled < 0n ? -scaled : scaled;
}

function balanceTypeLabel(value: string): string {
  if (value === "main") return "основной баланс";
  if (value === "bonus") return "бонусный баланс";
  if (value === "bank") return "банк";
  return "тип баланса скрыт";
}

function directionLabel(value: string): string {
  if (value === "user_credit") return "зачисление пользователю";
  if (value === "user_debit") return "списание пользователя";
  if (value === "bank_credit") return "зачисление банку";
  if (value === "bank_debit") return "списание банка";
  return "операция";
}

function sourceFromReason(reason: string): SourceFilter {
  const value = reason.toLowerCase();
  if (value.includes("task")) return "task";
  if (value.includes("withdraw")) return "withdraw";
  if (value.includes("deposit") || value.includes("ton")) return "deposit";
  if (value.includes("bank") || value.includes("mint") || value.includes("burn")) {
    return "bank";
  }
  if (value.includes("referral") || value.includes("refer")) return "referral";
  if (value.includes("advert") || value.includes("rewarded_ad") || value.includes("ad_bonus")) return "ads";
  if (value.includes("panel")) return "panel";
  if (value.includes("exchange") || value.includes("convert")) return "exchange";
  if (value.includes("shop") || value.includes("purchase") || value.includes("nft") || value.includes("vip")) return "shop";
  if (value.includes("admin") || value.includes("manual")) return "admin_manual";
  return "all";
}

function eventSeverity(item: TransferLogItem): DashboardEvent["severity"] {
  const reason = item.reason.toLowerCase();
  if (reason.includes("reject") || reason.includes("fail")) return "attention";
  if (item.direction === "user_debit") return "attention";
  if (item.direction === "user_credit") return "success";
  return "info";
}

function severityTone(severity: DashboardEvent["severity"]): AdminLogTone {
  if (severity === "success") return "success";
  if (severity === "attention") return "warning";
  return "info";
}

function titleForEvent(item: TransferLogItem): string {
  const source = sourceFromReason(item.reason);
  if (source === "task") return "Task bonus event";
  if (source === "withdraw") return "Withdrawal money-path event";
  if (source === "deposit") return "Deposit ledger event";
  if (source === "bank") return "Bank ledger event";
  if (source === "referral") return "Referral ledger event";
  if (source === "ads") return "Advertising ledger event";
  if (source === "panel") return "Panel ledger event";
  if (source === "exchange") return "Exchange ledger event";
  if (source === "shop") return "Shop ledger event";
  if (source === "admin_manual") return "Manual Admin ledger event";
  return "Ledger event";
}

function toEvent(item: TransferLogItem): DashboardEvent {
  const severity = eventSeverity(item);
  const redactedFields = [
    "[REDACTED]",
    "•••",
    "<redacted>",
  ].filter((marker) => item.reason.includes(marker)).length;
  return {
    id: String(item.id),
    title: titleForEvent(item),
    description: safeText(item.reason),
    severity,
    source: sourceFromReason(item.reason),
    amountD8: formatFixedDown(item.amount, 8),
    amountLabel: amountLabel(item.amount),
    balanceLabel: balanceTypeLabel(item.balance_type),
    directionLabel: directionLabel(item.direction),
    createdAt: safeText(item.created_at),
    redactedFields,
  };
}

function withinTimeFilter(event: DashboardEvent, filter: TimeFilter): boolean {
  if (filter === "latest") return true;
  const ts = Date.parse(event.createdAt);
  if (!Number.isFinite(ts)) return true;
  const diffMs = Date.now() - ts;
  if (filter === "hour") return diffMs <= 60 * 60 * 1000;
  if (filter === "day") return diffMs <= 24 * 60 * 60 * 1000;
  if (filter === "month") return diffMs <= 30 * 24 * 60 * 60 * 1000;
  return diffMs <= 365 * 24 * 60 * 60 * 1000;
}

function buildPoints(events: DashboardEvent[]): EventPoint[] {
  const attention = events.filter((event) => event.severity === "attention").length;
  const success = events.filter((event) => event.severity === "success").length;
  const info = events.filter((event) => event.severity === "info").length;
  const task = events.filter((event) => event.source === "task").length;
  const bank = events.filter((event) => event.source === "bank").length;
  const withdraw = events.filter((event) => event.source === "withdraw").length;
  const deposit = events.filter((event) => event.source === "deposit").length;
  const referral = events.filter((event) => event.source === "referral").length;
  const ads = events.filter((event) => event.source === "ads").length;
  const panel = events.filter((event) => event.source === "panel").length;
  const exchange = events.filter((event) => event.source === "exchange").length;
  const shop = events.filter((event) => event.source === "shop").length;
  const adminManual = events.filter((event) => event.source === "admin_manual").length;
  return [
    { id: "attention", label: "Внимание", value: attention, tone: "warning" },
    { id: "success", label: "Успех", value: success, tone: "success" },
    { id: "info", label: "Инфо", value: info, tone: "info" },
    { id: "task", label: "Задачи", value: task, tone: "neutral" },
    { id: "bank", label: "Банк", value: bank, tone: "neutral" },
    { id: "withdraw", label: "Выводы", value: withdraw, tone: "warning" },
    { id: "deposit", label: "Депозиты", value: deposit, tone: "success" },
    { id: "referral", label: "Рефералы", value: referral, tone: "neutral" },
    { id: "ads", label: "Реклама", value: ads, tone: "neutral" },
    { id: "panel", label: "Панели", value: panel, tone: "neutral" },
    { id: "exchange", label: "Обмен", value: exchange, tone: "neutral" },
    { id: "shop", label: "Магазин", value: shop, tone: "neutral" },
    { id: "admin_manual", label: "Admin", value: adminManual, tone: "neutral" },
  ];
}



type SafeLogExportTextFormat = "json" | "csv" | "txt";
type SafeLogExportFormat = SafeLogExportTextFormat | "xlsx";
type SafeLogExportFilters = {
  source: SourceFilter;
  severity: SeverityFilter;
  time: TimeFilter;
};

function safeLogFilterLabels(filters: SafeLogExportFilters) {
  return {
    source: SOURCE_OPTIONS.find((option) => option.key === filters.source)?.label ?? filters.source,
    severity: SEVERITY_OPTIONS.find((option) => option.key === filters.severity)?.label ?? filters.severity,
    time: TIME_OPTIONS.find((option) => option.key === filters.time)?.label ?? filters.time,
  };
}

function safeLogExportRows(events: DashboardEvent[]) {
  return events.map((event) => ({
    event_id: event.id,
    title: event.title,
    summary: event.description,
    severity: event.severity,
    source: event.source,
    amount_d8: event.amountD8,
    balance: event.balanceLabel,
    direction: event.directionLabel,
    created_at: event.createdAt,
    redacted_fields: event.redactedFields,
  }));
}

function csvCell(value: unknown): string {
  const text = String(value ?? "");
  return `"${text.replace(/"/g, '""')}"`;
}

function safeLogExportBody(
  events: DashboardEvent[],
  format: SafeLogExportTextFormat,
  generatedAt: string,
  filters: SafeLogExportFilters,
): string {
  const rows = safeLogExportRows(events);
  const filterLabels = safeLogFilterLabels(filters);
  if (format === "json") {
    return JSON.stringify({
      kind: "efhc_admin_safe_logs",
      generated_at: generatedAt,
      count: rows.length,
      filters: filterLabels,
      safety: "sanitized transfer-log snapshot; raw payload, secrets and idempotency data excluded",
      items: rows,
    }, null, 2);
  }
  if (format === "csv") {
    const headers = [
      "event_id", "title", "summary", "severity", "source",
      "amount_d8", "balance", "direction", "created_at",
      "redacted_fields",
    ];
    return [
      headers.join(","),
      ...rows.map((row) => headers.map((key) =>
        csvCell(row[key as keyof typeof row]),
      ).join(",")),
    ].join("\n");
  }
  return [
    "EFHC Admin — безопасная выгрузка журнала для анализа",
    `Сформировано: ${generatedAt}`,
    `Событий: ${rows.length}`,
    `Фильтры: источник=${filterLabels.source}; статус=${filterLabels.severity}; период=${filterLabels.time}`,
    "Raw payload, secrets, idempotency data: excluded",
    "",
    ...rows.map((row) => [
      `#${row.event_id} · ${row.title} · ${row.severity}`,
      `${row.amount_d8} EFHC · ${row.direction} · ${row.balance}`,
      `${row.source} · ${row.created_at}`,
      row.summary,
      `Скрыто полей: ${row.redacted_fields}`,
    ].join("\n")),
  ].join("\n\n");
}

function downloadSafeLogs(
  events: DashboardEvent[],
  format: SafeLogExportFormat,
  filters: SafeLogExportFilters,
  scopedGlobalId = "",
): void {
  if (typeof window === "undefined" || typeof document === "undefined") return;
  const generatedAt = new Date().toISOString();
  if (format === "xlsx") {
    const rows = safeLogExportRows(events);
    const filterLabels = safeLogFilterLabels(filters);
    const table: Array<Array<unknown>> = [
      ["EFHC Admin — безопасная выгрузка журнала для анализа"],
      ["Сформировано", generatedAt],
      ["Событий", rows.length],
      ["Фильтр: источник", filterLabels.source],
      ["Фильтр: статус", filterLabels.severity],
      ["Фильтр: период", filterLabels.time],
      ["Safety", "Raw payload, secrets, idempotency data: excluded"],
      [],
      [
        "event_id", "title", "summary", "severity", "source",
        "amount_d8", "balance", "direction", "created_at",
        "redacted_fields",
      ],
      ...rows.map((row) => [
        row.event_id, row.title, row.summary, row.severity, row.source,
        row.amount_d8, row.balance, row.direction, row.created_at,
        row.redacted_fields,
      ]),
    ];
    downloadBlob(
      buildSimpleXlsx(table, "Admin logs"),
      scopedGlobalId
        ? `efhc-admin-safe-logs-global-${scopedGlobalId}-${generatedAt.slice(0, 10)}.xlsx`
        : `efhc-admin-safe-logs-${generatedAt.slice(0, 10)}.xlsx`,
    );
    return;
  }
  const body = safeLogExportBody(events, format, generatedAt, filters);
  const mime = format === "json"
    ? "application/json;charset=utf-8"
    : format === "csv"
      ? "text/csv;charset=utf-8"
      : "text/plain;charset=utf-8";
  const blob = new Blob([body], { type: mime });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = scopedGlobalId
    ? `efhc-admin-safe-logs-global-${scopedGlobalId}-${generatedAt.slice(0, 10)}.${format}`
    : `efhc-admin-safe-logs-${generatedAt.slice(0, 10)}.${format}`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

type AdminLogsEventsDashboardRuntimeProps = {
  selectedGlobalId?: GlobalId | null;
  selectionRestored?: boolean;
};

export function AdminLogsEventsDashboardRuntime({
  selectedGlobalId = null,
  selectionRestored = true,
}: AdminLogsEventsDashboardRuntimeProps = {}) {
  const visualProof = isAdminVisualProofMode();
  const adminApiRequest = useAdminLinkedTransport();
  const [response, setResponse] = useState<TransferLogsOut>(
    visualProof ? VISUAL_PROOF_RESPONSE : EMPTY_RESPONSE,
  );
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState<SafeLogExportFormat | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [source, setSource] = useState<SourceFilter>("all");
  const [severity, setSeverity] = useState<SeverityFilter>("all");
  const [time, setTime] = useState<TimeFilter>("latest");
  const [pendingSource, setPendingSource] = useState<SourceFilter>("all");
  const [pendingSeverity, setPendingSeverity] = useState<SeverityFilter>("all");
  const [pendingTime, setPendingTime] = useState<TimeFilter>("latest");
  const [filterApplyPressed, setFilterApplyPressed] = useState(false);

  const refresh = useCallback(() => {
    if (!selectionRestored) return;
    setLoading(true);
    setError(null);
    setResponse(EMPTY_RESPONSE);
    const scopedGlobalId = /^\d{10}$/.test(String(selectedGlobalId || ""))
      ? String(selectedGlobalId)
      : "";
    const params = new URLSearchParams({ limit: "20" });
    if (scopedGlobalId) params.set("global_id", scopedGlobalId);
    void adminApiRequest<TransferLogsOut>(`${ADMIN_LOGS_TRANSFERS_PATH}?${params.toString()}`, "GET")
      .then((next) => {
        if (scopedGlobalId) {
          const foreignOrUnproven = (next.items || []).some(
            (item) => String(item.global_id || "").trim() !== scopedGlobalId,
          );
          if (foreignOrUnproven) {
            throw new Error("admin_logs_selected_global_id_scope_unproven");
          }
        }
        setResponse(next);
        setUpdatedAt(new Date().toISOString());
      })
      .catch((err: unknown) => {
        setError(scopedLogErrorMessage(err));
        setResponse(EMPTY_RESPONSE);
        setUpdatedAt(new Date().toISOString());
      })
      .finally(() => setLoading(false));
  }, [adminApiRequest, selectedGlobalId, selectionRestored]);

  useEffect(() => {
    if (!selectionRestored) return;
    if (visualProof) {
      if (selectedGlobalId) {
        setError("Scoped Global ID view недоступен в visual-proof режиме без server authority.");
        setResponse(EMPTY_RESPONSE);
      } else {
        setError(null);
        setResponse(VISUAL_PROOF_RESPONSE);
      }
      setUpdatedAt("2026-07-21T10:32:00Z");
      return;
    }
    refresh();
  }, [refresh, selectedGlobalId, selectionRestored, visualProof]);

  useEffect(() => {
    if (!filterApplyPressed) return;
    const timer = window.setTimeout(() => setFilterApplyPressed(false), 420);
    return () => window.clearTimeout(timer);
  }, [filterApplyPressed]);

  const applyPendingFilters = useCallback(() => {
    setSource(pendingSource);
    setSeverity(pendingSeverity);
    setTime(pendingTime);
    setFilterApplyPressed(true);
  }, [pendingSeverity, pendingSource, pendingTime]);

  const selectedScopeProven = useMemo(() => {
    const scopedGlobalId = /^\d{10}$/.test(String(selectedGlobalId || ""))
      ? String(selectedGlobalId)
      : "";
    if (!scopedGlobalId) return true;
    return (response.items || []).every(
      (item) => String(item.global_id || "").trim() === scopedGlobalId,
    );
  }, [response.items, selectedGlobalId]);

  const events = useMemo(
    () => selectedScopeProven ? (response.items || []).map(toEvent) : [],
    [response.items, selectedScopeProven],
  );
  const syncEventFilter = useCallback(
    (event: DashboardEvent) => {
      const sourceOk = source === "all" || event.source === source;
      const severityOk =
        severity === "all" || event.severity === severity;
      return sourceOk && severityOk && withinTimeFilter(event, time);
    },
    [severity, source, time],
  );
  const largeFilter = useLargeAdminFilter(
    events,
    "logs",
    { now: Date.now(), severity, source, time },
    syncEventFilter,
  );
  const visibleEvents = largeFilter.filtered;
  const downloadAllSafeLogs = useCallback(async (format: SafeLogExportFormat) => {
    if (exporting) return;
    setExporting(format);
    setError(null);
    try {
      const scopedGlobalId = /^\d{10}$/.test(String(selectedGlobalId || "")) ? String(selectedGlobalId) : "";
      if (visualProof) {
        if (scopedGlobalId) throw new Error("admin_logs_scoped_export_unavailable_in_visual_proof");
        downloadSafeLogs(visibleEvents, format, { source, severity, time });
        return;
      }
      const collected: TransferLogItem[] = [];
      const seenIds = new Set<string>();
      const seenCursors = new Set<string>();
      let cursor: string | null = null;
      do {
        const params = new URLSearchParams({ limit: "80" });
        if (scopedGlobalId) params.set("global_id", scopedGlobalId);
        if (cursor) params.set("cursor", cursor);
        const page = await adminApiRequest<TransferLogsOut>(
          `${ADMIN_LOGS_TRANSFERS_PATH}?${params.toString()}`,
          "GET",
        );
        for (const item of page.items || []) {
          if (scopedGlobalId && String(item.global_id || "").trim() !== scopedGlobalId) {
            throw new Error("admin_logs_export_scope_violation");
          }
          const id = String(item.id);
          if (!seenIds.has(id)) {
            seenIds.add(id);
            collected.push(item);
          }
        }
        const next = page.next_cursor || null;
        if (!next || seenCursors.has(next)) break;
        seenCursors.add(next);
        cursor = next;
      } while (cursor);
      const exportEvents = collected.map(toEvent).filter(syncEventFilter);
      downloadSafeLogs(exportEvents, format, { source, severity, time }, scopedGlobalId);
    } catch (err: unknown) {
      setError(scopedLogErrorMessage(err));
    } finally {
      setExporting(null);
    }
  }, [adminApiRequest, exporting, selectedGlobalId, severity, source, syncEventFilter, time, visualProof, visibleEvents]);

  const points = useMemo(() => buildPoints(events), [events]);
  const visiblePoints = useMemo(() => buildPoints(visibleEvents), [visibleEvents]);
  const attentionCount = events.filter((event) => event.severity === "attention").length;
  const successCount = events.filter((event) => event.severity === "success").length;
  const totalAmount = fromScaledBigint(
    events.reduce((acc, event) => acc + absoluteD8(event.amountD8), 0n),
    8,
  );
  const freshness = error ? "stale" : loading ? "unknown" : "fresh";
  const redactedCount = events.reduce(
    (total, event) => total + event.redactedFields,
    0,
  );

  return (
    <section
      className="efhc-admin-logs-events-dashboard efhc-dashboard-surface"
      data-admin-logs-events-dashboard-runtime="1490"
      data-admin-reports-black-violet="v435"
      data-admin-logs-events-truth="read-only-transfer-log-snapshot"
      data-admin-logs-events-no-write-actions="true"
      data-admin-logs-events-no-raw-payload="true"
      data-admin-logs-events-no-debug-json="true"
      data-admin-logs-events-no-secrets="true"
      data-admin-logs-events-no-fake-timeseries="true"
      data-grafana-reference-only="true"
      data-sandbox-reference-only="true"
      data-admin-worker-filter={largeFilter.workerActive ? "active" : "idle"}
    >
      <div className="efhc-admin-reports-journals-head-v440">
        <div className="min-w-0">
          <h2 className="text-base font-semibold">Журналы</h2>
          <p className="mt-1 text-xs efhc-text-muted">
            Событийный журнал объединён с Отчётами как единый контур только для чтения просмотра и выгрузки. Отдельный модуль Журналы больше не нужен.
          </p>
        </div>
        <button
          type="button"
          className={`efhc-btn-secondary efhc-admin-reports-filter-apply-v440${filterApplyPressed ? " is-pressed" : ""}`}
          data-admin-log-filter-apply-v440
          data-pressed={filterApplyPressed ? "true" : "false"}
          aria-pressed={filterApplyPressed}
          onClick={applyPendingFilters}
        >
          Применить фильтры
        </button>
      </div>

      <div className="efhc-admin-logs-sticky-filters">
      <AdminDashboardToolbar
        title="Журнал событий"
        subtitle="Операторская лента безопасных событий без исходного содержимого запросов и без секретов."
        breadcrumb="Админ / Журналы"
        refresh={(
          <AdminRefreshPicker
            label="Обновление журнала"
            onRefresh={refresh}
            refreshLabel="Обновить события"
            value="manual"
          />
        )}
        updatedAt={updatedAt || "снимок ожидается"}
        freshness={(
          <AdminFreshnessBadge
            freshness={freshness}
            label={loading ? "загрузка" : error ? "ошибка" : "снимок событий"}
          />
        )}
        filters={(
          <AdminFilterBar
            groups={[
              {
                key: "log-source",
                label: "Источник",
                value: pendingSource,
                options: SOURCE_OPTIONS,
                onChange: (value) => setPendingSource(value as SourceFilter),
                querySync: "disabled",
              },
              {
                key: "log-severity",
                label: "Статус",
                value: pendingSeverity,
                options: SEVERITY_OPTIONS,
                onChange: (value) => setPendingSeverity(value as SeverityFilter),
                querySync: "disabled",
              },
              {
                key: "log-time",
                label: "Период",
                value: pendingTime,
                options: TIME_OPTIONS,
                onChange: (value) => setPendingTime(value as TimeFilter),
                querySync: "disabled",
              },
            ]}
            onReset={() => {
              setPendingSource("all");
              setPendingSeverity("all");
              setPendingTime("latest");
              setSource("all");
              setSeverity("all");
              setTime("latest");
            }}
            resetLabel="Сбросить"
          />
        )}
      />
      </div>

      <AdminDashboardGrid>
        <AdminKpiCard
          label="Всего событий"
          value={String(events.length)}
          meta="снимок журнала переводов"
          hint="GET /admin/logs/transfers?limit=20 + cursor"
          tone="neutral"
        />
        <AdminKpiCard
          label="Внимание"
          value={String(attentionCount)}
          meta="расчётный статус"
          hint="Списания, признаки отказа/ошибки и события, требующие внимания."
          tone={attentionCount > 0 ? "warning" : "success"}
        />
        <AdminKpiCard
          label="Успешные"
          value={String(successCount)}
          meta="расчётный статус"
          hint="Зачисления и успешные события учёта."
          tone="success"
        />
        <AdminKpiCard
          label="Скрытые поля"
          value={String(redactedCount)}
          meta="безопасно скрытые поля"
          hint="Исходные значения никогда не показываются."
          tone={redactedCount ? "warning" : "success"}
        />
        <AdminKpiCard
          label="Объём"
          value={amountLabel(totalAmount)}
          meta="абсолютная сумма EFHC"
          hint="Сумма абсолютных значений только для видимого снимка."
          tone="info"
        />
      </AdminDashboardGrid>

      <AdminPanelChrome
        title="Распределение событий"
        subtitle="Сводка статусов без вымышленной истории: только текущий снимок."
        status={error ? "error" : loading ? "loading" : "success"}
        source="GET /admin/logs/transfers"
      >
        <AdminMiniBarChart
          points={visiblePoints}
          label="Видимый срез"
          unit="событий"
          source="расчёт по текущему снимку"
          dataKind="derived"
          ariaLabel="Распределение событий журнала администратора"
        />
        <div className="mt-3 flex flex-wrap gap-2">
          {points.map((point) => (
            <AdminStatusBadge
              key={point.id}
              label={`${point.label}: ${point.value}`}
              tone={point.tone}
            />
          ))}
        </div>
      </AdminPanelChrome>

      <AdminPanelChrome
        title="Выгрузка журнала для анализа"
        subtitle="Выгрузка дочитывает журнал по cursor и применяет текущие фильтры: источник, статус и период. Raw payload, секреты и данные идемпотентности не экспортируются."
        status={visibleEvents.length === 0 ? "empty" : "success"}
        source="GET /admin/logs/transfers + cursor; filtered safe export"
      >
        <div className="mb-2 text-xs text-slate-400" data-admin-log-export-filters="v207">
          Текущие фильтры: {safeLogFilterLabels({ source, severity, time }).source} · {safeLogFilterLabels({ source, severity, time }).severity} · {safeLogFilterLabels({ source, severity, time }).time}
        </div>
        <div className="efhc-admin-log-export-strip" data-admin-safe-log-export="json-csv-txt-xlsx" data-admin-safe-log-export-filtered="v440">
          <button
            type="button"
            className="efhc-admin-log-load-more w-full"
            disabled={Boolean(exporting)}
            onClick={() => void downloadAllSafeLogs("json")}
          >
            JSON
          </button>
          <button
            type="button"
            className="efhc-admin-log-load-more w-full"
            disabled={Boolean(exporting)}
            onClick={() => void downloadAllSafeLogs("csv")}
          >
            CSV
          </button>
          <button
            type="button"
            className="efhc-admin-log-load-more w-full"
            disabled={Boolean(exporting)}
            onClick={() => void downloadAllSafeLogs("txt")}
          >
            TXT
          </button>
          <button
            type="button"
            className="efhc-admin-log-load-more w-full"
            disabled={Boolean(exporting)}
            onClick={() => void downloadAllSafeLogs("xlsx")}
          >
            XLSX
          </button>
        </div>
        <p className="mt-2 text-xs text-slate-400">
          Admin API Workbench остаётся отдельным инструментом проверки API; журнал выгружается отсюда.
        </p>
      </AdminPanelChrome>

      {selectedGlobalId ? (
        <AdminPanelChrome
          title={`Журнал Global ID ${selectedGlobalId}`}
          subtitle="Экранный список использует тот же page-local Global ID scope, что и выгрузка журнала. Чужая или неподтверждённая строка блокирует выбранный scope целиком."
          status={error ? "error" : loading ? "loading" : visibleEvents.length ? "success" : "empty"}
          source="GET /admin/logs/transfers?global_id={selected_global_id}"
        >
          {!loading && !error && selectedScopeProven && visibleEvents.length ? (
            <AdminActionTable
              rows={visibleEvents.map((event) => ({
                label: event.title,
                value: `${event.amountLabel} EFHC · ${event.directionLabel}`,
                hint: `${event.createdAt} · ${event.description}`,
              }))}
            />
          ) : (
            <p className="text-sm text-slate-400" data-admin-logs-list-mode="selected-global-id-v431">
              {loading ? "Загрузка журнала выбранного Global ID…" : error ? "Журнал выбранного Global ID не загружен." : "Для выбранного Global ID событий по текущим фильтрам не найдено."}
            </p>
          )}
        </AdminPanelChrome>
      ) : null}

      <AdminPanelChrome
        title="Полоса состояний событий"
        subtitle="Визуализация текущего снимка состояний, а не реальная временная история."
        status="success"
        source="расчёт по текущему снимку без заявления о временном ряде"
      >
        <AdminHeatStrip
          points={visiblePoints}
          ariaLabel="Текущие состояния событий журнала администратора"
          dataKind="derived"
        />
      </AdminPanelChrome>

      <AdminPanelChrome
        title="Переходы к рабочим разделам"
        subtitle="Сводка помогает перейти в нужный раздел, но сама не меняет данные."
        status="success"
        source="только навигация"
      >
        <AdminActionTable
          rows={[
            {
              label: "Задачи",
              value: "события бонусов заданий",
              hint: "Рабочие действия выполняются только в /admin/tasks.",
            },
            {
              label: "Банк",
              value: "события учёта",
              hint: "Mint/Burn остаются в защищённом банковском контуре.",
            },
            {
              label: "Выводы",
              value: "события выплат",
              hint: "Решения по выплатам остаются в /admin/withdrawals.",
            },
            {
              label: "Депозиты",
              value: "события входящих платежей",
              hint: "Повторная обработка и исключения остаются в /admin/efhc-deposits.",
            },
            {
              label: "Рефералы",
              value: "начисления и реферальные события",
            },
            {
              label: "Реклама",
              value: "рекламные начисления и события",
            },
            {
              label: "Панели",
              value: "активации и учёт панелей",
            },
            {
              label: "Обмен",
              value: "операции обмена EFHC",
            },
            {
              label: "Магазин",
              value: "покупки и связанные ledger-события",
            },
            {
              label: "Ручные Admin-операции",
              value: "ручные административные проводки",
            },
          ]}
        />
      </AdminPanelChrome>

      <AdminPanelChrome
        title="Границы достоверности и безопасности"
        subtitle="Журналы предназначены для наблюдения и не меняют бизнес-состояние системы."
        status={error ? "error" : "success"}
        tone={error ? "danger" : "neutral"}
        source="контракт журнала"
      >
        <AdminActionTable
          rows={[
            {
              label: "Источник",
              value: "журнал переводов только для чтения",
              hint: "События берутся из существующего административного API-маршрута.",
            },
            {
              label: "Данные",
              value: "только безопасная сводка",
              hint: "Исходные метаданные и отладочный JSON не показываются.",
            },
            {
              label: "Действия",
              value: "только навигация и поддержка",
              hint: "Сводка не меняет состояние системы.",
            },
            {
              label: "История",
              value: "только текущий снимок",
              hint: "Реальный временной ряд появится только после отдельного изменения серверного контракта.",
            },
          ]}
        />
        {error ? <p className="text-sm text-red-200">{error || null}</p> : null}
      </AdminPanelChrome>
    </section>
  );
}
