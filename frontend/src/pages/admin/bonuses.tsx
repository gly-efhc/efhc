import React, { useEffect, useMemo, useState } from "react";

import {
  AdminBonusesCompactOverview,
  EMPTY_ADMIN_BONUS_SUMMARY,
  adminBonusSourceLabel,
  type AdminBonusItem,
  type AdminBonusSource,
  type AdminBonusSummary,
} from "../../components/admin/AdminBonusesAnalytics";
import { AdminPage } from "../../components/admin/AdminPage";
import { AdminListExpandControl, useAdminListWindow } from "../../components/admin/AdminListWindow";
import { AdminCompactOperationList } from "../../components/admin/AdminCompactOperationList";
import { AdminSectionCard } from "../../components/admin/AdminSectionCard";
import { Button } from "../../components/ui/Button";
import { TelegramEmptyState } from "../../components/ui/telegram/TelegramEmptyState";
import { useT } from "../../hooks/useT";
import { adminUiErrorMessage } from "../../lib/adminError";
import { ADMIN_BONUSES_PATH } from "../../lib/api/generated/adminSeams";
import { formatD8ToHuman } from "../../lib/format";
import { buildJsonBlobFromTable, buildSimpleXlsx, downloadBlob } from "../../lib/export/simpleXlsx";
import { useAdminPageGlobalIdSelection } from "../../hooks/admin/useAdminPageGlobalIdSelection";
import { useAdminLinkedTransport } from "../../queries/useAdminLinkedTransport";

type BonusActivity = {
  ok: boolean;
  summary: AdminBonusSummary;
  items: AdminBonusItem[];
  limit: number;
  offset: number;
  has_more: boolean;
};

type SourceFilter = "all" | AdminBonusSource;
type PeriodPreset = "all" | "24h" | "7d" | "30d" | "90d" | "custom";

const PAGE_SIZE = 20;
const PERIOD_MS: Record<Exclude<PeriodPreset, "all" | "custom">, number> = {
  "24h": 24 * 60 * 60 * 1000,
  "7d": 7 * 24 * 60 * 60 * 1000,
  "30d": 30 * 24 * 60 * 60 * 1000,
  "90d": 90 * 24 * 60 * 60 * 1000,
};

function formatDate(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

function periodLabel(period: PeriodPreset): string {
  if (period === "24h") return "Последние 24 часа";
  if (period === "7d") return "Последние 7 дней";
  if (period === "30d") return "Последние 30 дней";
  if (period === "90d") return "Последние 90 дней";
  if (period === "custom") return "Произвольный период";
  return "Весь период";
}

function customDateIso(value: string, endOfDay: boolean): string | null {
  if (!value) return null;
  const parsed = new Date(`${value}${endOfDay ? "T23:59:59.999" : "T00:00:00.000"}`);
  return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString();
}

export default function AdminBonusesPage() {
  const adminApiRequest = useAdminLinkedTransport();
  const t = useT();
  const { selectedGlobalId, restored, rememberGlobalId, clearGlobalId } = useAdminPageGlobalIdSelection("bonuses");
  const [summary, setSummary] = useState<AdminBonusSummary>(EMPTY_ADMIN_BONUS_SUMMARY);
  const [items, setItems] = useState<AdminBonusItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [serverHasMore, setServerHasMore] = useState(false);
  const [loadMessage, setLoadMessage] = useState("");
  const [readError, setReadError] = useState("");
  const [source, setSource] = useState<SourceFilter>("all");
  const [userFilter, setUserFilter] = useState("");
  const [period, setPeriod] = useState<PeriodPreset>("all");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [refreshNonce, setRefreshNonce] = useState(0);
  const [exporting, setExporting] = useState<"json" | "csv" | "xlsx" | "">("");
  const [visibleSources, setVisibleSources] = useState<Record<AdminBonusSource, boolean>>({
    tasks: true,
    referrals: true,
    manual: true,
  });

  const userFilterTrimmed = userFilter.trim();
  const validGlobalId = /^\d{10}$/.test(userFilterTrimmed);
  const invalidGlobalId = Boolean(userFilterTrimmed) && !validGlobalId;
  const selectedExportGlobalId = validGlobalId && String(selectedGlobalId || "") === userFilterTrimmed
    ? userFilterTrimmed
    : "";

  const dateBounds = useMemo(() => {
    if (period === "all") return { dateFrom: null, dateTo: null };
    if (period === "custom") {
      return {
        dateFrom: customDateIso(dateFrom, false),
        dateTo: customDateIso(dateTo, true),
      };
    }
    return {
      dateFrom: new Date(Date.now() - PERIOD_MS[period]).toISOString(),
      dateTo: null,
    };
  }, [dateFrom, dateTo, period]);

  const queryString = useMemo(() => {
    const q = new URLSearchParams();
    q.set("source", source);
    if (validGlobalId) q.set("global_id", userFilterTrimmed);
    if (dateBounds.dateFrom) q.set("date_from", dateBounds.dateFrom);
    if (dateBounds.dateTo) q.set("date_to", dateBounds.dateTo);
    return q.toString();
  }, [dateBounds.dateFrom, dateBounds.dateTo, source, userFilterTrimmed, validGlobalId]);

  const bonusWindow = useAdminListWindow(items, queryString);

  async function loadFirstPage() {
    if (invalidGlobalId) {
      setItems([]);
      setSummary(EMPTY_ADMIN_BONUS_SUMMARY);
      setServerHasMore(false);
      setLoadMessage("Global ID должен содержать ровно 10 цифр.");
      setReadError("");
      return;
    }
    setLoading(true);
    setLoadMessage("");
    setReadError("");
    try {
      const q = new URLSearchParams(queryString);
      q.set("limit", String(validGlobalId ? PAGE_SIZE : 1));
      q.set("offset", "0");
      const result = await adminApiRequest<BonusActivity>(
        `${ADMIN_BONUSES_PATH}?${q.toString()}`,
        "GET",
      );
      setSummary(result.summary ?? EMPTY_ADMIN_BONUS_SUMMARY);
      setItems(validGlobalId ? (result.items || []) : []);
      setServerHasMore(validGlobalId && Boolean(result.has_more));
      if (validGlobalId) rememberGlobalId(userFilterTrimmed);
      bonusWindow.collapse();
    } catch (e: unknown) {
      setItems([]);
      setSummary(EMPTY_ADMIN_BONUS_SUMMARY);
      setServerHasMore(false);
      setReadError(adminUiErrorMessage(e, t, "admin.errors.load_failed"));
    } finally {
      setLoading(false);
    }
  }

  async function collectFilteredRowsForExport(): Promise<AdminBonusItem[]> {
    if (!validGlobalId || invalidGlobalId) return [];
    const collected: AdminBonusItem[] = [];
    const seen = new Set<string>();
    let offset = 0;
    for (;;) {
      const q = new URLSearchParams(queryString);
      q.set("limit", "200");
      q.set("offset", String(offset));
      const result = await adminApiRequest<BonusActivity>(
        `${ADMIN_BONUSES_PATH}?${q.toString()}`,
        "GET",
      );
      for (const item of result.items || []) {
        if (seen.has(item.event_key)) continue;
        seen.add(item.event_key);
        collected.push(item);
      }
      if (!result.has_more || !(result.items || []).length) break;
      offset += (result.items || []).length;
    }
    return collected;
  }

  async function exportFilteredRows(format: "json" | "csv" | "xlsx") {
    if (!selectedExportGlobalId || exporting) return;
    setExporting(format);
    setLoadMessage("");
    try {
      const rows = await collectFilteredRowsForExport();
      if (rows.some((item) => String(item.global_id || "").trim() !== selectedExportGlobalId)) {
        throw new Error("admin_bonus_export_scope_violation");
      }
      const header = ["global_id", "created_at", "source", "amount_efhcb", "reason", "username", "admin_global_id"];
      const table = [
        header,
        ...rows.map((item) => [
          item.global_id,
          item.created_at,
          adminBonusSourceLabel(item.source),
          item.amount,
          item.reason,
          item.username || "",
          item.admin_global_id || "",
        ]),
      ];
      const day = new Date().toISOString().slice(0, 10);
      const base = `EFHC_bonus_${selectedExportGlobalId}_${day}`;
      if (format === "json") {
        downloadBlob(buildJsonBlobFromTable(table, {
          kind: "efhc_admin_bonus_export",
          generated_at: new Date().toISOString(),
          global_id: selectedExportGlobalId,
          filters: { source, period, date_from: dateBounds.dateFrom, date_to: dateBounds.dateTo },
        }), `${base}.json`);
      } else if (format === "xlsx") {
        downloadBlob(buildSimpleXlsx(table, "Начисления EFHCb"), `${base}.xlsx`);
      } else {
        const csv = table.map((row) => row.map((value) => `"${String(value ?? "").replace(/"/g, '""')}"`).join(",")).join("\n");
        downloadBlob(new Blob([csv], { type: "text/csv;charset=utf-8" }), `${base}.csv`);
      }
    } catch (e: unknown) {
      setLoadMessage(adminUiErrorMessage(e, t));
    } finally {
      setExporting("");
    }
  }

  async function loadMore() {
    if (loadingMore || !serverHasMore || invalidGlobalId || !validGlobalId) return;
    setLoadingMore(true);
    setLoadMessage("");
    try {
      const q = new URLSearchParams(queryString);
      q.set("limit", String(PAGE_SIZE));
      q.set("offset", String(items.length));
      const result = await adminApiRequest<BonusActivity>(
        `${ADMIN_BONUSES_PATH}?${q.toString()}`,
        "GET",
      );
      const nextItems = result.items || [];
      setItems((current) => {
        const seen = new Set(current.map((item) => item.event_key));
        return [...current, ...nextItems.filter((item) => !seen.has(item.event_key))];
      });
      setServerHasMore(Boolean(result.has_more));
      bonusWindow.revealServerPage();
    } catch (e: unknown) {
      setLoadMessage(adminUiErrorMessage(e, t));
    } finally {
      setLoadingMore(false);
    }
  }

  useEffect(() => {
    if (!restored || !selectedGlobalId || userFilter) return;
    setUserFilter(String(selectedGlobalId));
  }, [restored]);

  useEffect(() => {
    void loadFirstPage();
  }, [queryString, invalidGlobalId, refreshNonce]);

  const sourceFilterLabel = source === "all" ? "Все источники" : adminBonusSourceLabel(source);
  const hasActiveResultFilters = source !== "all" || period !== "all";

  return (
    <AdminPage
      title="Аналитика начислений"
      subtitle="Анализ EFHCb по заданиям, рефералам и ручным операциям администратора. Денежные действия выполняются только в разделе «Пользователи»."
      backHref="/admin"
      actions={(
        <>
          <Button
            onClick={() => setRefreshNonce((value) => value + 1)}
            variant="secondary"
          >
            Обновить данные
          </Button>
          <Button
            href={validGlobalId ? `/admin/users?global_id=${encodeURIComponent(userFilterTrimmed)}` : "/admin/users"}
            variant="secondary"
          >
            Операции пользователя
          </Button>
        </>
      )}
      surfaceBadges={[{ label: "Только просмотр", tone: "connected" }]}
    >
      <div
        className="efhc-bonuses-analytics"
        data-admin-selected-global-id={selectedGlobalId || "none"}
        data-admin-bonuses-authority="FRONTEND_v187_COMPACT_BANK_DENSITY"
        data-eam-family="EAM-ADMIN-012"
      >
        <AdminBonusesCompactOverview
          summary={summary}
          visibleSources={visibleSources}
          onToggleSource={(selected) => {
            setVisibleSources((current) => ({
              ...current,
              [selected]: !current[selected],
            }));
          }}
        />

        <AdminSectionCard
          title="Фильтры аналитики"
          subtitle={`Сводка и история: ${periodLabel(period)}. Фильтр истории: ${sourceFilterLabel}.`}
          actions={(
            <Button
              onClick={() => {
                setSource("all");
                setUserFilter("");
                clearGlobalId();
                setPeriod("all");
                setDateFrom("");
                setDateTo("");
              }}
              variant="ghost"
            >
              Сбросить
            </Button>
          )}
        >
          <div className="efhc-bonuses-periods" aria-label="Период аналитики">
            {([
              ["all", "Всё"],
              ["24h", "24 ч"],
              ["7d", "7 д"],
              ["30d", "30 д"],
              ["90d", "90 д"],
              ["custom", "Период"],
            ] as Array<[PeriodPreset, string]>).map(([value, label]) => (
              <Button
                key={value}
                onClick={() => setPeriod(value)}
                variant={period === value ? "primary" : "secondary"}
              >
                {label}
              </Button>
            ))}
          </div>

          <div className="efhc-bonuses-filter-grid">
            <label className="grid gap-1">
              <span className="text-xs opacity-75">Источник истории</span>
              <select
                className="efhc-input"
                value={source}
                onChange={(event) => setSource(event.target.value as SourceFilter)}
              >
                <option value="all">Все источники</option>
                <option value="tasks">За задания</option>
                <option value="referrals">За рефералов</option>
                <option value="manual">Вручную администратором</option>
              </select>
            </label>

            <label className="grid gap-1" data-admin-global-id-search-canon="v435">
              <span className="text-xs opacity-75">Global ID пользователя</span>
              <input
                aria-invalid={invalidGlobalId || undefined}
                className="efhc-input"
                inputMode="numeric"
                maxLength={10}
                value={userFilter}
                placeholder="10 цифр или пусто"
                onChange={(event) => setUserFilter(event.target.value.replace(/\D/g, "").slice(0, 10))}
              />
            </label>

            {period === "custom" ? (
              <>
                <label className="grid gap-1">
                  <span className="text-xs opacity-75">С даты</span>
                  <input
                    className="efhc-input"
                    type="date"
                    value={dateFrom}
                    onChange={(event) => setDateFrom(event.target.value)}
                  />
                </label>
                <label className="grid gap-1">
                  <span className="text-xs opacity-75">По дату</span>
                  <input
                    className="efhc-input"
                    type="date"
                    value={dateTo}
                    onChange={(event) => setDateTo(event.target.value)}
                  />
                </label>
              </>
            ) : null}
          </div>
          {invalidGlobalId ? (
            <div className="efhc-bonuses-filter-error" role="alert">
              Global ID должен содержать ровно 10 цифр.
            </div>
          ) : null}
        </AdminSectionCard>

        <AdminSectionCard
          title="Начисления по Global ID"
          subtitle={validGlobalId
            ? `Точечная история Global ID ${userFilterTrimmed}. Общий список начислений отключён.`
            : "Общий список начислений отключён. Введите Global ID выше, чтобы показать историю конкретного пользователя."}
          data-admin-bonuses-list-mode="global-id-only-v205"
        >
          {validGlobalId ? (
            <div className="mb-3 flex flex-wrap gap-2" data-admin-bonuses-filtered-export="global-id-json-csv-xlsx-v434">
              <Button variant="secondary" disabled={Boolean(exporting) || !selectedExportGlobalId} onClick={() => void exportFilteredRows("json")} data-admin-bonuses-export-scope={selectedExportGlobalId || "fail-closed"}>
                {exporting === "json" ? "Подготовка JSON…" : "Скачать JSON по фильтрам"}
              </Button>
              <Button variant="secondary" disabled={Boolean(exporting) || !selectedExportGlobalId} onClick={() => void exportFilteredRows("csv")} data-admin-bonuses-export-scope={selectedExportGlobalId || "fail-closed"}>
                {exporting === "csv" ? "Подготовка CSV…" : "Скачать CSV по фильтрам"}
              </Button>
              <Button variant="secondary" disabled={Boolean(exporting) || !selectedExportGlobalId} onClick={() => void exportFilteredRows("xlsx")} data-admin-bonuses-export-scope={selectedExportGlobalId || "fail-closed"}>
                {exporting === "xlsx" ? "Подготовка XLSX…" : "Скачать XLSX по фильтрам"}
              </Button>
            </div>
          ) : null}

          {loadMessage ? (
            <TelegramEmptyState
              title="Не удалось загрузить данные"
              detail={loadMessage}
            />
          ) : null}
          {!loading && readError ? (
            <div data-admin-bonuses-state="read-error">
              <TelegramEmptyState
                title="Не удалось загрузить начисления"
                detail={readError}
                actionLabel="Повторить"
                onAction={() => setRefreshNonce((value) => value + 1)}
              />
            </div>
          ) : null}
          {loading ? (
            <div data-admin-bonuses-state="loading">
              <TelegramEmptyState title="Загрузка…" />
            </div>
          ) : null}

          {!loading && !loadMessage && !readError && items.length ? (
            <AdminCompactOperationList
              rows={bonusWindow.visibleItems.map((item) => ({
                id: item.event_key,
                operation: adminBonusSourceLabel(item.source),
                amount: `${formatD8ToHuman(item.amount)} EFHCb`,
                subject: `Global ID ${item.global_id}`,
                time: formatDate(item.created_at),
                action: (
                  <Button
                    href={`/admin/users?global_id=${encodeURIComponent(item.global_id)}`}
                    variant="ghost"
                  >
                    Открыть
                  </Button>
                ),
              }))}
            />
          ) : null}

          {!validGlobalId && !loading && !loadMessage && !readError ? (
            <TelegramEmptyState
              title="Общий список отключён"
              detail="Для просмотра строк укажите точный Global ID. Сводная аналитика выше остаётся доступной без списка."
            />
          ) : null}

          {validGlobalId && !loading && !loadMessage && !readError && !items.length ? (
            <div data-admin-bonuses-state={hasActiveResultFilters ? "filter-empty" : "true-empty"}>
              <TelegramEmptyState
                title={hasActiveResultFilters ? "По выбранным фильтрам начислений нет" : "Начислений у пользователя пока нет"}
                detail={hasActiveResultFilters
                  ? "Измените источник или период для указанного Global ID."
                  : `Для Global ID ${userFilterTrimmed} начисления ещё не зарегистрированы.`}
              />
            </div>
          ) : null}

          {validGlobalId && !loading && !loadMessage && !readError && items.length ? (
            <AdminListExpandControl
              shown={bonusWindow.visibleCount}
              total={bonusWindow.totalCount}
              hasServerMore={serverHasMore}
              loadingMore={loadingMore}
              onExpand={() => {
                if (bonusWindow.hasMore) bonusWindow.expand();
                else if (serverHasMore) void loadMore();
              }}
              onCollapse={bonusWindow.collapse}
            />
          ) : null}
        </AdminSectionCard>
      </div>
    </AdminPage>
  );
}
