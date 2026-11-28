import React, { useCallback, useEffect, useMemo, useState } from "react";

import {
  ADMIN_EFHC_DEPOSITS_INBOX_PATH,
  ADMIN_EFHC_DEPOSITS_RUNTIME_SUMMARY_PATH,
  type AdminEfhcDepositsRuntimeSummaryResponse,
  ADMIN_EFHC_DEPOSITS_UNMATCHED_PATH,
} from "../../lib/api/generated/adminSeams";
import { adminSafeLoadError } from "../../lib/adminError";
import { buildJsonBlobFromTable, buildSimpleXlsx, downloadBlob } from "../../lib/export/simpleXlsx";
import { useAdminPageGlobalIdSelection } from "../../hooks/admin/useAdminPageGlobalIdSelection";
import { useAdminLinkedTransport } from "../../queries/useAdminLinkedTransport";
import type { AdminLogExportFormat, AdminLogExportRows } from "../../services/adminLogExport.service";
import type { DbId } from "../../types/db-id";
import { Button } from "../ui/Button";
import { AdminKpiCard } from "./AdminDashboardUiKit";
import { AdminCompactOperationList } from "./AdminCompactOperationList";
import { AdminListShell } from "./AdminListShell";
import { AdminSectionCard } from "./AdminSectionCard";

type TonInboxItem = {
  id: DbId;
  tx_hash: string;
  amount: string;
  memo?: string | null;
  from_address?: string | null;
  to_address?: string | null;
  status: string;
  resolved_global_id?: string | null;
  parsed_sku?: string | null;
  asset?: string | null;
  purpose?: string | null;
  retries_count: number;
  next_retry_at?: string | null;
  processed_at?: string | null;
  last_error?: string | null;
  created_at: string;
  updated_at: string;
};

type TonInboxResponse = {
  ok: boolean;
  items: TonInboxItem[];
  next_cursor_id?: DbId | null;
};

type UnmatchedItem = {
  id: DbId;
  tx_hash: string;
  asset: string;
  amount: string;
  from_address?: string | null;
  to_address?: string | null;
  memo?: string | null;
  reason?: string | null;
  resolved_global_id?: string | null;
  created_at: string;
};

type UnmatchedResponse = {
  ok: boolean;
  items: UnmatchedItem[];
  next_cursor_id?: DbId | null;
};

type VisibleDeposit = {
  key: string;
  txHash: string;
  status: string;
  amount: string;
  asset: string;
  globalId?: string | null;
  createdAt: string;
  unmatched: boolean;
};

const STATUS_OPTIONS = [
  { value: "", label: "Все состояния" },
  { value: "credited", label: "Зачислено" },
  { value: "pending_manual", label: "Нужно решение администратора" },
  { value: "error_retry", label: "Временная ошибка — можно повторить" },
  { value: "error_network_retry", label: "Связь с TON временно недоступна" },
  { value: "error_user_not_found", label: "Не найден пользователь" },
  { value: "error_bad_memo", label: "Не удалось понять назначение платежа" },
  { value: "parsed", label: "Распознано — обработка продолжается" },
  { value: "received", label: "Получено — ожидает обработки" },
] as const;

function statusLabel(status: string): string {
  return STATUS_OPTIONS.find((row) => row.value === status)?.label || "Неизвестное состояние";
}

function dateLabel(value?: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString("ru-RU");
}

function isDirectEfhcDeposit(item: TonInboxItem): boolean {
  if (String(item.parsed_sku || "").trim()) return false;
  const purpose = String(item.purpose || "").trim().toLowerCase();
  const asset = String(item.asset || "").trim().toUpperCase();
  const memo = String(item.memo || "").trim().toUpperCase();
  return purpose === "direct_efhc_jetton_deposit"
    || asset === "EFHC"
    || asset === "EFHCJ"
    || memo.startsWith("EFHC:")
    || memo.startsWith("EFHC|");
}

function isDirectUnmatched(item: UnmatchedItem): boolean {
  const asset = String(item.asset || "").trim().toUpperCase();
  const memo = String(item.memo || "").trim().toUpperCase();
  return asset === "EFHC" || asset === "EFHCJ" || memo.startsWith("EFHC:") || memo.startsWith("EFHC|");
}

function walletAddressMatches(value: string | null | undefined, walletAddress: string): boolean {
  if (!walletAddress) return true;
  const current = String(value || "").trim();
  const query = walletAddress.trim();
  if (!current || !query) return false;
  const rawTon = /^-?\d+:[0-9a-fA-F]{64}$/;
  if (rawTon.test(current) && rawTon.test(query)) return current.toLowerCase() === query.toLowerCase();
  return current === query;
}

function summaryAmount(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const raw = String(value).trim();
  const match = /^(-?)(\d+)(?:\.(\d+))?$/.exec(raw);
  if (!match) return raw;
  const [, sign, wholeRaw, fractionRaw = ""] = match;
  const whole = wholeRaw.replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  const fraction = fractionRaw.replace(/0+$/, "");
  return `${sign}${whole}${fraction ? `,${fraction}` : ""}`;
}

function csvCell(value: unknown): string {
  const text = String(value ?? "");
  return /[";,\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function csvBlob(rows: Array<Array<unknown>>): Blob {
  const body = `\uFEFF${rows.map((row) => row.map(csvCell).join(";")).join("\r\n")}`;
  return new Blob([body], { type: "text/csv;charset=utf-8" });
}

function searchKind(query: string): "none" | "global_id" | "wallet" {
  if (!query) return "none";
  return /^\d{10}$/.test(query) ? "global_id" : "wallet";
}

export function AdminTonInboxHumanPanel() {
  const adminApiRequest = useAdminLinkedTransport();
  const { selectedGlobalId, restored, rememberGlobalId, clearGlobalId } = useAdminPageGlobalIdSelection("efhc-deposits");
  const [items, setItems] = useState<TonInboxItem[]>([]);
  const [unmatched, setUnmatched] = useState<UnmatchedItem[]>([]);
  const [searchInput, setSearchInput] = useState("");
  const [appliedSearch, setAppliedSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exportRows, setExportRows] = useState<AdminLogExportRows>("100000");
  const [exporting, setExporting] = useState<AdminLogExportFormat | null>(null);
  const [summary, setSummary] = useState<AdminEfhcDepositsRuntimeSummaryResponse | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);

  const loadSummary = useCallback(async () => {
    setSummaryLoading(true);
    try {
      const response = await adminApiRequest<AdminEfhcDepositsRuntimeSummaryResponse>(
        ADMIN_EFHC_DEPOSITS_RUNTIME_SUMMARY_PATH,
        "GET",
      );
      setSummary(response);
    } catch (caught: unknown) {
      setError(adminSafeLoadError(caught));
    } finally {
      setSummaryLoading(false);
    }
  }, [adminApiRequest]);

  const loadOperations = useCallback(async (rawSearch: string): Promise<boolean> => {
    const queryValue = rawSearch.trim();
    const kind = searchKind(queryValue);
    const globalId = kind === "global_id" ? queryValue : "";
    const walletAddress = kind === "wallet" ? queryValue : "";

    setLoading(true);
    setError(null);
    try {
      const incomingRows: TonInboxItem[] = [];
      let incomingCursor: DbId | null = null;
      const incomingVisited = new Set<string>();
      let incomingPages = 0;
      do {
        incomingPages += 1;
        const params = new URLSearchParams({ limit: "20" });
        if (globalId) params.set("global_id", globalId);
        if (walletAddress) params.set("q", walletAddress);
        if (incomingCursor) params.set("cursor_id", String(incomingCursor));
        const response = await adminApiRequest<TonInboxResponse>(
          `${ADMIN_EFHC_DEPOSITS_INBOX_PATH}?${params.toString()}`,
          "GET",
        );
        incomingRows.push(...(response.items || []).filter(isDirectEfhcDeposit).filter((item) => {
          if (globalId) return String(item.resolved_global_id || "").trim() === globalId;
          if (walletAddress) {
            return walletAddressMatches(item.from_address, walletAddress)
              || walletAddressMatches(item.to_address, walletAddress);
          }
          return true;
        }));
        const next = response.next_cursor_id ?? null;
        const key = next == null ? "" : String(next);
        if (!key || incomingVisited.has(key)) break;
        incomingVisited.add(key);
        incomingCursor = next;
      } while (incomingRows.length < 20 && incomingPages < 50);

      let unmatchedRows: UnmatchedItem[] = [];
      if (queryValue) {
        unmatchedRows = [];
        let unmatchedCursor: DbId | null = null;
        const unmatchedVisited = new Set<string>();
        let unmatchedPages = 0;
        do {
          unmatchedPages += 1;
          const params = new URLSearchParams({ limit: "20" });
          if (globalId) params.set("global_id", globalId);
          if (walletAddress) params.set("q", walletAddress);
          if (unmatchedCursor) params.set("cursor_id", String(unmatchedCursor));
          const response = await adminApiRequest<UnmatchedResponse>(
            `${ADMIN_EFHC_DEPOSITS_UNMATCHED_PATH}?${params.toString()}`,
            "GET",
          );
          unmatchedRows.push(...(response.items || []).filter(isDirectUnmatched).filter((item) => {
            if (globalId) {
              return String(item.resolved_global_id || "").trim() === globalId;
            }
            if (walletAddress) {
              return walletAddressMatches(item.from_address, walletAddress)
                || walletAddressMatches(item.to_address, walletAddress);
            }
            return false;
          }));
          const next = response.next_cursor_id ?? null;
          const key = next == null ? "" : String(next);
          if (!key || unmatchedVisited.has(key)) break;
          unmatchedVisited.add(key);
          unmatchedCursor = next;
        } while (unmatchedRows.length < 20 && unmatchedPages < 50);
      }

      setItems(incomingRows.slice(0, 20));
      setUnmatched(unmatchedRows.slice(0, 20));
      return true;
    } catch (caught: unknown) {
      setItems([]);
      setUnmatched([]);
      setError(adminSafeLoadError(caught));
      return false;
    } finally {
      setLoading(false);
    }
  }, [adminApiRequest]);

  useEffect(() => {
    if (!restored) return;
    const remembered = selectedGlobalId ? String(selectedGlobalId) : "";
    if (remembered) {
      setSearchInput(remembered);
      setAppliedSearch(remembered);
    }
    void loadOperations(remembered);
    void loadSummary();
  }, [restored]);

  const visibleRows = useMemo<VisibleDeposit[]>(() => {
    const incomingRows: VisibleDeposit[] = items.map((item) => ({
      key: `inbox:${String(item.id)}`,
      txHash: item.tx_hash,
      status: item.status,
      amount: item.amount,
      asset: "EFHC",
      globalId: item.resolved_global_id,
      createdAt: item.created_at,
      unmatched: false,
    }));
    if (!appliedSearch) return incomingRows;

    const seenTx = new Set(incomingRows.map((row) => row.txHash));
    const unmatchedRows: VisibleDeposit[] = unmatched
      .filter((item) => !seenTx.has(item.tx_hash))
      .map((item) => ({
        key: `unmatched:${String(item.id)}`,
        txHash: item.tx_hash,
        status: "unmatched",
        amount: item.amount,
        asset: item.asset || "EFHC",
        globalId: item.resolved_global_id,
        createdAt: item.created_at,
        unmatched: true,
      }));
    return [...incomingRows, ...unmatchedRows]
      .sort((left, right) => Date.parse(right.createdAt) - Date.parse(left.createdAt))
      .slice(0, 20);
  }, [appliedSearch, items, unmatched]);

  async function exportDirectLogs(format: AdminLogExportFormat) {
    if (exporting) return;
    setExporting(format);
    setError(null);
    try {
      const requested = exportRows === "all" ? Number.MAX_SAFE_INTEGER : Number(exportRows);
      const scopedGlobalId = /^\d{10}$/.test(String(selectedGlobalId || "")) ? String(selectedGlobalId) : "";
      const exportSearch = appliedSearch.trim();
      const exportSearchKind = searchKind(exportSearch);
      const rows: Array<Array<unknown>> = [[
        "ID", "Хэш транзакции", "Сумма EFHC", "Статус", "Global ID", "Отправитель", "Получатель", "Назначение", "Получено", "Обработано",
      ]];
      const seenCursors = new Set<string>();
      let cursor: DbId | null = null;
      let collected = 0;
      while (collected < requested) {
        const params = new URLSearchParams({ limit: "200" });
        if (scopedGlobalId) params.set("global_id", scopedGlobalId);
        if (exportSearchKind === "wallet") params.set("q", exportSearch);
        if (cursor) params.set("cursor_id", String(cursor));
        const page = await adminApiRequest<TonInboxResponse>(`${ADMIN_EFHC_DEPOSITS_INBOX_PATH}?${params.toString()}`, "GET");
        for (const item of (page.items || []).filter(isDirectEfhcDeposit)) {
          if (scopedGlobalId) {
            const returnedOwner = String(item.resolved_global_id || "").trim();
            if (returnedOwner !== scopedGlobalId) {
              throw new Error("admin_deposit_export_scope_violation");
            }
          }
          if (exportSearchKind === "wallet" && !walletAddressMatches(item.from_address, exportSearch) && !walletAddressMatches(item.to_address, exportSearch)) continue;
          if (collected >= requested) break;
          rows.push([item.id, item.tx_hash, item.amount, statusLabel(item.status), item.resolved_global_id || "", item.from_address || "", item.to_address || "", item.memo || "", item.created_at, item.processed_at || ""]);
          collected += 1;
        }
        const next = page.next_cursor_id;
        const key = next == null ? "" : String(next);
        if (!key || seenCursors.has(key)) break;
        seenCursors.add(key);
        cursor = next ?? null;
      }
      const date = new Date().toISOString().slice(0, 10);
      const base = scopedGlobalId
        ? `efhc-direct-deposits-global-${scopedGlobalId}-${date}`
        : `efhc-direct-deposits-${date}`;
      if (format === "json") {
        downloadBlob(buildJsonBlobFromTable(rows, {
          kind: "efhc_admin_direct_deposits_export",
          generated_at: new Date().toISOString(),
          global_id: scopedGlobalId || null,
          search: exportSearch || null,
          rows: exportRows,
        }), `${base}.json`);
      } else if (format === "csv") {
        downloadBlob(csvBlob(rows), `${base}.csv`);
      } else if (format === "txt") {
        const body = rows.map((row) => row.map((value) => String(value ?? "")).join("\t")).join("\n");
        downloadBlob(new Blob([body], { type: "text/plain;charset=utf-8" }), `${base}.txt`);
      } else {
        downloadBlob(buildSimpleXlsx(rows, "Direct EFHC deposits"), `${base}.xlsx`);
      }
    } catch (caught: unknown) {
      setError(adminSafeLoadError(caught));
    } finally {
      setExporting(null);
    }
  }

  async function runSearch() {
    const query = searchInput.trim();
    if (!query) return;
    const ok = await loadOperations(query);
    if (!ok) return;
    setAppliedSearch(query);
    if (searchKind(query) === "global_id") rememberGlobalId(query);
  }

  function resetSearch() {
    clearGlobalId();
    setSearchInput("");
    setAppliedSearch("");
    setError(null);
    void loadOperations("");
  }

  return (
    <section className="space-y-4" data-admin-ton-inbox-human="true" data-admin-deposit-layout="kpi-search-logs-operations-v418">
      <AdminSectionCard
        title="Прямые пополнения EFHC"
        subtitle="Только EFHC jetton, отправленные через «+ EFHC» и зачисляемые в EFHCm. Shop-платежи здесь не отображаются."
      >
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" data-admin-efhc-deposits-summary="v394">
          <AdminKpiCard instanceId="deposits-summary-shown" eamFamily="EAM-ADMIN-022" visualPrimitive="ADMIN_SUMMARY_KPI" label="Всего операций" value={summaryLoading && !summary ? "—" : Number(summary?.credited_efhc_operations_count || 0).toLocaleString("ru-RU")} tone="neutral" />
          <AdminKpiCard instanceId="deposits-summary-attention" eamFamily="EAM-ADMIN-022" visualPrimitive="ADMIN_SUMMARY_KPI" label="Всего EFHC" value={summaryAmount(summary?.credited_efhc_total)} tone="neutral" />
          <AdminKpiCard instanceId="deposits-summary-next" eamFamily="EAM-ADMIN-022" visualPrimitive="ADMIN_SUMMARY_KPI" label="30 дней" value={summaryAmount(summary?.credited_efhc_30d)} tone="neutral" />
          <AdminKpiCard instanceId="deposits-summary-state" eamFamily="EAM-ADMIN-022" visualPrimitive="ADMIN_SUMMARY_KPI" label="24 часа EFHC" value={summaryAmount(summary?.credited_efhc_24h)} tone="neutral" />
        </div>
      </AdminSectionCard>

      <div
        className="grid w-full min-w-0 grid-cols-2 items-end"
        data-admin-deposit-search-v418="universal-global-id-or-ton"
        data-admin-selected-global-id={selectedGlobalId || "none"}
        data-admin-search-geometry="v425-v430"
        data-admin-global-id-search-canon="v435"
        style={{ gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: ".45rem" }}
      >
        <label className="col-span-2 min-w-0">
          <span className="sr-only">Global ID или TON-адрес</span>
          <input
            className="efhc-input w-full"
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
            placeholder="Global ID или TON-адрес"
            autoCapitalize="none"
            autoCorrect="off"
            spellCheck={false}
            style={{
              minHeight: "2.25rem",
              padding: ".52rem .62rem",
              borderRadius: ".68rem",
              borderColor: "var(--efhc-admin-canon-border-strong)",
              background: "var(--efhc-admin-canon-inset)",
              color: "var(--efhc-admin-canon-text)",
              boxShadow: "none",
            }}
          />
        </label>
        <Button
          variant="secondary"
          className="w-full min-w-0"
          onClick={resetSearch}
          disabled={loading || (!searchInput && !appliedSearch && !selectedGlobalId)}
          style={{
            minHeight: "2.25rem",
            padding: ".52rem .68rem",
            borderRadius: ".68rem",
            borderColor: "var(--efhc-admin-canon-border-strong)",
            background: "var(--efhc-admin-canon-inset)",
            color: "var(--efhc-admin-canon-text)",
            boxShadow: "none",
          }}
        >
          Сбросить
        </Button>
        <Button
          variant="secondary"
          className="w-full min-w-0"
          onClick={() => void runSearch()}
          disabled={loading || !searchInput.trim()}
          style={{
            minHeight: "2.25rem",
            padding: ".52rem .68rem",
            borderRadius: ".68rem",
            borderColor: "var(--efhc-admin-canon-border-strong)",
            background: "var(--efhc-admin-canon-inset)",
            color: "var(--efhc-admin-canon-text)",
            boxShadow: "none",
          }}
        >
          Найти
        </Button>
      </div>

      <AdminSectionCard title="Скачать журнал" subtitle="Стандартная выгрузка только прямых пополнений EFHC; покупки Shop в неё не входят.">
        <div
          className="efhc-admin-export-controls-v445 efhc-admin-deposits-export-v442"
          data-admin-direct-deposit-log-export="json-csv-txt-xlsx-v445"
          data-admin-direct-deposit-export-transport="GET /admin/efhc-deposits/inbox paginated"
        >
          <select className="efhc-admin-export-rows-v445" value={exportRows} onChange={(event) => setExportRows(event.target.value as AdminLogExportRows)} disabled={Boolean(exporting)} aria-label="Строк экспорта"><option value="100">100</option><option value="1000">1 000</option><option value="100000">100 000</option><option value="1000000">1 000 000</option><option value="all">Все</option></select>
          <div className="efhc-admin-deposits-export-strip-v442">
            {(["json", "csv", "txt", "xlsx"] as AdminLogExportFormat[]).map((format) => (
              <Button
                key={format}
                className="w-full min-w-0"
                variant="secondary"
                disabled={Boolean(exporting)}
                onClick={() => void exportDirectLogs(format)}
                aria-busy={exporting === format}
              >
                {format.toUpperCase()}
              </Button>
            ))}
          </div>
        </div>
      </AdminSectionCard>

      <AdminListShell title="Последние входящие операции">
        {visibleRows.length ? (
          <AdminCompactOperationList
            rows={visibleRows.map((row) => ({
              id: row.key,
              operation: row.unmatched ? "Нужна проверка" : statusLabel(row.status),
              amount: `${row.amount} ${row.asset}`,
              subject: row.globalId ? `Global ID ${row.globalId}` : "Global ID не определён",
              time: dateLabel(row.createdAt),
            }))}
          />
        ) : null}
      </AdminListShell>

      {error ? <p className="text-xs text-red-200" role="status">Данные временно недоступны. Обновите раздел и попробуйте снова.</p> : null}
    </section>
  );
}
