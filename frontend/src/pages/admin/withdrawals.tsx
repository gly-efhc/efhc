import { publicRuntimeValue } from "../../lib/public-runtime";
import { useAdminLinkedTransport } from "../../queries/useAdminLinkedTransport";
/* Compatibility marker: Refresh selected case */
/* Compatibility marker: Repair consistency */
import React, { useContext, useEffect, useMemo, useState } from "react";
import { AdminPage } from "../../components/admin/AdminPage";
import { LayoutContext } from "../../components/Layout";
import { AdminCompactOperationList } from "../../components/admin/AdminCompactOperationList";
import { AdminPromptModal } from "../../components/admin/AdminPromptModal";
import { AdminListShell } from "../../components/admin/AdminListShell";
import { AdminListExpandControl, useAdminListWindow } from "../../components/admin/AdminListWindow";
import { AdminWithdrawalsMobileDecisionPanel } from "../../components/admin/AdminWithdrawalsMobileDecisionPanel";
import { AdminWithdrawalsDashboardRuntime } from "../../components/admin/AdminWithdrawalsDashboardRuntime";
import { Button } from "../../components/ui/Button";
import { Modal } from "../../components/ui/Modal";
import {
  adminPath,
  ADMIN_REPORTS_WITHDRAWALS_PATH,
  ADMIN_WITHDRAWALS_PATH,
  ADMIN_WITHDRAWALS_REQUEST_ID_APPROVE_PATH,
  ADMIN_WITHDRAWALS_REQUEST_ID_MARK_PAID_PATH,
  ADMIN_WITHDRAWALS_REQUEST_ID_PAYOUT_RESERVE_PATH,
  ADMIN_WITHDRAWALS_REQUEST_ID_PAYOUT_RESERVATION_PATH,
  ADMIN_WITHDRAW_OUTCOME_PREVIEW_PATH,
  ADMIN_USERS_GLOBAL_ID_PATH,
  type AdminWithdrawPayoutReservation,
  type AdminDomainReportResponse,
  type AdminWithdrawOutcomePreviewResponse,
} from "../../lib/api/generated/adminSeams";
import {
  ensureAdminWithdrawApproveRequest,
  ensureAdminWithdrawPayoutReserveRequest,
  ensureAdminWithdrawRejectRequest,
  parseAdminWithdrawalListResponse,
  parseAdminWithdrawActionResponse,
  parseAdminWithdrawOutcomePreviewResponse,
  parseAdminWithdrawPayoutReservationResponse,
} from "../../lib/api/generated/adminSeamValidators";
import { useT } from "../../hooks/useT";
import { useWalletsMe } from "../../hooks/useWalletsMe";
import { useAdminPageGlobalIdSelection } from "../../hooks/admin/useAdminPageGlobalIdSelection";
import { formatD8ToHuman } from "../../lib/format";
import { buildJsonBlobFromTable, buildSimpleXlsx, downloadBlob } from "../../lib/export/simpleXlsx";
import { parseGlobalId } from "../../types/identity";
import {
  adminWithdrawOutcomeLabel,
  adminWithdrawStatusLabel,
} from "../../lib/humanLabels";
import {
  buildEfhcWithdrawStructuredJettonTx,
  buildEfhcWithdrawTonConnectTx,
  tonConnectWalletSupportsJettonItems,
} from "../../lib/ton/efhc-withdraw-transfer";
import { TelegramEmptyState } from "../../components/ui/telegram/TelegramEmptyState";
import { TelegramInfoBlock } from "../../components/ui/telegram/TelegramInfoBlock";
import { TelegramSectionRow } from "../../components/ui/telegram/TelegramSectionRow";
import { TelegramStatusBadge } from "../../components/ui/telegram/TelegramStatusBadge";
import { adminSafeLoadError, adminUiErrorMessage } from "../../lib/adminError";
import { useWalletProvider } from "../../lib/wallet-provider";
import {
  routePrimaryWalletExecution,
  type PrimaryWalletExecutionReason,
} from "../../lib/wallet-provider/primaryWalletRouting";
import type { DbId } from "../../types/db-id";

type Withdrawal = ReturnType<typeof parseAdminWithdrawalListResponse>[number];

type PendingAction = { kind: "reject" | "manual-paid"; item: Withdrawal };

type WalletPayoutAttempt = {
  requestId: string;
  idempotencyKey: string;
  payoutRef: string;
  walletProvider: string;
  senderWalletAddress: string;
  boc: string | null;
  traceId: string | null;
  confirmedAt: string;
};

const WITHDRAW_PAYOUT_ATTEMPT_STORAGE_KEY =
  "efhc.admin.withdraw.payout-attempt.v401";

function readWalletPayoutAttempts(): Record<string, WalletPayoutAttempt> {
  if (typeof window === "undefined") return {};
  try {
    const raw = JSON.parse(
      window.localStorage.getItem(WITHDRAW_PAYOUT_ATTEMPT_STORAGE_KEY) || "{}",
    );
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return {};
    const out: Record<string, WalletPayoutAttempt> = {};
    for (const [key, value] of Object.entries(raw)) {
      if (!value || typeof value !== "object" || Array.isArray(value)) continue;
      const item = value as Partial<WalletPayoutAttempt>;
      if (String(item.requestId || "") !== String(key)) continue;
      if (!item.idempotencyKey || !item.payoutRef || !item.walletProvider) continue;
      if (!item.senderWalletAddress || !item.confirmedAt) continue;
      out[String(key)] = {
        requestId: String(item.requestId),
        idempotencyKey: String(item.idempotencyKey),
        payoutRef: String(item.payoutRef),
        walletProvider: String(item.walletProvider),
        senderWalletAddress: String(item.senderWalletAddress),
        boc: typeof item.boc === "string" ? item.boc : null,
        traceId: typeof item.traceId === "string" ? item.traceId : null,
        confirmedAt: String(item.confirmedAt),
      };
    }
    return out;
  } catch {
    return {};
  }
}

function writeWalletPayoutAttempts(
  attempts: Record<string, WalletPayoutAttempt>,
) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(
      WITHDRAW_PAYOUT_ATTEMPT_STORAGE_KEY,
      JSON.stringify(attempts),
    );
  } catch {
    // In-memory state remains available for the current page lifetime.
  }
}

function newIdk(prefix: string) {
  const c: any = globalThis.crypto;
  const fallback = `${Date.now()}-${Math.random()}`;
  const uuid = c?.randomUUID ? c.randomUUID() : fallback;
  return `${prefix}:${uuid}`;
}

function withdrawCompactDate(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

type WithdrawalExportFormat = "json" | "csv" | "txt" | "xlsx";

function assertWithdrawalOwnerScope(rows: Withdrawal[], selectedGlobalId: string): Withdrawal[] {
  if (!selectedGlobalId) return rows;
  if (rows.some((item) => String(item.global_id || "").trim() !== selectedGlobalId)) {
    throw new Error("admin_withdrawals_global_id_scope_violation");
  }
  return rows;
}

function withdrawalExportTable(rows: Withdrawal[]): Array<Array<unknown>> {
  return [
    [
      "request_id", "global_id", "amount_efhc", "status", "is_vip", "payout_asset",
      "external_address", "tx_hash", "created_at", "processed_at", "error_message",
      "tonconnect_transport_kind", "jetton_master_address", "jetton_decimals",
      "fee_message_ton_amount",
    ],
    ...rows.map((item) => [
      item.id, item.global_id, item.amount_efhc, item.status, item.is_vip, item.payout_asset,
      item.external_address || "", item.tx_hash || "", item.created_at, item.processed_at || "",
      item.error_message || "", item.tonconnect_transport_kind || "", item.jetton_master_address || "",
      item.jetton_decimals ?? "", item.fee_message_ton_amount || "",
    ]),
  ];
}

function csvCell(value: unknown): string {
  return `"${String(value ?? "").replace(/"/g, '""')}"`;
}

export default function AdminWithdrawalsPage() {
  const adminApiRequest = useAdminLinkedTransport();
  const t = useT();
  const { openWalletConnect } = useContext(LayoutContext);
  const walletsMe = useWalletsMe();
  const { selectedGlobalId, restored, rememberGlobalId, clearGlobalId } =
    useAdminPageGlobalIdSelection("withdrawals");
  const [globalIdInput, setGlobalIdInput] = useState("");
  const [globalIdError, setGlobalIdError] = useState<string | null>(null);
  const [globalIdSearching, setGlobalIdSearching] = useState(false);
  const [exporting, setExporting] = useState<WithdrawalExportFormat | "">("");
  const [exportError, setExportError] = useState<string | null>(null);
  const [items, setItems] = useState<Withdrawal[]>([]);
  const [dashboardItems, setDashboardItems] = useState<Withdrawal[]>([]);
  const [dashboardReport, setDashboardReport] =
    useState<AdminDomainReportResponse | null>(null);
  const [dashboardLoading, setDashboardLoading] = useState(false);
  const [dashboardError, setDashboardError] = useState<string | null>(null);
  const [dashboardUpdatedAt, setDashboardUpdatedAt] = useState<string | null>(
    null,
  );
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<string>("PENDING");
  const [vipOnly, setVipOnly] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<PendingAction | null>(null);
  const {
    activeAdapterId,
    session: walletSession,
    address: walletAddress,
    providerName: walletProviderName,
    listWallets,
    connect: connectWallet,
    disconnect: disconnectWallet,
    sendTransaction,
  } = useWalletProvider();
  const [payingId, setPayingId] = useState<DbId | null>(null);
  const [walletRouteNotice, setWalletRouteNotice] = useState<string | null>(null);
  const [walletPayoutAttempts, setWalletPayoutAttempts] = useState<
    Record<string, WalletPayoutAttempt>
  >(() => readWalletPayoutAttempts());
  const [serverReservedIds, setServerReservedIds] = useState<Record<string, boolean>>({});
  const [decisionOpen, setDecisionOpen] = useState(false);
  const [confirmForm, setConfirmForm] = useState<Record<string, string>>({
    reason: "",
  });
  const [selectedId, setSelectedId] = useState<DbId | null>(null);
  const [previewMode, setPreviewMode] = useState<string>("auto");
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [preview, setPreview] =
    useState<AdminWithdrawOutcomePreviewResponse | null>(null);
  const [repairBusy, setRepairBusy] = useState(false);
  const [repairNote, setRepairNote] = useState<string | null>(null);
  const selectedGlobalIdText = String(selectedGlobalId || "").trim();
  const withdrawalWindow = useAdminListWindow(items, `${selectedGlobalIdText || "all"}:${status}:${vipOnly}`);
  const [withdrawalHasMore, setWithdrawalHasMore] = useState(false);
  const [withdrawalNextOffset, setWithdrawalNextOffset] = useState(20);
  const [withdrawalLoadingMore, setWithdrawalLoadingMore] = useState(false);

  const query = useMemo(() => {
    const q = new URLSearchParams();
    if (selectedGlobalIdText) q.set("global_id", selectedGlobalIdText);
    if (status) q.set("status", status);
    if (vipOnly) q.set("vip_only", "true");
    q.set("limit", "21");
    q.set("offset", "0");
    return q.toString();
  }, [selectedGlobalIdText, status, vipOnly]);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await adminApiRequest<unknown>(
        `${ADMIN_WITHDRAWALS_PATH}?${query}`,
        "GET",
      );
      const rows = assertWithdrawalOwnerScope(
        parseAdminWithdrawalListResponse(res),
        selectedGlobalIdText,
      );
      setItems(rows.slice(0, 20));
      setWithdrawalHasMore(rows.length > 20);
      setWithdrawalNextOffset(20);
      withdrawalWindow.collapse();
    } catch (e: any) {
      setError(adminSafeLoadError(e, t));
    } finally {
      setLoading(false);
    }
  }

  async function loadMoreWithdrawals() {
    if (!withdrawalHasMore || withdrawalLoadingMore) return;
    setWithdrawalLoadingMore(true);
    setError(null);
    try {
      const q = new URLSearchParams();
      if (selectedGlobalIdText) q.set("global_id", selectedGlobalIdText);
      if (status) q.set("status", status);
      if (vipOnly) q.set("vip_only", "true");
      q.set("limit", "21");
      q.set("offset", String(withdrawalNextOffset));
      const raw = await adminApiRequest<unknown>(
        `${ADMIN_WITHDRAWALS_PATH}?${q.toString()}`,
        "GET",
      );
      const page = assertWithdrawalOwnerScope(
        parseAdminWithdrawalListResponse(raw),
        selectedGlobalIdText,
      );
      const nextRows = page.slice(0, 20);
      setItems((current) => {
        const seen = new Set(current.map((item) => String(item.id)));
        return [...current, ...nextRows.filter((item) => !seen.has(String(item.id)))];
      });
      setWithdrawalHasMore(page.length > 20);
      setWithdrawalNextOffset((current) => current + 20);
      withdrawalWindow.revealServerPage();
    } catch (e: any) {
      setError(adminSafeLoadError(e, t));
    } finally {
      setWithdrawalLoadingMore(false);
    }
  }

  async function loadDashboardSnapshots() {
    setDashboardLoading(true);
    setDashboardError(null);
    try {
      const statuses = ["PENDING", "PAID", "REJECTED", "CANCELED"];
      const [batches, report] = await Promise.all([
        Promise.all(
          statuses.map(async (nextStatus) => {
            const q = new URLSearchParams();
            if (selectedGlobalIdText) q.set("global_id", selectedGlobalIdText);
            q.set("status", nextStatus);
            if (vipOnly) q.set("vip_only", "true");
            q.set("limit", "200");
            q.set("offset", "0");
            const raw = await adminApiRequest<unknown>(
              `${ADMIN_WITHDRAWALS_PATH}?${q.toString()}`,
              "GET",
            );
            return assertWithdrawalOwnerScope(
              parseAdminWithdrawalListResponse(raw),
              selectedGlobalIdText,
            );
          }),
        ),
        adminApiRequest<AdminDomainReportResponse>(
          `${ADMIN_REPORTS_WITHDRAWALS_PATH}?range_hours=168&bucket=day`,
          "GET",
        ),
      ]);
      setDashboardItems(batches.flat());
      setDashboardReport(report);
      setDashboardUpdatedAt(report.generated_at || new Date().toISOString());
    } catch (e: any) {
      setDashboardItems([]);
      setDashboardReport(null);
      setDashboardError(adminSafeLoadError(e, t));
    } finally {
      setDashboardLoading(false);
    }
  }

  async function applyGlobalId() {
    let parsed;
    try {
      parsed = parseGlobalId(globalIdInput.trim());
    } catch {
      setGlobalIdError("Global ID должен содержать ровно 10 цифр.");
      return;
    }
    setGlobalIdSearching(true);
    setGlobalIdError(null);
    try {
      const raw = await adminApiRequest<{ global_id?: unknown }>(
        adminPath(ADMIN_USERS_GLOBAL_ID_PATH, { global_id: parsed }),
        "GET",
      );
      const proven = parseGlobalId(String(raw?.global_id || ""));
      if (String(proven) !== String(parsed)) {
        throw new Error("admin_withdrawals_global_id_owner_unproven");
      }
      rememberGlobalId(parsed);
      setGlobalIdInput(String(parsed));
      setSelectedId(null);
      setDecisionOpen(false);
    } catch (e: unknown) {
      setGlobalIdError(adminUiErrorMessage(e, t));
    } finally {
      setGlobalIdSearching(false);
    }
  }

  function resetGlobalId() {
    clearGlobalId();
    setGlobalIdInput("");
    setGlobalIdError(null);
    setExportError(null);
    setSelectedId(null);
    setDecisionOpen(false);
  }

  async function collectWithdrawalJournal(): Promise<Withdrawal[]> {
    const collected: Withdrawal[] = [];
    const seen = new Set<string>();
    let offset = 0;
    const pageSize = 500;
    for (;;) {
      const q = new URLSearchParams({ limit: String(pageSize), offset: String(offset) });
      if (selectedGlobalIdText) q.set("global_id", selectedGlobalIdText);
      const raw = await adminApiRequest<unknown>(
        `${ADMIN_WITHDRAWALS_PATH}?${q.toString()}`,
        "GET",
      );
      const page = assertWithdrawalOwnerScope(
        parseAdminWithdrawalListResponse(raw),
        selectedGlobalIdText,
      );
      let added = 0;
      for (const item of page) {
        const key = String(item.id);
        if (seen.has(key)) continue;
        seen.add(key);
        collected.push(item);
        added += 1;
      }
      if (page.length < pageSize) break;
      if (!added) throw new Error("admin_withdrawals_export_pagination_stalled");
      offset += page.length;
    }
    return collected;
  }

  async function exportWithdrawalJournal(format: WithdrawalExportFormat) {
    if (exporting) return;
    setExporting(format);
    setExportError(null);
    try {
      const rows = await collectWithdrawalJournal();
      const table = withdrawalExportTable(rows);
      const day = new Date().toISOString().slice(0, 10);
      const base = selectedGlobalIdText
        ? `EFHC_withdrawals_global_${selectedGlobalIdText}_${day}`
        : `EFHC_withdrawals_log_${day}`;
      if (format === "json") {
        downloadBlob(buildJsonBlobFromTable(table, {
          kind: "efhc_admin_withdrawals_log",
          generated_at: new Date().toISOString(),
          global_id: selectedGlobalIdText || null,
          statuses: ["PENDING", "PAID", "REJECTED", "CANCELED"],
          source: "GET /admin/withdrawals paginated server scope",
        }), `${base}.json`);
      } else if (format === "xlsx") {
        downloadBlob(buildSimpleXlsx(table, "Выплаты"), `${base}.xlsx`);
      } else if (format === "txt") {
        const body = table.map((row) => row.map((value) => String(value ?? "")).join("\t")).join("\n");
        downloadBlob(new Blob([body], { type: "text/plain;charset=utf-8" }), `${base}.txt`);
      } else {
        const body = table.map((row) => row.map(csvCell).join(",")).join("\n");
        downloadBlob(new Blob([body], { type: "text/csv;charset=utf-8" }), `${base}.csv`);
      }
    } catch (e: unknown) {
      setExportError(adminUiErrorMessage(e, t));
    } finally {
      setExporting("");
    }
  }

  async function loadPreview(item: Withdrawal, mode: string = previewMode) {
    setPreviewLoading(true);
    setPreviewError(null);
    try {
      const path = ADMIN_WITHDRAW_OUTCOME_PREVIEW_PATH.replace(
        "{request_id}",
        String(item.id),
      );
      const raw = await adminApiRequest<unknown>(
        `${path}?mode=${encodeURIComponent(mode)}`,
        "GET",
      );
      setPreview(parseAdminWithdrawOutcomePreviewResponse(raw));
    } catch (e: any) {
      setPreview(null);
      setPreviewError(adminUiErrorMessage(e, t));
    } finally {
      setPreviewLoading(false);
    }
  }

  async function refreshSelectedCase(requestId: DbId | null = selectedId) {
    await load();
    await loadDashboardSnapshots();
    const nextId = requestId ?? null;
    if (nextId !== null) {
      setSelectedId(nextId);
      const current = items.find((item) => item.id === nextId);
      if (current) {
        await loadPreview(current, previewMode);
      }
    }
  }

  async function repairConsistency() {
    setRepairBusy(true);
    setRepairNote(null);
    setError(null);
    try {
      const raw = await adminApiRequest<unknown>(
        `${ADMIN_WITHDRAWALS_PATH}/repair-consistency`,
        "POST",
        {
          idempotencyKey: newIdk("admin-withdraw-repair"),
          body: {},
        },
      );
      const out = raw as {
        ok?: boolean;
        auto_fixed_hold?: number;
        auto_fixed_refund?: number;
      };
      setRepairNote(
        `Проверка завершена: восстановлено удержаний ${String(out.auto_fixed_hold ?? 0)}, ` +
          `возвратов ${String(out.auto_fixed_refund ?? 0)}.`,
      );
      await load();
      if (selected) {
        await loadPreview(selected, previewMode);
      }
    } catch (e: any) {
      setError(adminSafeLoadError(e, t));
    } finally {
      setRepairBusy(false);
    }
  }

  useEffect(() => {
    if (!restored) return;
    void load();
  }, [query, restored]);

  useEffect(() => {
    if (!restored) return;
    void loadDashboardSnapshots();
  }, [vipOnly, restored, selectedGlobalIdText]);

  useEffect(() => {
    if (!restored) return;
    setGlobalIdInput(selectedGlobalIdText);
  }, [restored, selectedGlobalIdText]);

  useEffect(() => {
    if (!items.length) {
      setSelectedId(null);
      setDecisionOpen(false);
      return;
    }
    if (selectedId !== null && !items.some((item) => item.id === selectedId)) {
      setSelectedId(null);
      setDecisionOpen(false);
    }
  }, [items, selectedId]);

  const selectedSummary = pending
    ? [
        `Заявка: №${pending.item.id}`,
        `ID EFHC: ${pending.item.global_id}`,
        `Сумма: ${formatD8ToHuman(pending.item.amount_efhc)} EFHCm`,
        `Кошелёк: ${pending.item.external_address || "—"}`,
        `Статус: ${adminWithdrawStatusLabel(pending.item.status)}`,
      ].join("\n")
    : "";

  const selected = useMemo(
    () => items.find((item) => item.id === selectedId) || null,
    [items, selectedId],
  );

  useEffect(() => {
    if (!selected) {
      setPreview(null);
      return;
    }
    void loadPreview(selected, previewMode);
  }, [selected, previewMode]);

  function rememberWalletPayoutAttempt(attempt: WalletPayoutAttempt) {
    const key = String(attempt.requestId);
    const persisted = { ...readWalletPayoutAttempts(), [key]: attempt };
    // Persist synchronously after confirmed Send, before any React state commit.
    writeWalletPayoutAttempts(persisted);
    setWalletPayoutAttempts((current) => ({ ...current, [key]: attempt }));
  }

  function forgetWalletPayoutAttempt(id: DbId) {
    const key = String(id);
    const persisted = readWalletPayoutAttempts();
    if (persisted[key]) {
      delete persisted[key];
      writeWalletPayoutAttempts(persisted);
    }
    setWalletPayoutAttempts((current) => {
      if (!current[key]) return current;
      const next = { ...current };
      delete next[key];
      return next;
    });
  }

  function walletPayoutAttemptFor(id: DbId): WalletPayoutAttempt | null {
    return walletPayoutAttempts[String(id)] || null;
  }

  function noteServerReservation(id: DbId, reserved: boolean) {
    const key = String(id);
    setServerReservedIds((current) => {
      if (Boolean(current[key]) === reserved) return current;
      const next = { ...current };
      if (reserved) next[key] = true;
      else delete next[key];
      return next;
    });
  }

  async function getServerPayoutReservation(
    item: Withdrawal,
  ): Promise<AdminWithdrawPayoutReservation> {
    const raw = await adminApiRequest<unknown>(
      adminPath(ADMIN_WITHDRAWALS_REQUEST_ID_PAYOUT_RESERVATION_PATH, {
        request_id: item.id,
      }),
      "GET",
    );
    const parsed = parseAdminWithdrawPayoutReservationResponse(raw).result;
    noteServerReservation(item.id, parsed.reserved);
    return parsed;
  }

  async function reserveServerPayoutAttempt(
    item: Withdrawal,
    senderWalletAddress: string,
  ): Promise<AdminWithdrawPayoutReservation> {
    const reserveBody = ensureAdminWithdrawPayoutReserveRequest({
      sender_wallet_address: senderWalletAddress,
      wallet_provider: walletProviderName || null,
    });
    const raw = await adminApiRequest<unknown>(
      adminPath(ADMIN_WITHDRAWALS_REQUEST_ID_PAYOUT_RESERVE_PATH, {
        request_id: item.id,
      }),
      "POST",
      {
        idempotencyKey: newIdk(`admin-withdraw-reserve-${item.id}`),
        body: reserveBody,
      },
    );
    const reservation = parseAdminWithdrawPayoutReservationResponse(raw).result;
    noteServerReservation(item.id, reservation.reserved);
    if (!reservation.reserved || !reservation.idempotency_key || !reservation.payout_ref) {
      throw new Error("WITHDRAWAL_PAYOUT_RESERVATION_INVALID");
    }
    if (!reservation.safe_to_send) {
      throw new Error("WITHDRAWAL_PAYOUT_RECOVERY_REQUIRES_RECONCILIATION");
    }
    if (reservation.sender_wallet_address !== senderWalletAddress) {
      throw new Error("ADMIN_PAYOUT_SENDER_WALLET_MISMATCH");
    }
    if (reservation.recipient_external_address !== item.external_address) {
      throw new Error("WITHDRAWAL_RECIPIENT_AUTHORITY_MISMATCH");
    }
    if (reservation.amount_efhc !== item.amount_efhc) {
      throw new Error("WITHDRAWAL_AMOUNT_AUTHORITY_MISMATCH");
    }
    return reservation;
  }

  function closeDecision() {
    setDecisionOpen(false);
    setWalletRouteNotice(null);
  }

  function openManualPaid(item: Withdrawal) {
    setPending({ kind: "manual-paid", item });
    setConfirmForm({ reason: "" });
  }

  function openReject(item: Withdrawal) {
    setPending({ kind: "reject", item });
    setConfirmForm({ reason: "" });
  }

  async function finalizeConfirmedWalletPayout(
    item: Withdrawal,
    attempt: WalletPayoutAttempt,
  ) {
    const approveBody = ensureAdminWithdrawApproveRequest({
      payout_ref: attempt.payoutRef,
      wallet_send_confirmed: true,
      wallet_provider: attempt.walletProvider,
      sender_wallet_address: attempt.senderWalletAddress,
    });
    const approveOut = await adminApiRequest<unknown>(
      adminPath(ADMIN_WITHDRAWALS_REQUEST_ID_APPROVE_PATH, {
        request_id: item.id,
      }),
      "POST",
      {
        idempotencyKey: attempt.idempotencyKey,
        body: approveBody,
      },
    );
    parseAdminWithdrawActionResponse(approveOut);
    forgetWalletPayoutAttempt(item.id);
    noteServerReservation(item.id, false);
    setWalletRouteNotice(null);
    setDecisionOpen(false);
    setStatus("PAID");
    await load();
    await loadDashboardSnapshots();
  }

  async function executeWalletPayout(
    item: Withdrawal,
    senderWalletAddress: string,
  ) {
    if (!item.external_address) {
      setError("У заявки нет адреса кошелька для выплаты.");
      return;
    }
    setPayingId(item.id);
    setError(null);
    try {
      // Build the exact transaction before acquiring the server reservation.
      // Transaction construction has no wallet-send side effect; this avoids
      // stranding a reservation on an RPC/build failure. The server then
      // revalidates sender/recipient/amount immediately before external Send.
      const canUseWalletBuiltJetton = activeAdapterId === "tonconnect"
        && tonConnectWalletSupportsJettonItems(walletSession?.raw);
      const tx = canUseWalletBuiltJetton
        ? buildEfhcWithdrawStructuredJettonTx({
            senderOwnerAddress: senderWalletAddress,
            recipientOwnerAddress: item.external_address,
            amountEfhc: item.amount_efhc,
            feeMessageTonAmount: item.fee_message_ton_amount || "50000000",
            backendJettonMasterAddress: item.jetton_master_address,
            backendJettonDecimals: item.jetton_decimals,
          })
        : await buildEfhcWithdrawTonConnectTx({
            endpoint:
              publicRuntimeValue("NEXT_PUBLIC_TON_RPC_ENDPOINT")
              || "https://toncenter.com/api/v2/jsonRPC",
            senderOwnerAddress: senderWalletAddress,
            recipientOwnerAddress: item.external_address,
            amountEfhc: item.amount_efhc,
            feeMessageTonAmount: item.fee_message_ton_amount || "50000000",
          });

      // Cycle0199 G-02 boundary: reserve server authority immediately BEFORE
      // external TON Connect Send. Only a newly-created reservation grants
      // safe_to_send=true; recovered reservations never auto-resend. The
      // helper proves the transaction values equal server authority.
      const reservation = await reserveServerPayoutAttempt(
        item,
        senderWalletAddress,
      );
      const transactionResult = await sendTransaction(tx);
      const provider =
        reservation.wallet_provider
        || walletProviderName
        || transactionResult.provider
        || "tonconnect-wallet";
      const attempt: WalletPayoutAttempt = {
        requestId: String(item.id),
        idempotencyKey: reservation.idempotency_key!,
        payoutRef: reservation.payout_ref!,
        walletProvider: provider,
        senderWalletAddress: reservation.sender_wallet_address!,
        boc: transactionResult.boc || null,
        traceId: transactionResult.traceId || null,
        confirmedAt: new Date().toISOString(),
      };
      rememberWalletPayoutAttempt(attempt);
      await finalizeConfirmedWalletPayout(item, attempt);
    } catch (e: any) {
      setError(adminSafeLoadError(e, t));
    } finally {
      setPayingId(null);
    }
  }

  async function payWithWallet(item: Withdrawal) {
    if (payingId === item.id) return;
    setSelectedId(item.id);
    setDecisionOpen(true);
    if (!item.external_address) {
      setError("У заявки нет адреса кошелька для выплаты.");
      return;
    }
    setError(null);
    setWalletRouteNotice(null);

    const confirmedAttempt = walletPayoutAttemptFor(item.id);
    if (confirmedAttempt) {
      setPayingId(item.id);
      try {
        const reservation = await getServerPayoutReservation(item);
        if (
          !reservation.reserved
          || reservation.idempotency_key !== confirmedAttempt.idempotencyKey
          || reservation.payout_ref !== confirmedAttempt.payoutRef
          || reservation.sender_wallet_address !== confirmedAttempt.senderWalletAddress
        ) {
          throw new Error("WITHDRAWAL_CONFIRMED_ATTEMPT_WITHOUT_SERVER_RESERVATION");
        }
        await finalizeConfirmedWalletPayout(item, confirmedAttempt);
      } catch (e: any) {
        setError(adminSafeLoadError(e, t));
      } finally {
        setPayingId(null);
      }
      return;
    }

    try {
      const existingReservation = await getServerPayoutReservation(item);
      if (existingReservation.reserved) {
        setWalletRouteNotice(
          "Для заявки уже существует server-side payout reservation. Повторная отправка через кошелёк заблокирована. Если выплата уже была подтверждена в кошельке, используйте «Оплачено» для ручной фиксации результата.",
        );
        setError("WITHDRAWAL_PAYOUT_RECOVERY_REQUIRES_RECONCILIATION");
        return;
      }
      const routeResult = await routePrimaryWalletExecution({
        wallets: walletsMe.data?.wallets,
        currentSessionAddress: walletAddress,
        listWallets: () => listWallets("tonconnect"),
        connectWallet,
        disconnectWallet,
        markPending: () => undefined,
        openChooser: async (reason: PrimaryWalletExecutionReason) => {
          if (reason === "primary_transport_unavailable") {
            setError(t("wallet.primary_transport_fallback"));
            setWalletRouteNotice(
              "Откройте тот же основной кошелёк через TON Connect, затем вернитесь и повторно нажмите «Оплатить».",
            );
          } else {
            setWalletRouteNotice(
              "Привяжите основной кошелёк через TON Connect, затем вернитесь к заявке и повторно нажмите «Оплатить».",
            );
          }
          openWalletConnect(
            reason === "no_primary" ? "binding" : "execution_fallback",
          );
        },
        execute: async (primary) => {
          await executeWalletPayout(item, primary.wallet_address);
        },
      });
      if (routeResult.state === "primary_opened") {
        setWalletRouteNotice(
          "Основной кошелёк открыт. После возврата повторно нажмите «Оплатить» для этой заявки.",
        );
      }
    } catch (e: any) {
      setError(adminSafeLoadError(e, t));
    }
  }

  async function submitAction() {
    if (!pending) return;
    const item = pending.item;
    const reason = confirmForm.reason.trim();
    if (!reason) return;
    setLoading(true);
    setError(null);
    try {
      if (pending.kind === "manual-paid") {
        const reservation = await getServerPayoutReservation(item);
        const manualIdempotencyKey = reservation.reserved
          ? reservation.idempotency_key
          : newIdk(`admin-withdraw-paid-manual-${item.id}`);
        if (!manualIdempotencyKey) {
          throw new Error("WITHDRAWAL_PAYOUT_RESERVATION_INVALID");
        }
        const paidBody = ensureAdminWithdrawApproveRequest({
          confirmation_mode: "manual",
          reason,
          comment_override: reason,
          comment_auto_translated: false,
        });
        const paidOut = await adminApiRequest<unknown>(
          adminPath(ADMIN_WITHDRAWALS_REQUEST_ID_MARK_PAID_PATH, {
            request_id: item.id,
          }),
          "POST",
          {
            idempotencyKey: manualIdempotencyKey,
            body: paidBody,
          },
        );
        parseAdminWithdrawActionResponse(paidOut);
        forgetWalletPayoutAttempt(item.id);
        noteServerReservation(item.id, false);
        setStatus("PAID");
      } else {
        const rejectBody = ensureAdminWithdrawRejectRequest({
          reason,
          comment_override: reason,
          comment_auto_translated: false,
        });
        const rejectOut = await adminApiRequest<unknown>(
          `${ADMIN_WITHDRAWALS_PATH}/${item.id}/reject`,
          "POST",
          {
            idempotencyKey: newIdk(`admin-withdraw-reject-${item.id}`),
            body: rejectBody,
          },
        );
        parseAdminWithdrawActionResponse(rejectOut);
        forgetWalletPayoutAttempt(item.id);
        noteServerReservation(item.id, false);
        setStatus("REJECTED");
      }
      setPending(null);
      setConfirmForm({ reason: "" });
      setDecisionOpen(false);
      setSelectedId(null);
      await loadDashboardSnapshots();
    } catch (e: any) {
      setError(adminSafeLoadError(e, t));
    } finally {
      setLoading(false);
    }
  }

  return (
    <AdminPage
      title="Очередь заявок для оплаты"
      subtitle={
        "Карточки заявок пользователей на вывод: проверить заявку, выполнить выплату, " +
        "отклонить с возвратом или посмотреть итоговый статус."
      }
      backHref="/admin"
    >
      <AdminWithdrawalsDashboardRuntime
        items={dashboardItems}
        statusSnapshot={dashboardReport?.snapshot ?? null}
        currentItems={items}
        selected={selected}
        activeStatus={status}
        vipOnly={vipOnly}
        loading={dashboardLoading || loading}
        error={dashboardError || error}
        updatedAt={dashboardUpdatedAt || undefined}
        onRefresh={() => {
          void loadDashboardSnapshots();
          void load();
        }}
      />

      <section
        className="efhc-admin-withdrawals-tools-v439"
        data-admin-withdrawals-global-id-log-scope="v439"
        aria-label="Поиск Global ID и экспорт журнала выплат"
      >
        <div
          className="grid grid-cols-2 items-end"
          data-admin-selected-global-id={selectedGlobalId || "none"}
          data-admin-search-geometry="v425-v431"
          data-admin-withdraw-global-search-scope="v439"
          style={{ gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: ".45rem" }}
        >
          <label
            className="efhc-admin-withdrawals-global-id-label-v439 col-span-2"
            htmlFor="adminWithdrawGlobalIdV439"
          >
            Global ID
          </label>
          <input
            id="adminWithdrawGlobalIdV439"
            className="efhc-input col-span-2 w-full"
            inputMode="numeric"
            maxLength={10}
            value={globalIdInput}
            onChange={(event) => {
              setGlobalIdInput(event.target.value.replace(/\D/g, "").slice(0, 10));
              if (globalIdError) setGlobalIdError(null);
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter" && globalIdInput.length === 10) void applyGlobalId();
            }}
            placeholder="Global ID — 10 цифр"
            aria-label="Global ID для всего модуля Выплаты"
            style={{ minHeight: "2.25rem", padding: ".52rem .62rem", borderRadius: ".68rem" }}
          />
          <Button
            className="w-full min-w-0"
            variant="secondary"
            disabled={globalIdSearching || (!globalIdInput && !selectedGlobalId)}
            onClick={resetGlobalId}
            style={{ minHeight: "2.25rem", padding: ".52rem .68rem", borderRadius: ".68rem" }}
          >
            Сбросить
          </Button>
          <Button
            className="w-full min-w-0"
            variant="secondary"
            disabled={globalIdSearching || globalIdInput.length !== 10}
            onClick={() => void applyGlobalId()}
            style={{ minHeight: "2.25rem", padding: ".52rem .68rem", borderRadius: ".68rem" }}
          >
            {globalIdSearching ? "Поиск…" : "Найти"}
          </Button>
        </div>
        <div
          className="efhc-admin-withdrawals-export-v439"
          data-admin-withdrawals-log-export="json-csv-txt-xlsx-v439"
        >
          {(["json", "csv", "txt", "xlsx"] as WithdrawalExportFormat[]).map((format) => (
            <Button
              key={format}
              className="min-w-0 w-full"
              variant="secondary"
              disabled={Boolean(exporting) || !restored}
              onClick={() => void exportWithdrawalJournal(format)}
            >
              {exporting === format ? "…" : format.toUpperCase()}
            </Button>
          ))}
        </div>
        {globalIdError ? <p className="mt-2 text-sm text-red-200">{globalIdError}</p> : null}
        {exportError ? <p className="mt-2 text-sm text-red-200">{exportError}</p> : null}
      </section>

      <AdminWithdrawalsMobileDecisionPanel
        items={items}
        selected={selected}
        selectedId={selectedId}
        status={status}
        vipOnly={vipOnly}
        loading={loading}
        repairBusy={repairBusy}
        repairNote={repairNote}
        previewMode={previewMode}
        previewLoading={previewLoading}
        preview={preview}
        onStatusChange={setStatus}
        onVipOnlyChange={setVipOnly}
        onSelect={(id) => {
          setSelectedId(id);
          setDecisionOpen(true);
        }}
        onRefresh={() => {
          void refreshSelectedCase();
        }}
        onRepair={() => {
          void repairConsistency();
        }}
        onPreviewModeChange={setPreviewMode}
      />

      {error ? (
        <TelegramEmptyState
          title={t("admin.admin_withdraw_error_title")}
          detail={error || undefined}
        />
      ) : null}


      {!loading && items.length === 0 ? (
        <TelegramEmptyState
          title={t("admin.admin_withdraw_empty_title")}
          detail={t("admin.admin_withdraw_empty_detail")}
        />
      ) : null}

      {items.length > 0 ? (
        <AdminListShell
          title="Заявки на выплату"
          subtitle="Нажмите на заявку, чтобы открыть окно решения. Клик по строке не запускает кошелёк."
          actions={
            <label className="efhc-admin-toggle px-3 py-2 text-sm">
              <input
                type="checkbox"
                checked={vipOnly}
                onChange={(e) => setVipOnly(e.target.checked)}
              />
              {t("admin.vip_only")}
            </label>
          }
        >
          <div
            className="efhc-admin-withdrawal-payout-cards"
            data-eam-family="EAM-ADMIN-015"
            data-withdraw-payout-action="open-decision-modal"
          >
            <AdminCompactOperationList
              className="efhc-admin-withdrawal-payout-list"
              rows={withdrawalWindow.visibleItems.map((w) => ({
                id: w.id,
                operation: `#${w.id} · ${adminWithdrawStatusLabel(w.status)}`,
                amount: `${formatD8ToHuman(w.amount_efhc)} EFHCm`,
                subject: `Global ID ${w.global_id}`,
                time: withdrawCompactDate(w.created_at),
                onClick: () => {
                  setSelectedId(w.id);
                  setDecisionOpen(true);
                },
                active: decisionOpen && selectedId === w.id,
                ariaLabel: `Открыть заявку ${w.id}`,
              }))}
            />
          </div>
          <AdminListExpandControl
            shown={withdrawalWindow.visibleCount}
            total={withdrawalWindow.totalCount}
            hasServerMore={withdrawalHasMore}
            loadingMore={withdrawalLoadingMore}
            onExpand={withdrawalHasMore ? () => void loadMoreWithdrawals() : withdrawalWindow.expand}
            onCollapse={withdrawalWindow.collapse}
            className="mt-3"
          />
        </AdminListShell>
      ) : null}

      <Modal
        open={decisionOpen && selected !== null}
        onClose={closeDecision}
        closeDisabled={payingId === selected?.id}
        title={selected ? `Заявка #${selected.id}` : "Заявка на выплату"}
      >
        {selected ? (
          <div className="grid gap-3" data-withdraw-decision-modal="v186">
            <TelegramSectionRow
              compact
              title="ID пользователя EFHC"
              subtitle={`ID EFHC ${selected.global_id}`}
            />
            <TelegramSectionRow
              compact
              title="Сумма к оплате"
              subtitle={`${formatD8ToHuman(selected.amount_efhc)} EFHCm`}
              rightSlot={
                <TelegramStatusBadge
                  label={adminWithdrawStatusLabel(selected.status)}
                  tone="primary"
                />
              }
            />
            <TelegramSectionRow
              compact
              title="Адрес получателя"
              subtitle={selected.external_address || "—"}
            />
            <TelegramSectionRow
              compact
              title="Создано"
              subtitle={selected.created_at}
            />
            <TelegramSectionRow
              compact
              title="Обработано"
              subtitle={selected.processed_at || "—"}
            />
            <TelegramSectionRow
              compact
              title="Хеш транзакции"
              subtitle={selected.tx_hash || "—"}
            />
            <TelegramSectionRow
              compact
              title="Комментарий системы"
              subtitle={selected.error_message || "—"}
            />

            {walletRouteNotice && String(selected.status).toUpperCase() === "PENDING" ? (
              <TelegramInfoBlock
                title="Основной кошелёк"
                description={walletRouteNotice}
              />
            ) : null}

            <div className="flex flex-wrap gap-2">
              <Button
                variant="secondary"
                onClick={() => {
                  void refreshSelectedCase(selected.id);
                }}
                disabled={loading || previewLoading}
              >
                Обновить заявку
              </Button>
            </div>

            <TelegramInfoBlock
              title="Что увидит пользователь"
              description="Предварительный результат."
            >
              <div className="mt-3 space-y-2">
                <div className="flex flex-wrap gap-2">
                  {[
                    ["auto", "Авто"],
                    ["success", "Успех"],
                    ["reject", "Отклонение"],
                  ].map(([key, label]) => (
                    <Button
                      key={key}
                      variant={previewMode === key ? "primary" : "secondary"}
                      onClick={() => setPreviewMode(key)}
                      disabled={previewLoading}
                    >
                      {label}
                    </Button>
                  ))}
                </div>
                {previewError ? (
                  <TelegramEmptyState
                    title="Не удалось показать результат для пользователя"
                    detail={previewError}
                  />
                ) : null}
                {previewLoading ? (
                  <TelegramEmptyState title="Проверяем, что увидит пользователь" />
                ) : null}
                {preview ? (
                  <>
                    <TelegramSectionRow
                      compact
                      title="Результат"
                      subtitle={
                        preview.preview_mode === "auto"
                          ? "Автоматический"
                          : preview.preview_mode === "success"
                            ? "Успешный"
                            : "Отклонение"
                      }
                      rightSlot={
                        <TelegramStatusBadge
                          label={adminWithdrawOutcomeLabel(preview.bundle.outcome_kind)}
                          tone={
                            preview.bundle.outcome_kind === "success"
                              ? "connected"
                              : "warning"
                          }
                        />
                      }
                    />
                    <TelegramSectionRow
                      compact
                      title="Комментарий"
                      subtitle={preview.bundle.comment.text}
                    />
                  </>
                ) : null}
              </div>
            </TelegramInfoBlock>

            {String(selected.status).toUpperCase() === "PENDING" ? (
              <>
                <div className="grid gap-2 sm:grid-cols-2" data-withdraw-primary-actions="v403">
                  <Button
                    onClick={() => void payWithWallet(selected)}
                    disabled={loading || payingId === selected.id}
                  >
                    {payingId === selected.id ? "Оплата…" : "Оплатить"}
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() => openReject(selected)}
                    disabled={
                      loading
                      || Boolean(walletPayoutAttemptFor(selected.id))
                      || Boolean(serverReservedIds[String(selected.id)])
                    }
                  >
                    Отказать
                  </Button>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    variant="secondary"
                    onClick={() => openManualPaid(selected)}
                    disabled={loading}
                  >
                    Оплачено
                  </Button>
                </div>
              </>
            ) : null}
          </div>
        ) : null}
      </Modal>

      <AdminPromptModal
        open={pending !== null}
        title={
          pending?.kind === "manual-paid"
            ? "Подтвердить оплату вручную"
            : "Подтвердить отказ"
        }
        submitLabel={
          pending?.kind === "manual-paid"
            ? "Подтвердить оплату вручную"
            : "Подтвердить отказ"
        }
        fields={[
          { key: "summary", label: "Контекст", type: "textarea" },
          {
            key: "reason",
            label:
              pending?.kind === "manual-paid"
                ? "Причина ручного подтверждения оплаты"
                : t("admin.reject_reason_prompt"),
            type: "textarea",
          },
        ]}
        values={{
          summary: selectedSummary,
          reason: confirmForm.reason,
        }}
        onChange={(key, value) => {
          if (key === "reason") setConfirmForm({ reason: value });
        }}
        onClose={() => setPending(null)}
        onSubmit={() => {
          void submitAction();
        }}
        busy={loading}
        submitDisabled={Boolean(pending && !confirmForm.reason.trim())}
      />
    </AdminPage>
  );
}
