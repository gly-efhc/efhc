import React, { useEffect, useMemo, useRef, useState } from "react";

import { adminUiErrorMessage } from "../../lib/adminError";
import {
  adminPath,
  ADMIN_SHOP_NFT_REQUESTS_ORDER_ID_DECISION_PATH,
  ADMIN_SHOP_NFT_REQUESTS_PATH,
  ADMIN_USERS_GLOBAL_ID_PATH,
} from "../../lib/api/generated/adminSeams";
import { buildJsonBlobFromTable, buildSimpleXlsx, downloadBlob } from "../../lib/export/simpleXlsx";
import { useAdminPageGlobalIdSelection } from "../../hooks/admin/useAdminPageGlobalIdSelection";
import { useAdminLinkedTransport } from "../../queries/useAdminLinkedTransport";
import { Button } from "../ui/Button";
import { Modal } from "../ui/Modal";
import { TelegramEmptyState } from "../ui/telegram/TelegramEmptyState";
import { TelegramInfoBlock } from "../ui/telegram/TelegramInfoBlock";
import { TelegramSectionRow } from "../ui/telegram/TelegramSectionRow";
import { AdminSectionCard } from "./AdminSectionCard";
import { AdminListShell } from "./AdminListShell";
import { AdminListExpandControl, useAdminListWindow } from "./AdminListWindow";
import { AdminCompactOperationList } from "./AdminCompactOperationList";
import type { DbId } from "../../types/db-id";
import { GETGEMS_VIP_COLLECTION_URL } from "../../data/getgemsVipNfts";

export type VipNftRequest = {
  id: DbId;
  global_id: string;
  username?: string | null;
  status: string;
  item_code?: string | null;
  item_title?: string | null;
  payment_method?: string | null;
  expected_amount?: string | null;
  tx_hash?: string | null;
  /** Immutable per-order destination when an exact backend supports it. */
  delivery_wallet_address?: string | null;
  /** Forward-compatible payer snapshot; current v174.70 contract does not guarantee it. */
  payer_wallet_address?: string | null;
  created_at?: string | null;
  paid_at?: string | null;
  fulfilled_at?: string | null;
  nft_delivery?: {
    decision?: string;
    reason?: string;
    delivery_tx_hash?: string | null;
    decided_at?: string;
  } | null;
};

type NftRequestPage = {
  items: VipNftRequest[];
  next_cursor?: string | null;
  counts?: {
    total: number;
    waiting: number;
    issued: number;
    rejected: number;
  };
};

type BuyerWalletProfile = {
  global_id: string;
  ton_wallet?: string | null;
};

type StatusFilter = "waiting" | "issued" | "rejected" | "all";
type ExportFormat = "json" | "csv" | "txt" | "xlsx";

const VIP_ISSUANCE_STATUSES = new Set(["PAID_PENDING_MANUAL", "APPROVED", "FULFILLED", "REJECTED"]);
const VIP_NUMBER_REASON_RE = /(?:^|\s)\[VIP_NUMBER:(\d{4})\](?:\s|$)/i;
function issuedVipNumber(item: VipNftRequest | null | undefined): string {
  const direct = String((item as any)?.nft_number || "").trim();
  if (/^(?!0000)\d{4}$/.test(direct)) return direct;
  const reason = String(item?.nft_delivery?.reason || "");
  const match = reason.match(VIP_NUMBER_REASON_RE);
  return match && match[1] !== "0000" ? match[1] : "";
}
function reasonWithVipNumber(reason: string, number: string): string {
  const clean = reason.replace(VIP_NUMBER_REASON_RE, " ").replace(/\s{2,}/g, " ").trim();
  return `${clean} [VIP_NUMBER:${number}]`.trim();
}

function normalizedStatus(item: VipNftRequest): string {
  return String(item.status || "").trim().toUpperCase();
}

function isPaidIssuanceRequest(item: VipNftRequest): boolean {
  return VIP_ISSUANCE_STATUSES.has(normalizedStatus(item));
}

function matchesStatusFilter(item: VipNftRequest, filter: StatusFilter): boolean {
  const status = normalizedStatus(item);
  if (filter === "waiting") return status === "PAID_PENDING_MANUAL";
  if (filter === "issued") return status === "APPROVED" || status === "FULFILLED";
  if (filter === "rejected") return status === "REJECTED";
  return true;
}

function issuanceExportStatus(item: VipNftRequest): string {
  const status = normalizedStatus(item);
  if (status === "PAID_PENDING_MANUAL") return "НЕ ВЫДАНО";
  if (status === "APPROVED" || status === "FULFILLED") return "ВЫДАНО";
  return "ОТКАЗ";
}

function stateLabel(status: string): string {
  if (status === "PAID_PENDING_MANUAL") return "Ожидает выдачи";
  if (status === "APPROVED" || status === "FULFILLED") return "NFT выдан";
  if (status === "REJECTED") return "Заявка отклонена";
  return "Состояние заказа обновлено";
}

function paymentMethodLabel(value?: string | null): string {
  const method = String(value || "").trim().toUpperCase();
  return method === "TON" ? "TON/GRAM" : method;
}

function businessPriceD2(value?: string | null): string {
  const text = String(value || "").trim();
  if (!text) return "—";
  const match = text.match(/^(\d+)(?:\.(\d+))?$/);
  if (!match) return text;
  const fraction = match[2] || "";
  if (fraction.length > 2 && /[1-9]/.test(fraction.slice(2))) return text;
  return `${match[1]}.${fraction.slice(0, 2).padEnd(2, "0")}`;
}

function shortHash(value?: string | null): string {
  if (!value) return "Не указан";
  if (value.length < 18) return value;
  return `${value.slice(0, 8)}…${value.slice(-7)}`;
}

function humanDate(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString();
}

function vipQueueTime(item: VipNftRequest): number {
  const parsed = Date.parse(String(item.paid_at || item.created_at || ""));
  return Number.isFinite(parsed) ? parsed : Number.MAX_SAFE_INTEGER;
}

function sortVipQueueOldestFirst(items: VipNftRequest[]): VipNftRequest[] {
  return [...items].sort((left, right) => {
    const timeDiff = vipQueueTime(left) - vipQueueTime(right);
    if (timeDiff !== 0) return timeDiff;
    return String(left.id).localeCompare(String(right.id), "en", { numeric: true });
  });
}

function requestAgeLabel(item: VipNftRequest): string {
  const since = vipQueueTime(item);
  if (!Number.isFinite(since) || since === Number.MAX_SAFE_INTEGER) return "возраст неизвестен";
  const diff = Math.max(0, Date.now() - since);
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 60) return `ждёт ${Math.max(1, minutes)} мин`;
  const hours = Math.floor(minutes / 60);
  const restMinutes = minutes % 60;
  if (hours < 24) return `ждёт ${hours} ч${restMinutes ? ` ${restMinutes} мин` : ""}`;
  const days = Math.floor(hours / 24);
  const restHours = hours % 24;
  return `ждёт ${days} д${restHours ? ` ${restHours} ч` : ""}`;
}

function csvCell(value: unknown): string {
  const text = String(value ?? "");
  return /[";,\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function csvBlob(rows: Array<Array<unknown>>): Blob {
  const body = `\uFEFF${rows.map((row) => row.map(csvCell).join(";")).join("\r\n")}`;
  return new Blob([body], { type: "text/csv;charset=utf-8" });
}

function normalizedSearch(value: string): string {
  return value.trim().toLowerCase();
}

function matchesSearch(item: VipNftRequest, query: string, linkedWallet = ""): boolean {
  if (!query) return true;
  return String(item.id).toLowerCase().includes(query)
    || String(item.global_id || "").toLowerCase().includes(query)
    || String(item.delivery_wallet_address || "").toLowerCase().includes(query)
    || String(item.payer_wallet_address || "").toLowerCase().includes(query)
    || String(linkedWallet || "").toLowerCase().includes(query);
}

export function AdminVipNftRequestsPanel() {
  const request = useAdminLinkedTransport();
  const { selectedGlobalId, restored, rememberGlobalId, clearGlobalId } = useAdminPageGlobalIdSelection("vip-nft");
  const [filter, setFilter] = useState<StatusFilter>("waiting");
  const [items, setItems] = useState<VipNftRequest[]>([]);
  const [counts, setCounts] = useState({ total: 0, waiting: 0, issued: 0, rejected: 0 });
  const [selectedId, setSelectedId] = useState<DbId | null>(null);
  const [decisionOpen, setDecisionOpen] = useState(false);
  const [reason, setReason] = useState("VIP NFT передан пользователю");
  const [deliveryHash, setDeliveryHash] = useState("");
  const [issuedNumber, setIssuedNumber] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [buyerWallet, setBuyerWallet] = useState("");
  const [buyerWalletLoading, setBuyerWalletLoading] = useState(false);
  const [searchInput, setSearchInput] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [exporting, setExporting] = useState<ExportFormat | "">("");
  const autoOpenNextRef = useRef(false);
  const requestWindow = useAdminListWindow(items, `${filter}|${searchQuery}`);

  const selected = useMemo(
    () => items.find((item) => item.id === selectedId) || null,
    [items, selectedId],
  );
  const orderDeliveryWallet = String(selected?.delivery_wallet_address || "").trim();
  const payerWallet = String(selected?.payer_wallet_address || "").trim();
  const effectiveDeliveryWallet = orderDeliveryWallet || payerWallet || buyerWallet;
  const deliveryWalletSource = orderDeliveryWallet
    ? "order"
    : payerWallet
      ? "payer"
      : "verified-fallback";

  useEffect(() => {
    let active = true;
    const globalId = selected?.global_id;
    setBuyerWallet("");
    if (!globalId) {
      setBuyerWalletLoading(false);
      return () => { active = false; };
    }
    setBuyerWalletLoading(true);
    void request<BuyerWalletProfile>(
      adminPath(ADMIN_USERS_GLOBAL_ID_PATH, { global_id: globalId }),
      "GET",
    ).then((profile) => {
      if (!active) return;
      setBuyerWallet(String(profile.ton_wallet || "").trim());
    }).catch(() => {
      if (!active) return;
      setBuyerWallet("");
    }).finally(() => {
      if (active) setBuyerWalletLoading(false);
    });
    return () => { active = false; };
  }, [request, selected?.global_id]);

  async function fetchAll(status: string, globalId = ""): Promise<{ items: VipNftRequest[]; counts: typeof counts }> {
    const collected: VipNftRequest[] = [];
    const knownIds = new Set<string>();
    const seenCursors = new Set<string>();
    let cursor = "";
    let nextCounts = counts;

    while (true) {
      const params = new URLSearchParams();
      params.set("limit", "200");
      if (status) params.set("status", status);
      if (globalId) params.set("global_id", globalId);
      if (cursor) params.set("cursor", cursor);
      const page = await request<NftRequestPage>(
        `${ADMIN_SHOP_NFT_REQUESTS_PATH}?${params.toString()}`,
        "GET",
      );
      for (const item of page.items || []) {
        const key = String(item.id);
        if (knownIds.has(key)) continue;
        knownIds.add(key);
        collected.push(item);
      }
      if (page.counts) nextCounts = page.counts;
      const next = String(page.next_cursor || "").trim();
      if (!next || seenCursors.has(next)) break;
      seenCursors.add(next);
      cursor = next;
    }

    const issuanceItems = sortVipQueueOldestFirst(collected.filter(isPaidIssuanceRequest));
    const derivedCounts = {
      total: issuanceItems.length,
      waiting: issuanceItems.filter((item) => normalizedStatus(item) === "PAID_PENDING_MANUAL").length,
      issued: issuanceItems.filter((item) => ["APPROVED", "FULFILLED"].includes(normalizedStatus(item))).length,
      rejected: issuanceItems.filter((item) => normalizedStatus(item) === "REJECTED").length,
    };
    return { items: issuanceItems, counts: derivedCounts };
  }

  async function load() {
    setBusy(true);
    setNotice("");
    try {
      const query = normalizedSearch(searchQuery);
      const exactGlobalId = /^\d{10}$/.test(searchQuery.trim()) ? searchQuery.trim() : "";
      const result = await fetchAll("", exactGlobalId);
      const exactOwnerRows = exactGlobalId
        ? result.items.filter((item) => String(item.global_id || "").trim() === exactGlobalId)
        : result.items;
      const linkedWallets = query && !exactGlobalId ? await resolveAuditWallets(result.items, true) : new Map<string, string>();
      const visible = exactGlobalId
        ? exactOwnerRows.filter((item) => matchesStatusFilter(item, filter))
        : query
          ? result.items.filter((item) => matchesSearch(
              item,
              query,
              linkedWallets.get(String(item.global_id || "")) || "",
            ))
          : result.items.filter((item) => matchesStatusFilter(item, filter));
      if (exactGlobalId) rememberGlobalId(exactGlobalId);
      setItems(visible);
      setCounts(exactGlobalId ? {
        total: exactOwnerRows.length,
        waiting: exactOwnerRows.filter((item) => normalizedStatus(item) === "PAID_PENDING_MANUAL").length,
        issued: exactOwnerRows.filter((item) => ["APPROVED", "FULFILLED"].includes(normalizedStatus(item))).length,
        rejected: exactOwnerRows.filter((item) => normalizedStatus(item) === "REJECTED").length,
      } : result.counts);
      requestWindow.collapse();

      if (autoOpenNextRef.current) {
        autoOpenNextRef.current = false;
        const nextWaiting = visible.find((item) => normalizedStatus(item) === "PAID_PENDING_MANUAL") || null;
        if (nextWaiting) {
          setSelectedId(nextWaiting.id);
          setDecisionOpen(true);
          setReason("VIP NFT передан пользователю");
          setDeliveryHash("");
          setIssuedNumber(issuedVipNumber(nextWaiting));
          setNotice("Открыта следующая самая старая заявка на выдачу.");
        } else {
          setSelectedId(null);
          setDecisionOpen(false);
          setNotice("Новых заявок на выдачу VIP NFT нет.");
        }
      } else {
        setSelectedId(null);
        setDecisionOpen(false);
      }
    } catch (caught: unknown) {
      autoOpenNextRef.current = false;
      setNotice(adminUiErrorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (!restored || !selectedGlobalId) return;
    const remembered = String(selectedGlobalId);
    setSearchInput(remembered);
    setSearchQuery(remembered);
  }, [restored]);

  useEffect(() => {
    void load();
  }, [filter, searchQuery]);

  function openDecision(item: VipNftRequest) {
    setSelectedId(item.id);
    setDecisionOpen(true);
    setReason("VIP NFT передан пользователю");
    setDeliveryHash(item.nft_delivery?.delivery_tx_hash || "");
    setIssuedNumber(issuedVipNumber(item));
    setNotice("");
  }

  function closeDecision() {
    setDecisionOpen(false);
    setSelectedId(null);
    setDeliveryHash("");
    setIssuedNumber("");
  }

  async function decide(decision: "issued" | "rejected") {
    if (!selected) return;
    if (decision === "issued" && !effectiveDeliveryWallet) {
      setNotice("Нельзя подтвердить выдачу: криптокошелёк для отправки NFT не определён.");
      return;
    }
    const normalizedIssuedNumber = issuedNumber.trim();
    if (decision === "issued" && !/^(?!0000)\d{4}$/.test(normalizedIssuedNumber)) {
      setNotice("Укажите фактически выданный номер VIP NFT: 0001–9999.");
      return;
    }
    const cleanedReason = reason.trim();
    if (!cleanedReason) {
      setNotice("Укажите понятную причину решения.");
      return;
    }
    setBusy(true);
    setNotice("");
    try {
      const result = await request<{ message?: string }>(
        adminPath(ADMIN_SHOP_NFT_REQUESTS_ORDER_ID_DECISION_PATH, {
          order_id: selected.id,
        }),
        "POST",
        {
          body: {
            decision,
            reason: decision === "issued" ? reasonWithVipNumber(cleanedReason, normalizedIssuedNumber) : cleanedReason,
            delivery_tx_hash: decision === "issued" ? deliveryHash.trim() || null : null,
          },
        },
      );
      setReason("VIP NFT передан пользователю");
      setDeliveryHash("");
      setIssuedNumber("");
      setDecisionOpen(false);
      setSelectedId(null);
      autoOpenNextRef.current = true;
      const effectWillReload = filter !== "waiting" || Boolean(searchQuery);
      setSearchInput("");
      setSearchQuery("");
      setFilter("waiting");
      if (!effectWillReload) await load();
      if (!autoOpenNextRef.current) return;
      setNotice(result.message || "Решение сохранено.");
    } catch (caught: unknown) {
      autoOpenNextRef.current = false;
      setNotice(adminUiErrorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function resolveAuditWallets(rows: VipNftRequest[], includeAllLinked = false): Promise<Map<string, string>> {
    const map = new Map<string, string>();
    const globalIds = [...new Set(rows
      .filter((item) => includeAllLinked
        || (!String(item.delivery_wallet_address || "").trim() && !String(item.payer_wallet_address || "").trim()))
      .map((item) => String(item.global_id || "").trim())
      .filter(Boolean))];

    for (let offset = 0; offset < globalIds.length; offset += 8) {
      const batch = globalIds.slice(offset, offset + 8);
      await Promise.all(batch.map(async (globalId) => {
        try {
          const profile = await request<BuyerWalletProfile>(
            adminPath(ADMIN_USERS_GLOBAL_ID_PATH, { global_id: globalId }),
            "GET",
          );
          map.set(globalId, String(profile.ton_wallet || "").trim());
        } catch {
          map.set(globalId, "");
        }
      }));
    }
    return map;
  }

  async function exportAudit(format: ExportFormat) {
    setExporting(format);
    setNotice("");
    try {
      const scopedGlobalId = /^\d{10}$/.test(String(selectedGlobalId || "")) ? String(selectedGlobalId) : "";
      let exportItems: VipNftRequest[];
      if (scopedGlobalId) {
        const serverStatuses = filter === "waiting"
          ? ["PAID_PENDING_MANUAL"]
          : filter === "issued"
            ? ["APPROVED", "FULFILLED"]
            : filter === "rejected"
              ? ["REJECTED"]
              : [""];
        const pages = await Promise.all(serverStatuses.map((status) => fetchAll(status, scopedGlobalId)));
        const byId = new Map<string, VipNftRequest>();
        for (const page of pages) {
          for (const item of page.items) {
            if (String(item.global_id || "").trim() !== scopedGlobalId) {
              throw new Error("admin_vip_nft_export_scope_violation");
            }
            byId.set(String(item.id), item);
          }
        }
        exportItems = sortVipQueueOldestFirst([...byId.values()]);
      } else {
        exportItems = (await fetchAll("", "")).items;
      }
      const fallbackWallets = await resolveAuditWallets(exportItems);
      const rows: Array<Array<unknown>> = [[
        "order_id",
        "global_id",
        "price_d2",
        "payment_method",
        "delivery_wallet",
        "wallet_source",
        "nft_number",
        "status",
        "created_at",
        "paid_at",
        "fulfilled_at",
        "decided_at",
        "delivery_tx_hash",
        "decision_reason",
      ]];
      for (const item of exportItems) {
        const orderWallet = String(item.delivery_wallet_address || "").trim();
        const exactPayer = String(item.payer_wallet_address || "").trim();
        const linkedWallet = fallbackWallets.get(String(item.global_id || "")) || "";
        const wallet = orderWallet || exactPayer || linkedWallet;
        const walletSource = orderWallet ? "order" : exactPayer ? "payer" : linkedWallet ? "linked-account" : "missing";
        rows.push([
          String(item.id),
          item.global_id,
          businessPriceD2(item.expected_amount),
          paymentMethodLabel(item.payment_method),
          wallet,
          walletSource,
          issuedVipNumber(item),
          issuanceExportStatus(item),
          item.created_at || "",
          item.paid_at || "",
          item.fulfilled_at || "",
          item.nft_delivery?.decided_at || "",
          item.nft_delivery?.delivery_tx_hash || "",
          item.nft_delivery?.reason || "",
        ]);
      }
      const date = new Date().toISOString().slice(0, 10);
      const base = scopedGlobalId ? `efhc-vip-nft-issuance-global-${scopedGlobalId}-${date}` : `efhc-vip-nft-issuance-${date}`;
      if (format === "json") {
        downloadBlob(buildJsonBlobFromTable(rows, {
          kind: "efhc_admin_vip_nft_issuance_export",
          generated_at: new Date().toISOString(),
          global_id: scopedGlobalId || null,
          status_filter: filter,
        }), `${base}.json`);
      } else if (format === "csv") {
        downloadBlob(csvBlob(rows), `${base}.csv`);
      } else if (format === "txt") {
        const body = rows.map((row) => row.map((value) => String(value ?? "")).join("\t")).join("\n");
        downloadBlob(new Blob([body], { type: "text/plain;charset=utf-8" }), `${base}.txt`);
      } else {
        downloadBlob(buildSimpleXlsx(rows, "VIP NFT issuance"), `${base}.xlsx`);
      }
      setNotice(`Журнал выдачи VIP NFT подготовлен: ${exportItems.length} заявок.`);
    } catch (caught: unknown) {
      setNotice(adminUiErrorMessage(caught));
    } finally {
      setExporting("");
    }
  }

  const searchActive = Boolean(normalizedSearch(searchQuery));

  return (
    <div
      className="space-y-[14px]"
      data-admin-vip-nft-requests="shop-orders-v211"
      data-admin-vip-delivery-wallet="order-then-payer-then-linked-fallback"
      data-admin-vip-queue-first="true"
      data-admin-vip-queue-fifo="oldest-first"
      data-admin-vip-decision-ui="payout-style-modal"
      data-admin-vip-page-size="20"
      data-admin-vip-search="global-id-order-id-ton-wallet"
      data-admin-selected-global-id={selectedGlobalId || "none"}
      data-admin-vip-audit-export="json-csv-txt-xlsx-v442"
      data-admin-vip-auto-open-next="true"
      data-admin-vip-unpaid-orders="nonexistent"
      data-admin-vip-waiting-tone="subtle-neon-outline"
      data-admin-vip-search-mode="partial-substring"
    >
      <div
        className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4"
        data-admin-vip-nft-map="v211-top-summary"
        data-admin-vip-summary-position="top-v211"
        data-admin-vip-owner-correction="v354"
      >
        {[
          ["Всего заявок", counts.total],
          ["Ожидают выдачи", counts.waiting],
          ["Выдано", counts.issued],
          ["Отклонено", counts.rejected],
        ].map(([label, value], index) => (
          <div key={String(label)} className="efhc-admin-vip-summary-tile-v354 rounded-xl border p-3" data-owner-violet="true" data-admin-visual-primitive="ADMIN_SUMMARY_KPI" data-eam-family="EAM-ADMIN-017" data-admin-instance={`vip-nft-summary-${["total", "waiting", "issued", "rejected"][index]}`}>
            <div className="text-xs efhc-text-muted">{label}</div>
            <strong className="mt-1 block text-xl tabular-nums">{String(value)}</strong>
          </div>
        ))}
      </div>

      <AdminListShell
        title="Заявки на выдачу VIP NFT"
        actions={
          <Button variant="secondary" disabled={busy} onClick={() => void load()}>
            {busy ? "Обновляем…" : "Обновить заявки"}
          </Button>
        }
      >
        <div className="mb-3 grid w-full min-w-0 grid-cols-2 items-end" data-admin-vip-search-panel="v454-export-line" data-admin-search-geometry="v425-v430" data-admin-global-id-search-canon="v435" style={{ gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: ".45rem" }}>
          <input
            className="efhc-input col-span-2 w-full"
            value={searchInput}
            placeholder="Global ID, ShopOrder ID или TON-кошелёк"
            onChange={(event) => setSearchInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") setSearchQuery(searchInput.trim());
            }}
            aria-label="Поиск заявки VIP NFT по Global ID, ShopOrder ID или TON-кошельку"
            style={{ minHeight: "2.25rem", padding: ".52rem .62rem", borderRadius: ".68rem" }}
          />
          <Button
            className="w-full min-w-0"
            variant="secondary"
            disabled={busy || (!searchInput && !searchQuery && !selectedGlobalId)}
            onClick={() => {
              clearGlobalId();
              setSearchInput("");
              setSearchQuery("");
            }}
            style={{ minHeight: "2.25rem", padding: ".52rem .68rem", borderRadius: ".68rem" }}
          >
            Сбросить
          </Button>
          <Button
            className="w-full min-w-0"
            variant="secondary"
            disabled={busy || !searchInput.trim()}
            onClick={() => setSearchQuery(searchInput.trim())}
            style={{ minHeight: "2.25rem", padding: ".52rem .68rem", borderRadius: ".68rem" }}
          >
            Найти
          </Button>
        </div>

        {searchActive ? (
          <div className="mb-3 text-xs efhc-text-muted">
            Частичный поиск по всем статусам: Global ID, ShopOrder ID или TON-адрес кошелька. Основной FIFO-порядок очереди не изменяется.
          </div>
        ) : null}

        <div className="mb-3 flex flex-wrap gap-2">
          {([
            ["waiting", "Ожидают выдачи"],
            ["issued", "Выдано"],
            ["rejected", "Отклонено"],
            ["all", "Все"],
          ] as Array<[StatusFilter, string]>).map(([key, label]) => (
            <Button
              key={key}
              variant={!searchActive && filter === key ? "primary" : "secondary"}
              disabled={busy}
              onClick={() => {
                closeDecision();
                setSearchInput("");
                setSearchQuery("");
                setFilter(key);
              }}
            >
              {label}
            </Button>
          ))}
        </div>

        <div
          className="efhc-admin-vip-export-v442 mb-3"
          data-admin-vip-audit-download="v442"
          data-admin-vip-export-transport="GET /admin/shop/nft-requests paginated"
        >
          {(["json", "csv", "txt", "xlsx"] as ExportFormat[]).map((format) => (
            <Button
              key={format}
              className="w-full min-w-0"
              variant="secondary"
              disabled={Boolean(exporting) || busy}
              onClick={() => void exportAudit(format)}
              aria-busy={exporting === format}
            >
              {format.toUpperCase()}
            </Button>
          ))}
        </div>

        {items.length ? (
          <div className="space-y-2" data-admin-vip-request-list="fifo-oldest-first-v211">
            <AdminCompactOperationList
              className="efhc-admin-vip-nft-issuance-list"
              rows={requestWindow.visibleItems.map((item) => ({
                id: item.id,
                operation: `#${item.id} · ${stateLabel(item.status)}`,
                amount: `${businessPriceD2(item.expected_amount)}${item.payment_method ? ` ${paymentMethodLabel(item.payment_method)}` : ""}`,
                subject: `Global ID ${item.global_id}${issuedVipNumber(item) ? ` · VIP #${issuedVipNumber(item)}` : ""}`,
                time: `${humanDate(item.paid_at || item.created_at)} · ${requestAgeLabel(item)}`,
                onClick: () => openDecision(item),
                active: decisionOpen && selectedId === item.id,
                ariaLabel: `Открыть заявку VIP NFT ${item.id}`,
                tone: normalizedStatus(item) === "PAID_PENDING_MANUAL" ? "neon" : undefined,
              }))}
            />
            <AdminListExpandControl
              shown={requestWindow.visibleCount}
              total={requestWindow.totalCount}
              hasServerMore={false}
              loadingMore={busy}
              onExpand={requestWindow.expand}
              onCollapse={requestWindow.collapse}
            />
          </div>
        ) : (
          <TelegramEmptyState
            title={searchActive ? "Заявка не найдена" : "Заявок в этом разделе нет"}
            detail={searchActive
              ? "Проверьте Global ID, ShopOrder ID или TON-адрес кошелька и повторите поиск."
              : "Новые оплаченные VIP NFT появятся здесь автоматически."}
          />
        )}
      </AdminListShell>

      <Modal
        open={decisionOpen && selected !== null}
        onClose={closeDecision}
        closeDisabled={busy}
        title={selected ? `Заявка VIP NFT #${selected.id}` : "Заявка VIP NFT"}
      >
        {selected ? (
          <div className="grid gap-3" data-admin-vip-decision-modal="v211">
            <section
              className="rounded-xl border border-[color:var(--tg-hint)]/20 p-4"
              data-admin-vip-wallet-destination="v211"
              data-wallet-source={deliveryWalletSource}
            >
              <div className="text-xs font-medium uppercase tracking-wide efhc-text-muted">Кошелёк выдачи VIP NFT</div>
              <div
                className="mt-2 break-all font-mono text-base font-semibold"
                data-admin-vip-wallet-address="full"
              >
                {buyerWalletLoading && !orderDeliveryWallet && !payerWallet
                  ? "Загружаем привязанный TON-кошелёк аккаунта…"
                  : effectiveDeliveryWallet || "Криптокошелёк назначения не определён"}
              </div>
              <div className="mt-2 text-xs efhc-text-muted">
                Отправляйте NFT только на этот адрес. Это единственный owner-visible wallet в карточке выдачи.
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <Button
                  variant="secondary"
                  disabled={!effectiveDeliveryWallet}
                  onClick={() => {
                    if (!effectiveDeliveryWallet) return;
                    void navigator.clipboard?.writeText(effectiveDeliveryWallet);
                    setNotice("Кошелёк выдачи VIP NFT скопирован.");
                  }}
                >
                  Копировать кошелёк выдачи
                </Button>
              </div>
            </section>

            <TelegramSectionRow compact title="Global ID" subtitle={selected.global_id} />
            <TelegramSectionRow compact title="Пользователь" subtitle={selected.username ? `@${selected.username}` : "Username не указан"} />
            <TelegramSectionRow compact title="Товар" subtitle="EFHC VIP NFT" />
            <TelegramSectionRow
              compact
              title="Цена покупки"
              subtitle={`${businessPriceD2(selected.expected_amount)} ${paymentMethodLabel(selected.payment_method)}`.trim()}
            />
            <TelegramSectionRow compact title="Состояние" subtitle={stateLabel(selected.status)} />
            <TelegramSectionRow compact title="Возраст заявки" subtitle={requestAgeLabel(selected)} />
            <TelegramSectionRow compact title="Платёж" subtitle={shortHash(selected.tx_hash)} />
            <TelegramSectionRow compact title="Оплачено" subtitle={humanDate(selected.paid_at)} />
            <TelegramSectionRow compact title="Создана" subtitle={humanDate(selected.created_at)} />

            <div className="flex flex-wrap gap-2">
              <Button variant="secondary" href={`/admin/users?global_id=${encodeURIComponent(selected.global_id)}`}>
                Открыть пользователя
              </Button>
              <Button variant="secondary" href={GETGEMS_VIP_COLLECTION_URL} target="_blank" rel="noreferrer">
                Открыть коллекцию GetGems
              </Button>
            </div>

            {selected.nft_delivery?.reason || selected.nft_delivery?.delivery_tx_hash || selected.nft_delivery?.decided_at ? (
              <AdminSectionCard title="Аудит решения" subtitle="Сведения о принятом решении.">
                <div className="grid gap-2 md:grid-cols-2" data-admin-vip-terminal-audit="read-only-v211">
                  <TelegramSectionRow compact title="Номер выданного VIP NFT" subtitle={issuedVipNumber(selected) || "Не записан"} />
                  <TelegramSectionRow compact title="Решение администратора" subtitle={selected.nft_delivery?.reason || "—"} />
                  <TelegramSectionRow compact title="Решено" subtitle={humanDate(selected.nft_delivery?.decided_at)} />
                  <TelegramSectionRow compact title="Выполнено" subtitle={humanDate(selected.fulfilled_at)} />
                  <TelegramSectionRow compact title="Tx передачи NFT" subtitle={selected.nft_delivery?.delivery_tx_hash || "Не указан"} />
                </div>
              </AdminSectionCard>
            ) : null}

            {normalizedStatus(selected) === "PAID_PENDING_MANUAL" ? (
              <div className="space-y-3">
                <TelegramInfoBlock title="Порядок выдачи VIP NFT">
                  <div className="space-y-2 text-sm">
                    <p>1. Скопируйте полный кошелёк выдачи в верхней части окна.</p>
                    <p>2. Выберите конкретный EFHC VIP NFT и вручную отправьте его на этот TON-адрес.</p>
                    <p>3. После фактической передачи укажите tx hash, если он доступен, и подтвердите выдачу.</p>
                  </div>
                </TelegramInfoBlock>
                <label className="grid gap-1">
                  <span className="text-sm font-medium">Комментарий администратора</span>
                  <textarea
                    className="efhc-input min-h-24"
                    value={reason}
                    onChange={(event) => setReason(event.target.value)}
                    placeholder="Что сделано или почему заявка отклонена"
                  />
                </label>
                <label className="grid gap-1">
                  <span className="text-sm font-medium">Номер выданного VIP NFT</span>
                  <input
                    className="efhc-input font-mono"
                    value={issuedNumber}
                    onChange={(event) => setIssuedNumber(event.target.value.replace(/\D/g, "").slice(0, 4))}
                    inputMode="numeric"
                    maxLength={4}
                    placeholder="0001–9999"
                    data-admin-vip-issued-number-input="true"
                  />
                  <small className="text-xs efhc-text-muted">Номер записывается в серверный audit reason существующего decision-contract. Ownership/Global ID остаётся автоматически определяемым ownership checker по фактическому NFT в verified wallet.</small>
                </label>
                <label className="grid gap-1">
                  <span className="text-sm font-medium">Подтверждение передачи NFT</span>
                  <input
                    className="efhc-input"
                    value={deliveryHash}
                    onChange={(event) => setDeliveryHash(event.target.value)}
                    placeholder="Хэш передачи NFT, если он есть"
                  />
                </label>
                <div className="flex flex-wrap gap-2">
                  <Button disabled={busy || buyerWalletLoading || !effectiveDeliveryWallet} onClick={() => void decide("issued")}>
                    Подтвердить выдачу NFT
                  </Button>
                  <Button variant="secondary" disabled={busy} onClick={() => void decide("rejected")}>
                    Отклонить заявку
                  </Button>
                  <Button variant="ghost" disabled={busy} onClick={closeDecision}>
                    Закрыть без решения
                  </Button>
                </div>
                <TelegramInfoBlock title="После решения">
                  <p className="text-sm">Если в очереди есть ещё заявки, автоматически откроется следующая самая старая. Её можно просто закрыть без решения.</p>
                </TelegramInfoBlock>
                <TelegramInfoBlock title="Важно">
                  <p className="text-sm">Отклонение не выполняет автоматический возврат. Спорные случаи решаются вручную через существующую поддержку.</p>
                </TelegramInfoBlock>
              </div>
            ) : (
              <TelegramInfoBlock title="Решение уже принято">
                <p className="text-sm">{stateLabel(selected.status)}. Номер: {issuedVipNumber(selected) || "не записан"}. Фактический владелец номера определяется автоматически ownership checker. Исправление terminal audit-number в production требует отдельного подтверждённого backend audit-update contract; текущий decision endpoint после выдачи не переиспользуется.</p>
              </TelegramInfoBlock>
            )}
          </div>
        ) : null}
      </Modal>

      {notice ? (
        <TelegramInfoBlock title="Результат действия">
          <p className="text-sm">{notice}</p>
        </TelegramInfoBlock>
      ) : null}
    </div>
  );
}
