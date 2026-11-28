import React, { useEffect, useState } from "react";

import { AdminPage } from "../../components/admin/AdminPage";
import { AdminSectionCard } from "../../components/admin/AdminSectionCard";
import { Button } from "../../components/ui/Button";
import { TelegramEmptyState } from "../../components/ui/telegram/TelegramEmptyState";
import { useT } from "../../hooks/useT";
import {
  ADMIN_REFERRAL_LOGS_PATH,
  ADMIN_REFERRAL_SUMMARY_PATH,
  type AdminReferralLogItem,
  type AdminReferralLogResponse,
  type AdminReferralSummaryItem,
} from "../../lib/api/generated/adminSeams";
import {
  parseAdminReferralLogResponse,
  parseAdminReferralSummaryResponse,
} from "../../lib/api/generated/adminSeamValidators";
import { adminSafeLoadError } from "../../lib/adminError";
import { buildJsonBlobFromTable, buildSimpleXlsx, downloadBlob } from "../../lib/export/simpleXlsx";
import { useAdminPageGlobalIdSelection } from "../../hooks/admin/useAdminPageGlobalIdSelection";
import { useAdminLinkedTransport } from "../../queries/useAdminLinkedTransport";
import { parseGlobalId, type GlobalId } from "../../types/identity";

type SummaryItem = AdminReferralSummaryItem;
type ReferralLogItem = AdminReferralLogItem;
type ReferralExportFormat = "json" | "csv" | "txt" | "xlsx";

function referralLevelForActive(activeCount: number): number {
  if (activeCount >= 10_000) return 5;
  if (activeCount >= 3_000) return 4;
  if (activeCount >= 1_000) return 3;
  if (activeCount >= 100) return 2;
  if (activeCount >= 10) return 1;
  return 0;
}

function csvCell(value: unknown): string {
  return `"${String(value ?? "").replace(/"/g, '""')}"`;
}

export default function AdminReferralsPage() {
  const adminApiRequest = useAdminLinkedTransport();
  const t = useT();
  const { selectedGlobalId, restored, rememberGlobalId, clearGlobalId } = useAdminPageGlobalIdSelection("referrals");
  const [input, setInput] = useState("");
  const [result, setResult] = useState<SummaryItem | null>(null);
  const [searchedId, setSearchedId] = useState<GlobalId | null>(null);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState<ReferralExportFormat | "">("");
  const [error, setError] = useState<string | null>(null);

  function assertSummaryScope(page: ReturnType<typeof parseAdminReferralSummaryResponse>, globalId: GlobalId) {
    if (page.next_cursor !== null || page.items.length > 1) {
      throw new Error("admin_referrals_selected_summary_scope_violation");
    }
    if (page.items.some((item) => item.inviter_global_id !== globalId)) {
      throw new Error("admin_referrals_selected_summary_owner_mismatch");
    }
  }

  function assertLogScope(page: AdminReferralLogResponse, globalId: GlobalId) {
    if (page.global_id !== globalId) {
      throw new Error("admin_referrals_selected_log_owner_mismatch");
    }
    if (page.items.some((item) => item.inviter_global_id !== globalId)) {
      throw new Error("admin_referrals_selected_log_foreign_row");
    }
  }

  async function requestDetailPage(globalId: GlobalId, cursor: string | null, limit = 200) {
    const params = new URLSearchParams({ global_id: globalId, limit: String(limit) });
    if (cursor) params.set("cursor", cursor);
    const raw = await adminApiRequest<unknown>(
      `${ADMIN_REFERRAL_LOGS_PATH}?${params.toString()}`,
      "GET",
    );
    const page = parseAdminReferralLogResponse(raw);
    assertLogScope(page, globalId);
    return page;
  }

  async function collectAllDetails(globalId: GlobalId): Promise<ReferralLogItem[]> {
    const rows: ReferralLogItem[] = [];
    const seenCursors = new Set<string>();
    let cursor: string | null = null;
    for (;;) {
      const page = await requestDetailPage(globalId, cursor);
      rows.push(...page.items);
      const next = page.next_cursor;
      if (!next) break;
      if (seenCursors.has(next)) throw new Error("admin_referrals_selected_log_cursor_loop");
      seenCursors.add(next);
      cursor = next;
    }
    return rows;
  }

  async function search(rawInput?: string) {
    let globalId: GlobalId;
    try {
      globalId = parseGlobalId(String(rawInput ?? input).trim());
    } catch {
      setResult(null);
      setSearchedId(null);
      setError("Global ID должен содержать ровно 10 цифр.");
      return;
    }

    setLoading(true);
    setError(null);
    setResult(null);
    setSearchedId(globalId);
    try {
      const params = new URLSearchParams({ global_id: globalId, limit: "1" });
      const raw = await adminApiRequest<unknown>(
        `${ADMIN_REFERRAL_SUMMARY_PATH}?${params.toString()}`,
        "GET",
      );
      const page = parseAdminReferralSummaryResponse(raw);
      assertSummaryScope(page, globalId);
      const found = page.items[0] ?? null;
      if (!found) return;
      setResult(found);
      rememberGlobalId(globalId);
    } catch (e: unknown) {
      setError(adminSafeLoadError(e, t));
    } finally {
      setLoading(false);
    }
  }

  async function exportSelected(format: ReferralExportFormat) {
    if (!searchedId || !result || result.inviter_global_id !== searchedId || exporting) return;
    if (String(selectedGlobalId || "") !== searchedId) return;
    setExporting(format);
    setError(null);
    try {
      const rows = await collectAllDetails(searchedId);
      if (rows.some((item) => item.inviter_global_id !== searchedId)) {
        throw new Error("admin_referrals_selected_export_foreign_row");
      }
      const active = Number(result.active_count || 0);
      const inactive = Number(result.inactive_count || 0);
      const table: Array<Array<unknown>> = [
        [
          "row_type",
          "global_id",
          "active_count",
          "inactive_count",
          "invited_total",
          "referral_level",
          "total_bonus_efhcb",
          "invitee_global_id",
          "status",
          "invited_at",
          "activated_at",
          "reward_recorded",
        ],
        [
          "summary",
          searchedId,
          active,
          inactive,
          active + inactive,
          referralLevelForActive(active),
          result.total_bonus_efhc,
          "",
          "",
          "",
          "",
          "",
        ],
        ...rows.map((item) => [
          "detail",
          searchedId,
          "",
          "",
          "",
          "",
          "",
          item.invitee_global_id,
          item.status,
          item.invited_at,
          item.activated_at || "",
          item.reward_recorded ? "yes" : "no",
        ]),
      ];
      const day = new Date().toISOString().slice(0, 10);
      const base = `EFHC_referrals_${searchedId}_${day}`;
      if (format === "json") {
        downloadBlob(buildJsonBlobFromTable(table, {
          kind: "efhc_admin_referrals_selected",
          generated_at: new Date().toISOString(),
          global_id: searchedId,
          scope: "selected_global_id",
        }), `${base}.json`);
      } else if (format === "xlsx") {
        downloadBlob(buildSimpleXlsx(table, "Referrals"), `${base}.xlsx`);
      } else if (format === "txt") {
        const text = table.map((row) => row.map((value) => String(value ?? "")).join("\t")).join("\n");
        downloadBlob(new Blob([text], { type: "text/plain;charset=utf-8" }), `${base}.txt`);
      } else {
        const csv = `\uFEFF${table.map((row) => row.map(csvCell).join(",")).join("\r\n")}`;
        downloadBlob(new Blob([csv], { type: "text/csv;charset=utf-8" }), `${base}.csv`);
      }
    } catch (e: unknown) {
      setError(adminSafeLoadError(e, t));
    } finally {
      setExporting("");
    }
  }

  useEffect(() => {
    if (!restored || !selectedGlobalId) return;
    const remembered = String(selectedGlobalId);
    setInput(remembered);
    void search(remembered);
  }, [restored]);

  function resetSearch() {
    clearGlobalId();
    setInput("");
    setResult(null);
    setSearchedId(null);
    setError(null);
  }

  return (
    <AdminPage
      title={t("admin.referrals")}
      subtitle="Реферальная статистика по Global ID."
      backHref="/admin"
      surfaceBadges={[{ label: "Только просмотр", tone: "connected" }]}
    >
      <div className="space-y-4" data-admin-referrals-surface="global-id-stats-export-v207">
        <AdminSectionCard title="Статистика по Global ID">
          <div className="grid grid-cols-2 items-end" data-admin-selected-global-id={selectedGlobalId || "none"} data-admin-search-geometry="v425-v430" data-admin-global-id-search-canon="v435" style={{ gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: ".45rem" }}>
            <input
              className="efhc-input col-span-2 w-full"
              inputMode="numeric"
              maxLength={10}
              value={input}
              onChange={(event) => setInput(event.target.value.replace(/\D/g, "").slice(0, 10))}
              onKeyDown={(event) => {
                if (event.key === "Enter" && input.length === 10) void search();
              }}
              placeholder="Global ID — 10 цифр"
              aria-label="Global ID для поиска реферальной сводки"
              style={{ minHeight: "2.25rem", padding: ".52rem .62rem", borderRadius: ".68rem" }}
            />
            <Button
              className="w-full min-w-0"
              variant="secondary"
              disabled={loading || (!input && !selectedGlobalId)}
              onClick={resetSearch}
              style={{ minHeight: "2.25rem", padding: ".52rem .68rem", borderRadius: ".68rem" }}
            >
              Сбросить
            </Button>
            <Button
              className="w-full min-w-0"
              variant="secondary"
              disabled={loading || input.length !== 10}
              onClick={() => void search()}
              style={{ minHeight: "2.25rem", padding: ".52rem .68rem", borderRadius: ".68rem" }}
            >
              {loading ? "Поиск…" : "Найти"}
            </Button>
          </div>
        </AdminSectionCard>

        {error ? <TelegramEmptyState title="Не удалось получить реферальную сводку" detail={error} /> : null}

        {searchedId && !loading && !error && !result ? (
          <TelegramEmptyState title={`Для Global ID ${searchedId} реферальная сводка не найдена`} />
        ) : null}

        {result ? (
          <AdminSectionCard title={`Global ID ${result.inviter_global_id}`}>
            <div className="divide-y divide-[color:var(--tg-hint)]/15" data-admin-referrals-search-result="v207">
              <div className="grid gap-1 py-3 sm:grid-cols-[minmax(0,1fr)_auto]"><strong>Пригласил всего</strong><b>{Number(result.active_count || 0) + Number(result.inactive_count || 0)}</b></div>
              <div className="grid gap-1 py-3 sm:grid-cols-[minmax(0,1fr)_auto]"><strong>Реферальный уровень</strong><b><span data-i18n-fixed-token="Lvl">Lvl</span> {referralLevelForActive(Number(result.active_count || 0))}</b></div>
              <div className="grid gap-1 py-3 sm:grid-cols-[minmax(0,1fr)_auto]"><strong>Получил бонусов</strong><b className="tabular-nums">{result.total_bonus_efhc} EFHCb</b></div>
            </div>
            <div className="mt-3 grid grid-cols-4 gap-2" data-admin-referrals-export-strip="equal-width-v451">
              {(["json", "csv", "txt", "xlsx"] as const).map((format) => (
                <Button
                  key={format}
                  className="w-full min-w-0"
                  variant="secondary"
                  disabled={Boolean(exporting) || !searchedId || result.inviter_global_id !== searchedId || String(selectedGlobalId || "") !== searchedId}
                  aria-busy={exporting === format}
                  onClick={() => void exportSelected(format)}
                  data-admin-referrals-single-user-export={`server-scoped-owner-proof-v451-${format}`}
                >
                  {format.toUpperCase()}
                </Button>
              ))}
            </div>
          </AdminSectionCard>
        ) : null}

        {!searchedId && !error ? (
          <TelegramEmptyState title="Введите Global ID" />
        ) : null}
      </div>
    </AdminPage>
  );
}
