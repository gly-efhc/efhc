import React, { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/router";

import { AdminPage } from "../../components/admin/AdminPage";
import { AdminCompactOperationList } from "../../components/admin/AdminCompactOperationList";
import { AdminListExpandControl, useAdminListWindow } from "../../components/admin/AdminListWindow";
import { AdminPromptModal } from "../../components/admin/AdminPromptModal";
import { AdminSectionCard } from "../../components/admin/AdminSectionCard";
import { AdminSettingsCard } from "../../components/admin/AdminSettingsCard";
import { Button } from "../../components/ui/Button";
import { Modal } from "../../components/ui/Modal";
import { useT } from "../../hooks/useT";
import { newIdempotencyKey } from "../../lib/idempotency";
import { TelegramEmptyState } from "../../components/ui/telegram/TelegramEmptyState";
import { TelegramSectionRow } from "../../components/ui/telegram/TelegramSectionRow";
import { TelegramStatusBadge } from "../../components/ui/telegram/TelegramStatusBadge";
import {
  adminPath,
  ADMIN_SHOP_ORDERS_PATH,
  ADMIN_SHOP_ORDERS_STATUS_COUNTERS_PATH,
  ADMIN_SHOP_ORDERS_USER_GLOBAL_ID_PATH,
  ADMIN_SHOP_ORDERS_ORDER_ID_FORCE_FULFILL_PATH,
  ADMIN_SHOP_ITEMS_PATH,
  ADMIN_SHOP_ORDER_ORDER_ID_PATH,
  ADMIN_SHOP_ITEMS_UPSERT_PATH,
  ADMIN_SHOP_ITEMS_STATUS_PATH,
  ADMIN_USERS_RESOLVE_PROVIDER_PATH,
} from "../../lib/api/generated/adminSeams";
import { adminUiErrorMessage } from "../../lib/adminError";
import { useAdminPageGlobalIdSelection } from "../../hooks/admin/useAdminPageGlobalIdSelection";
import { useAdminLinkedTransport } from "../../queries/useAdminLinkedTransport";
import { dbIdFromApi, type DbId } from "../../types/db-id";
import { buildJsonBlobFromTable, buildSimpleXlsx, downloadBlob } from "../../lib/export/simpleXlsx";
import type { AdminLogExportFormat, AdminLogExportRows } from "../../services/adminLogExport.service";

type AdminOrdersResponse = {
  items?: Array<Record<string, unknown>>;
  next_cursor?: string | null;
};

type CatalogItem = {
  id?: DbId;
  sku: string;
  code?: string;
  title: string;
  description: string | null;
  translations?: Record<string, { title?: string; description?: string }>;
  item_type: string;
  active?: boolean;
  is_active?: boolean;
  status?: string;
  quantity_efhc?: string;
  image_url?: string;
  price_efhc?: string;
  price_ton?: string;
  price_usdt?: string;
  pay_currencies?: string[];
  category?: string;
  badge?: string;
  action_mode?: string;
  external_url?: string;
  delivery_mode?: string;
  sort_order?: number;
  created_at?: string | null;
  updated_at?: string | null;
  history_count?: number;
  history_tail?: Array<Record<string, unknown>>;
  owner_global_id?: string | null;
  vip_owner_global_id?: string | null;
  delivery_wallet_address?: string | null;
  methods: Record<string, { price?: string }> | null;
};

type AdminOrder = {
  order_id: DbId;
  global_id?: string | null;
  status: string;
  type: string;
  item_code?: string | null;
  item_title?: string | null;
  payment_method?: string | null;
  quantity_efhc?: string | null;
  expected_amount?: string | null;
  tx_hash?: string | null;
  memo?: string | null;
  payment_error_log?: string | null;
  fulfillment_state?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  paid_at?: string | null;
  fulfilled_at?: string | null;
};

type ShopEditorState = {
  code: string;
  price_efhc: string;
  price_ton: string;
  price_usdt: string;
  pay_currencies: string[];
  category: string;
  badge: string;
  action_mode: string;
  external_url: string;
  delivery_mode: string;
  sort_order: string;
  is_active: boolean;
  status: string;
  title: string;
  description: string;
  translations: Record<string, { title?: string; description?: string }>;
  image_url: string;
  item_type: string;
  quantity_efhc: string;
  vip_selected_price_efhc: string;
  vip_selected_price_ton: string;
  vip_selected_price_usdt: string;
  vip_available_numbers: string;
  vip_unavailable_numbers: string;
};

const FIXED_EFHC_PACKAGE_QUANTITIES = ["10", "50", "100", "150", "200", "250", "300", "350", "500", "750", "1000", "1500", "2000", "2500", "3000"] as const;
const FIXED_EFHC_PACKAGE_QUANTITY_SET = new Set<string>(FIXED_EFHC_PACKAGE_QUANTITIES);
const FIXED_EFHC_PACKAGE_CODE_SET = new Set<string>(FIXED_EFHC_PACKAGE_QUANTITIES.map((quantity) => `EFHC_PACKAGE_${quantity}`));
const CUSTOM_EFHC_PACKAGE_CODE = "EFHC_PACKAGE_CUSTOM";
const CUSTOM_EFHC_PACKAGE_TITLE = "Обмен EFHCm";
const VIP_SELECTED_PRICE_SUFFIX = "_SELECTED_PRICE";
const VIP_NUMBER_MARKER = "_NUMBER_";

const VIP_FIXED_IMAGE_URL = "/assets/efhc/efhc_vip_nft_0000.jpg";
function fixedPackageImage(quantity: string): string {
  return ["10", "100", "250", "500", "750", "1000"].includes(quantity)
    ? `/assets/efhc/shop/efhc-package-${quantity}.svg`
    : "/assets/efhc/efhc_coin_256.png";
}

function canonicalWholeEfhc(value: unknown): string | null {
  const text = String(value ?? "").trim();
  const match = text.match(/^(\d+)(?:\.(\d{1,8}))?$/);
  if (!match) return null;
  if (match[2] && /[1-9]/.test(match[2])) return null;
  return match[1].replace(/^0+(?=\d)/, "");
}

const EDITOR_DEFAULT: ShopEditorState = {
  code: "",
  price_efhc: "",
  price_ton: "",
  price_usdt: "",
  pay_currencies: ["TON", "USDT"],
  category: "efhc",
  badge: "",
  action_mode: "checkout",
  external_url: "",
  delivery_mode: "bank_credit",
  sort_order: "0",
  is_active: true,
  status: "draft",
  title: "",
  description: "",
  translations: {},
  image_url: "",
  item_type: "EFHC_PACKAGE",
  quantity_efhc: "",
  vip_selected_price_efhc: "",
  vip_selected_price_ton: "",
  vip_selected_price_usdt: "",
  vip_available_numbers: "",
  vip_unavailable_numbers: "",
};

function isD2PriceInput(value: string): boolean {
  return /^\d*(?:[.,]\d{0,2})?$/.test(value);
}

function isD8PriceInput(value: string): boolean {
  return /^\d*(?:[.,]\d{0,8})?$/.test(value);
}

function catalogCode(item: CatalogItem): string {
  return String(item.code || item.sku || "").trim();
}

function fixedPackageOwnerSlot(item: CatalogItem): string | null {
  const code = catalogCode(item).toUpperCase();
  if (FIXED_EFHC_PACKAGE_CODE_SET.has(code)) return code.replace(/^EFHC_PACKAGE_/, "");
  const quantity = canonicalWholeEfhc(item.quantity_efhc);
  return quantity && FIXED_EFHC_PACKAGE_QUANTITY_SET.has(quantity) ? quantity : null;
}

function ownerShopCatalogPositions(catalog: CatalogItem[]): CatalogItem[] {
  const packages = FIXED_EFHC_PACKAGE_QUANTITIES.map((slot) => {
    const stableCode = `EFHC_PACKAGE_${slot}`;
    const existing = catalog.find((item) => String(item.item_type || "").trim().toUpperCase() === "EFHC_PACKAGE" && fixedPackageOwnerSlot(item) === slot);
    if (existing) return { ...existing, title: `${slot} EFHCm` };
    return {
      sku: stableCode, code: stableCode, title: `${slot} EFHCm`, description: null, item_type: "EFHC_PACKAGE",
      is_active: false, status: "hidden", quantity_efhc: `${slot}.00000000`, image_url: fixedPackageImage(slot),
      price_efhc: "", price_ton: "", price_usdt: "", pay_currencies: ["TON", "USDT"],
      category: "efhc", badge: "", action_mode: "checkout", external_url: "", delivery_mode: "bank_credit",
      sort_order: Number(slot), methods: null,
    } satisfies CatalogItem;
  });
  const customExisting = catalog.find((item) => String(item.item_type || "").trim().toUpperCase() === "EFHC_PACKAGE" && catalogCode(item).toUpperCase() === CUSTOM_EFHC_PACKAGE_CODE);
  const custom = customExisting ? { ...customExisting, title: CUSTOM_EFHC_PACKAGE_TITLE } : ({
    sku: CUSTOM_EFHC_PACKAGE_CODE, code: CUSTOM_EFHC_PACKAGE_CODE, title: CUSTOM_EFHC_PACKAGE_TITLE,
    description: "Ручной выбор количества EFHCm по курсу за 1 EFHCm.", item_type: "EFHC_PACKAGE",
    is_active: false, status: "hidden", quantity_efhc: undefined, image_url: "/assets/efhc/efhc_coin_256.png",
    price_efhc: "", price_ton: "", price_usdt: "", pay_currencies: ["TON", "USDT"], category: "efhc", badge: "",
    action_mode: "checkout", external_url: "", delivery_mode: "bank_credit", sort_order: 4000, methods: null,
  } satisfies CatalogItem);
  const vip = catalog.find((item) => String(item.item_type || "").trim().toUpperCase() === "NFT_VIP") || ({
    sku: "EFHC_VIP_NFT_ANY", code: "EFHC_VIP_NFT_ANY", title: "EFHC VIP NFT", description: null, item_type: "NFT_VIP",
    is_active: false, status: "hidden", quantity_efhc: undefined, image_url: VIP_FIXED_IMAGE_URL,
    price_efhc: "", price_ton: "", price_usdt: "",
    pay_currencies: ["TON", "USDT", "EFHC"], category: "vip", badge: "", action_mode: "checkout", external_url: "",
    delivery_mode: "manual", sort_order: 5000, methods: null,
  } satisfies CatalogItem);
  return [...packages, custom, vip];
}

function parseVipNumbers(value: string): { numbers: string[]; invalid: string[] } {
  const tokens = value.split(/[\s,;]+/).map((token) => token.trim()).filter(Boolean);
  const invalid = tokens.filter((token) => !/^\d{4}$/.test(token) || token === "0000");
  const numbers = Array.from(new Set(tokens.filter((token) => /^\d{4}$/.test(token) && token !== "0000"))).sort();
  return { numbers, invalid };
}

function vipNumberFromCatalog(item: CatalogItem, baseCode: string): string {
  const code = catalogCode(item);
  const prefix = `${baseCode}${VIP_NUMBER_MARKER}`;
  const number = code.startsWith(prefix) ? code.slice(prefix.length) : "";
  return /^\d{4}$/.test(number) && number !== "0000" ? number : "";
}

function isOwnedVipNumberItem(item: CatalogItem): boolean {
  const status = statusOf(item).toLowerCase();
  return Boolean(String(item.owner_global_id || item.vip_owner_global_id || "").trim())
    || ["sold", "owned", "issued"].includes(status);
}

function formatUnknown(value: unknown): string {
  if (value == null) return "—";
  if (typeof value === "string") return value;
  if (typeof value === "number") return String(value);
  if (typeof value === "boolean") return value ? "true" : "false";
  return JSON.stringify(value);
}

function statusOf(item: CatalogItem): string {
  return item.status || ((item.active ?? item.is_active) ? "live" : "hidden");
}

function isPaidShopOrderRecord(row: Record<string, unknown>): boolean {
  const status = String(row.status || "").trim().toUpperCase();
  return !["", "PENDING", "UNPAID", "CREATED"].includes(status);
}

function isExactGlobalId(value: string): boolean {
  return /^\d{10}$/.test(value.trim());
}

function csvCell(value: unknown): string {
  const text = String(value ?? "");
  return /[";,\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function csvBlob(rows: Array<Array<unknown>>): Blob {
  return new Blob([`\uFEFF${rows.map((row) => row.map(csvCell).join(";")).join("\r\n")}`], { type: "text/csv;charset=utf-8" });
}


function toEditor(item: CatalogItem): ShopEditorState {
  return {
    code: item.code || item.sku,
    title: item.title,
    description: item.description || "",
    translations: item.translations || {},
    item_type: item.item_type || "EFHC_PACKAGE",
    quantity_efhc: item.quantity_efhc || "",
    image_url: item.image_url || "",
    price_efhc: item.price_efhc || item.methods?.EFHC?.price || "",
    price_ton: item.price_ton || item.methods?.TON?.price || "",
    price_usdt: item.price_usdt || item.methods?.USDT?.price || "",
    pay_currencies: item.pay_currencies || Object.keys(item.methods || {}),
    category: item.category || "other",
    badge: item.badge || "",
    action_mode: item.action_mode || "checkout",
    external_url: item.external_url || "",
    delivery_mode: item.delivery_mode || "manual",
    sort_order: String(item.sort_order || 0),
    status: statusOf(item),
    is_active: statusOf(item) === "live",
    vip_selected_price_efhc: "",
    vip_selected_price_ton: "",
    vip_selected_price_usdt: "",
    vip_available_numbers: "",
    vip_unavailable_numbers: "",
  };
}

export default function AdminShopPage() {
  const router = useRouter();
  const [copyLocale, setCopyLocale] = useState("en");
  const adminApiRequest = useAdminLinkedTransport();
  const { selectedGlobalId, restored, rememberGlobalId, clearGlobalId } = useAdminPageGlobalIdSelection("shop");
  const t = useT();
  const [orders, setOrders] = useState<Array<Record<string, unknown>>>([]);
  const [ordersCursor, setOrdersCursor] = useState<string | null>(null);
  const [ordersLoadingMore, setOrdersLoadingMore] = useState(false);
  const [ordersExportRows, setOrdersExportRows] = useState<AdminLogExportRows>("100000");
  const [ordersExporting, setOrdersExporting] = useState<AdminLogExportFormat | null>(null);
  const [orderCounters, setOrderCounters] = useState<{
    total: number;
    pending: number;
    paid_auto: number;
    pending_manual: number;
    approved: number;
    rejected: number;
    cancelled: number;
  } | null>(null);
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [selectedOrder, setSelectedOrder] = useState<AdminOrder | null>(null);
  const [selectedUserOrders, setSelectedUserOrders] = useState<AdminOrder[]>([]);
  const [searchedGlobalId, setSearchedGlobalId] = useState("");
  const [userSearchState, setUserSearchState] = useState<"idle" | "invalid" | "loading" | "found" | "empty" | "error">("idle");
  const [userOrdersExporting, setUserOrdersExporting] = useState<AdminLogExportFormat | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [fulfillModalOpen, setFulfillModalOpen] = useState(false);
  const [fulfillForm, setFulfillForm] = useState({ order_id: "", reason: "Ручное завершение подтверждённого заказа" });
  const [orderSearchInput, setOrderSearchInput] = useState("");

  const [selectedSku, setSelectedSku] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState("catalog");
  const [editorOpen, setEditorOpen] = useState(false);
  const [editor, setEditor] = useState<ShopEditorState>(EDITOR_DEFAULT);
  const [vipMapFilter, setVipMapFilter] = useState<"all" | "available" | "unavailable" | "occupied" | "not-listed">("all");
  const [vipMapSearch, setVipMapSearch] = useState("");
  const [vipMapPage, setVipMapPage] = useState(0);
  async function loadOrders(nextCursor?: string | null) {
    const append = Boolean(nextCursor);
    if (append) setOrdersLoadingMore(true);
    else setLoading(true);
    setMessage(null);
    try {
      // The backend feed can contain PaymentIntent/unpaid legacy records. Filtering
      // after a single raw 20-row page would expose fewer than 20 paid ShopOrders
      // and would violate the owner-approved paid-only 20+20 operational window.
      const rows: Record<string, unknown>[] = [];
      const seenCursors = new Set<string>();
      let cursor = String(nextCursor || "").trim();
      let next: string | null = null;
      while (rows.length < 20) {
        const params = new URLSearchParams({ limit: String(Math.max(1, 20 - rows.length)) });
        if (cursor) params.set("cursor", cursor);
        const res = await adminApiRequest<AdminOrdersResponse>(
          `${ADMIN_SHOP_ORDERS_PATH}?${params.toString()}`,
          "GET",
        );
        rows.push(...(Array.isArray(res.items) ? res.items : []).filter(isPaidShopOrderRecord));
        next = String(res.next_cursor || "").trim() || null;
        if (!next || seenCursors.has(next)) break;
        seenCursors.add(next);
        cursor = next;
      }
      setOrders((current) => {
        if (!append) return rows;
        const key = (row: Record<string, unknown>) => String(row.order_id ?? row.id ?? "");
        const seen = new Set(current.map(key));
        return [...current, ...rows.filter((row) => !seen.has(key(row)))];
      });
      setOrdersCursor(next);
      if (append) ordersWindow.revealServerPage();
    } catch (e: any) {
      setMessage(adminUiErrorMessage(e, t));
    } finally {
      if (append) setOrdersLoadingMore(false);
      else setLoading(false);
    }
  }

  async function exportPaidOrders(format: AdminLogExportFormat) {
    if (ordersExporting) return;
    setOrdersExporting(format);
    setMessage(null);
    try {
      const requested = ordersExportRows === "all" ? Number.MAX_SAFE_INTEGER : Number(ordersExportRows);
      const scopedGlobalId = /^\d{10}$/.test(String(selectedGlobalId || "")) ? String(selectedGlobalId) : "";
      const table: Array<Array<unknown>> = [["ShopOrder ID", "Global ID", "Товар", "Тип", "Статус", "Способ оплаты", "Сумма", "Хэш транзакции", "Создан", "Оплачен", "Выполнен"]];
      const seen = new Set<string>();
      let cursor = "";
      let collected = 0;
      while (collected < requested) {
        const params = new URLSearchParams({ limit: "200" });
        if (scopedGlobalId) params.set("global_id", scopedGlobalId);
        if (cursor) params.set("cursor", cursor);
        const page = await adminApiRequest<AdminOrdersResponse>(`${ADMIN_SHOP_ORDERS_PATH}?${params.toString()}`, "GET");
        for (const row of (page.items || []).filter(isPaidShopOrderRecord)) {
          if (scopedGlobalId && String(row.global_id || "").trim() !== scopedGlobalId) {
            throw new Error("admin_shop_export_scope_violation");
          }
          if (collected >= requested) break;
          table.push([row.order_id ?? row.id ?? "", row.global_id ?? "", row.item_code ?? row.sku ?? "", row.type ?? "", row.status ?? "", row.payment_method ?? "", row.expected_amount ?? row.quantity_efhc ?? "", row.tx_hash ?? "", row.created_at ?? "", row.paid_at ?? "", row.fulfilled_at ?? ""]);
          collected += 1;
        }
        const next = String(page.next_cursor || "").trim();
        if (!next || seen.has(next)) break;
        seen.add(next);
        cursor = next;
      }
      const date = new Date().toISOString().slice(0, 10);
      const base = scopedGlobalId ? `efhc-shop-orders-global-${scopedGlobalId}-${date}` : `efhc-shop-orders-${date}`;
      if (format === "json") {
        downloadBlob(buildJsonBlobFromTable(table, {
          kind: "efhc_admin_shop_orders_export",
          generated_at: new Date().toISOString(),
          global_id: scopedGlobalId || null,
          rows: ordersExportRows,
          paid_only: true,
        }), `${base}.json`);
      } else if (format === "csv") downloadBlob(csvBlob(table), `${base}.csv`);
      else downloadBlob(buildSimpleXlsx(table, "Shop orders"), `${base}.xlsx`);
      setMessage(`Журнал оплаченных заказов подготовлен: ${collected.toLocaleString("ru-RU")} записей.`);
    } catch (e: any) {
      setMessage(adminUiErrorMessage(e, t));
    } finally {
      setOrdersExporting(null);
    }
  }


  async function loadOrderCounters() {
    try {
      const res = await adminApiRequest<{
        total: number;
        pending: number;
        paid_auto: number;
        pending_manual: number;
        approved: number;
        rejected: number;
        cancelled: number;
      }>(ADMIN_SHOP_ORDERS_STATUS_COUNTERS_PATH, "GET");
      setOrderCounters(res);
    } catch (e: any) {
      setMessage(adminUiErrorMessage(e, t));
    }
  }

  async function forceFulfillOrder() {
    setLoading(true);
    setMessage(null);
    try {
      const orderId = dbIdFromApi(fulfillForm.order_id.trim());
      await adminApiRequest(
        adminPath(ADMIN_SHOP_ORDERS_ORDER_ID_FORCE_FULFILL_PATH, {
          order_id: orderId,
        }),
        "POST",
        {
        body: { reason: fulfillForm.reason.trim() || "Ручное завершение подтверждённого заказа" },
        idempotencyKey: newIdempotencyKey(),
      });
      setFulfillModalOpen(false);
      await loadOrders();
      await loadOrderCounters();
    } catch (e: any) {
      setMessage(adminUiErrorMessage(e, t));
    } finally {
      setLoading(false);
    }
  }

  async function loadCatalog() {
    try {
      const res = await adminApiRequest<CatalogItem[]>(ADMIN_SHOP_ITEMS_PATH, "GET");
      const normalized = (res || []).map((item) => ({
        ...item,
        active: item.is_active ?? item.active,
        methods: item.methods || {
          EFHC: item.price_efhc ? { price: item.price_efhc } : undefined,
          TON: item.price_ton ? { price: item.price_ton } : undefined,
          USDT: item.price_usdt ? { price: item.price_usdt } : undefined,
        } as any,
      }));
      setCatalog(normalized);
    } catch (e: any) {
      setMessage(adminUiErrorMessage(e, t));
    }
  }

  async function loadOrder(rawOrderId?: string) {
    const raw = String(rawOrderId ?? orderSearchInput).trim().replace(/^#/, "");
    setLoading(true);
    setMessage(null);
    try {
      const orderId = dbIdFromApi(raw);
      const res = await adminApiRequest<AdminOrder>(
        adminPath(ADMIN_SHOP_ORDER_ORDER_ID_PATH, {
          order_id: orderId,
        }),
        "GET",
      );
      if (!isPaidShopOrderRecord(res as unknown as Record<string, unknown>)) {
        throw new Error("SHOP_ORDER_NOT_PAID");
      }
      setSelectedOrder(res);
      if (isExactGlobalId(String(res.global_id || ""))) rememberGlobalId(String(res.global_id));
      setSelectedUserOrders([]);
      setSearchedGlobalId("");
      setUserSearchState("found");
      setActiveTab("orders");
    } catch (e: any) {
      setSelectedOrder(null);
      setUserSearchState("error");
      setMessage(adminUiErrorMessage(e, t));
    } finally {
      setLoading(false);
    }
  }

  async function loadUserOrders(rawGlobalId?: string) {
    const globalId = String(rawGlobalId ?? orderSearchInput).trim();
    if (!isExactGlobalId(globalId)) {
      setSelectedUserOrders([]);
      setSearchedGlobalId("");
      setUserSearchState("invalid");
      return;
    }
    setLoading(true);
    setUserSearchState("loading");
    setMessage(null);
    try {
      const res = await adminApiRequest<AdminOrder[]>(
        adminPath(ADMIN_SHOP_ORDERS_USER_GLOBAL_ID_PATH, {
          global_id: globalId,
        }),
        "GET",
      );
      const paidRows = (res || []).filter((row) => isPaidShopOrderRecord(row as unknown as Record<string, unknown>));
      setSelectedOrder(null);
      setSelectedUserOrders(paidRows);
      setSearchedGlobalId(globalId);
      rememberGlobalId(globalId);
      setUserSearchState(paidRows.length ? "found" : "empty");
      setActiveTab("orders");
    } catch (e: any) {
      setSelectedUserOrders([]);
      setSearchedGlobalId(globalId);
      setUserSearchState("error");
      setMessage(adminUiErrorMessage(e, t));
    } finally {
      setLoading(false);
    }
  }

  async function runUniversalOrderSearch() {
    const raw = orderSearchInput.trim();
    if (!raw || loading) return;
    if (/^\d{10}$/.test(raw)) {
      await loadUserOrders(raw);
      return;
    }
    if (/^#?\d+$/.test(raw)) {
      await loadOrder(raw);
      return;
    }

    setLoading(true);
    setUserSearchState("loading");
    setMessage(null);
    setSelectedOrder(null);
    setSelectedUserOrders([]);
    try {
      const query = new URLSearchParams({ q: raw });
      const resolved = await adminApiRequest<{ global_id: string }>(
        `${ADMIN_USERS_RESOLVE_PROVIDER_PATH}?${query.toString()}`,
        "GET",
      );
      const globalId = String(resolved.global_id || "").trim();
      if (!isExactGlobalId(globalId)) throw new Error("ADMIN_ORDER_OWNER_RESOLUTION_INVALID");
      const res = await adminApiRequest<AdminOrder[]>(
        adminPath(ADMIN_SHOP_ORDERS_USER_GLOBAL_ID_PATH, { global_id: globalId }),
        "GET",
      );
      const paidRows = (res || []).filter((row) => isPaidShopOrderRecord(row as unknown as Record<string, unknown>));
      setSelectedUserOrders(paidRows);
      setSearchedGlobalId(globalId);
      rememberGlobalId(globalId);
      setUserSearchState(paidRows.length ? "found" : "empty");
      setActiveTab("orders");
    } catch (e: unknown) {
      setSearchedGlobalId("");
      setUserSearchState("error");
      setMessage(adminUiErrorMessage(e, t));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!restored || !selectedGlobalId) return;
    const remembered = String(selectedGlobalId);
    setOrderSearchInput(remembered);
    setSearchedGlobalId(remembered);
  }, [restored]);

  function resetOrderOwnerSelection() {
    clearGlobalId();
    setOrderSearchInput("");
    setSelectedOrder(null);
    setSelectedUserOrders([]);
    setSearchedGlobalId("");
    setUserSearchState("idle");
    setMessage(null);
  }

  async function exportSelectedUserOrders(format: AdminLogExportFormat) {
    const globalId = String(selectedGlobalId || "").trim();
    if (!isExactGlobalId(globalId) || searchedGlobalId.trim() !== globalId || userOrdersExporting) return;
    setUserOrdersExporting(format);
    setMessage(null);
    try {
      const res = await adminApiRequest<AdminOrder[]>(
        adminPath(ADMIN_SHOP_ORDERS_USER_GLOBAL_ID_PATH, { global_id: globalId }),
        "GET",
      );
      const paidRows = (res || []).filter((row) => isPaidShopOrderRecord(row as unknown as Record<string, unknown>));
      if (paidRows.some((row) => String(row.global_id || "").trim() !== globalId)) {
        throw new Error("admin_shop_selected_export_scope_violation");
      }
      const table: Array<Array<unknown>> = [[
        "ShopOrder ID", "Global ID", "Товар", "Название", "Тип", "Статус", "Способ оплаты", "Сумма",
        "Хэш транзакции", "Memo", "Fulfillment", "Создан", "Обновлён", "Оплачен", "Выполнен",
      ]];
      for (const row of paidRows) {
        table.push([
          row.order_id, row.global_id ?? "", row.item_code ?? "", row.item_title ?? "", row.type ?? "", row.status ?? "",
          row.payment_method ?? "", row.expected_amount ?? row.quantity_efhc ?? "", row.tx_hash ?? "", row.memo ?? "",
          row.fulfillment_state ?? "", row.created_at ?? "", row.updated_at ?? "", row.paid_at ?? "", row.fulfilled_at ?? "",
        ]);
      }
      const date = new Date().toISOString().slice(0, 10);
      const base = `efhc-shop-orders-global-${globalId}-${date}`;
      if (format === "json") {
        downloadBlob(buildJsonBlobFromTable(table, {
          kind: "efhc_admin_shop_user_orders_export",
          generated_at: new Date().toISOString(),
          global_id: globalId,
          paid_only: true,
        }), `${base}.json`);
      } else if (format === "csv") downloadBlob(csvBlob(table), `${base}.csv`);
      else downloadBlob(buildSimpleXlsx(table, "User Shop orders"), `${base}.xlsx`);
      setMessage(`Выгрузка оплаченных заказов Global ID ${globalId}: ${paidRows.length.toLocaleString("ru-RU")} записей.`);
    } catch (e: any) {
      setMessage(adminUiErrorMessage(e, t));
    } finally {
      setUserOrdersExporting(null);
    }
  }

  async function saveItemContent(payload?: Partial<ShopEditorState>) {
    const body = {
      code: payload?.code ?? editor.code,
      title: payload?.title ?? editor.title,
      description: payload?.description ?? editor.description,
      translations: payload?.translations ?? editor.translations,
      item_type: payload?.item_type ?? editor.item_type,
      quantity_efhc: (payload?.quantity_efhc ?? editor.quantity_efhc) || null,
      image_url: (payload?.image_url ?? editor.image_url) || null,
      status: payload?.status ?? editor.status,
      price_efhc: (payload?.price_efhc ?? editor.price_efhc) || null,
      price_ton: (payload?.price_ton ?? editor.price_ton) || null,
      price_usdt: (payload?.price_usdt ?? editor.price_usdt) || null,
      pay_currencies: payload?.pay_currencies ?? editor.pay_currencies,
      category: payload?.category ?? editor.category,
      badge: payload?.badge ?? editor.badge,
      action_mode: payload?.action_mode ?? editor.action_mode,
      external_url: (payload?.external_url ?? editor.external_url) || null,
      delivery_mode: payload?.delivery_mode ?? editor.delivery_mode,
      sort_order: Number((payload?.sort_order ?? editor.sort_order) || 0),
    };
    if (!String(body.code || "").trim()) {
      setMessage("Укажите код товара.");
      return;
    }
    if (!String(body.title || "").trim()) {
      setMessage("Укажите название товара.");
      return;
    }
    const normalizedType = String(body.item_type || "").trim().toUpperCase();
    let vipNumbers: string[] = [];
    let vipUnavailableNumbers: string[] = [];
    if (normalizedType === "EFHC_PACKAGE") {
      const isCustomPackage = String(body.code || "").trim().toUpperCase() === CUSTOM_EFHC_PACKAGE_CODE;
      if (isCustomPackage) {
        body.quantity_efhc = null;
        body.price_efhc = null;
        body.pay_currencies = body.pay_currencies.filter((method) => method === "TON" || method === "USDT");
      } else {
        const fixedCode = String(body.code || "").trim().toUpperCase();
        if (!FIXED_EFHC_PACKAGE_CODE_SET.has(fixedCode)) {
          setMessage("Новый произвольный номинал EFHCm запрещён: используйте один из 15 canonical fixed packages или Обмен EFHCm.");
          return;
        }
        const quantity = fixedCode.replace(/^EFHC_PACKAGE_/, "");
        body.quantity_efhc = quantity;
        body.price_efhc = null;
        body.pay_currencies = body.pay_currencies.filter((method) => method === "TON" || method === "USDT");
      }
    }
    if (normalizedType === "NFT_VIP") {
      body.quantity_efhc = null;
      body.image_url = VIP_FIXED_IMAGE_URL;
      body.pay_currencies = body.pay_currencies.filter((method) => method === "TON" || method === "USDT" || method === "EFHC");
      const parsedInventory = parseVipNumbers(payload?.vip_available_numbers ?? editor.vip_available_numbers);
      const parsedUnavailable = parseVipNumbers(payload?.vip_unavailable_numbers ?? editor.vip_unavailable_numbers);
      if (parsedInventory.invalid.length) {
        setMessage(`Номера VIP NFT должны быть четырёхзначными 0001–9999. 0000 уже недоступен. Ошибка: ${parsedInventory.invalid.slice(0, 5).join(", ")}.`);
        return;
      }
      if (parsedUnavailable.invalid.length) {
        setMessage(`Недоступные номера должны быть четырёхзначными 0001–9999. Ошибка: ${parsedUnavailable.invalid.slice(0, 5).join(", ")}.`);
        return;
      }
      const overlap = parsedInventory.numbers.filter((number) => parsedUnavailable.numbers.includes(number));
      if (overlap.length) {
        setMessage(`Один номер нельзя одновременно сделать доступным и недоступным: ${overlap.slice(0, 5).join(", ")}.`);
        return;
      }
      vipNumbers = parsedInventory.numbers;
      vipUnavailableNumbers = parsedUnavailable.numbers;
      const baseCode = String(body.code || "");
      const occupied = new Set(
        catalog.filter((candidate) => isOwnedVipNumberItem(candidate))
          .map((candidate) => vipNumberFromCatalog(candidate, baseCode))
          .filter(Boolean),
      );
      const blocked = vipNumbers.filter((number) => occupied.has(number));
      if (blocked.length) {
        setMessage(`Занятые номера нельзя вернуть в продажу: ${blocked.slice(0, 5).join(", ")}. Данные владельца защищены.`);
        return;
      }
      if (!isD8PriceInput(payload?.vip_selected_price_efhc ?? editor.vip_selected_price_efhc)) {
        setMessage("Цена EFHC за выбор номера: максимум 8 знаков после запятой.");
        return;
      }
    }
    if (body.price_efhc && !isD8PriceInput(String(body.price_efhc))) {
      setMessage("Цена EFHC: максимум 8 знаков после запятой.");
      return;
    }
    if (body.price_ton && !isD2PriceInput(String(body.price_ton))) {
      setMessage("Цена TON: максимум 2 знака после запятой.");
      return;
    }
    if (body.price_usdt && !isD2PriceInput(String(body.price_usdt))) {
      setMessage("Цена USDT: максимум 2 знака после запятой.");
      return;
    }
    setSaving(true);
    setMessage(null);
    try {
      await adminApiRequest(ADMIN_SHOP_ITEMS_UPSERT_PATH, "POST", {
        idempotencyKey: newIdempotencyKey(),
        body,
      });
      if (normalizedType === "NFT_VIP") {
        const selectedPrices = {
          efhc: (payload?.vip_selected_price_efhc ?? editor.vip_selected_price_efhc) || null,
          // Selected-number TON/USDT inherit only Admin-defined base VIP prices.
          ton: body.price_ton || null,
          usdt: body.price_usdt || null,
        };
        const selectedCode = `${body.code}${VIP_SELECTED_PRICE_SUFFIX}`;
        await adminApiRequest(ADMIN_SHOP_ITEMS_UPSERT_PATH, "POST", {
          idempotencyKey: newIdempotencyKey(),
          body: {
            code: selectedCode,
            title: "EFHC VIP NFT · выбор номера",
            description: "Ценовая ступень для выбора конкретного доступного четырёхзначного номера.",
            item_type: "NFT_VIP_SELECTED_PRICE",
            quantity_efhc: null,
            image_url: null,
            status: body.status,
            price_efhc: selectedPrices.efhc,
            price_ton: selectedPrices.ton,
            price_usdt: selectedPrices.usdt,
            pay_currencies: ["TON", "USDT", "EFHC"],
            category: "vip_price",
            badge: "Выбор номера",
            action_mode: "checkout",
            external_url: null,
            delivery_mode: "manual",
            sort_order: Number(body.sort_order) + 1,
          },
        });

        const existingNumberItems = catalog.filter((candidate) => {
          const code = catalogCode(candidate);
          return String(candidate.item_type || "").trim().toUpperCase() === "NFT_VIP_NUMBER"
            && code.startsWith(`${body.code}${VIP_NUMBER_MARKER}`);
        });
        for (const number of vipNumbers) {
          const numberCode = `${body.code}${VIP_NUMBER_MARKER}${number}`;
          await adminApiRequest(ADMIN_SHOP_ITEMS_UPSERT_PATH, "POST", {
            idempotencyKey: newIdempotencyKey(),
            body: {
              code: numberCode,
              title: `EFHC VIP NFT #${number}`,
              description: "Доступный четырёхзначный номер EFHC VIP NFT.",
              item_type: "NFT_VIP_NUMBER",
              quantity_efhc: null,
              image_url: null,
              status: body.status,
              price_efhc: selectedPrices.efhc,
              price_ton: selectedPrices.ton,
              price_usdt: selectedPrices.usdt,
              pay_currencies: ["TON", "USDT", "EFHC"],
              category: "vip_number",
              badge: number,
              action_mode: "checkout",
              external_url: null,
              delivery_mode: "manual",
              sort_order: 2100 + Number(number),
            },
          });
        }
        for (const number of vipUnavailableNumbers) {
          const numberCode = `${body.code}${VIP_NUMBER_MARKER}${number}`;
          const existing = existingNumberItems.find((candidate) => catalogCode(candidate) === numberCode);
          if (existing) {
            await adminApiRequest(ADMIN_SHOP_ITEMS_STATUS_PATH, "POST", {
              idempotencyKey: newIdempotencyKey(),
              body: { code: numberCode, status: "hidden" },
            });
          } else {
            await adminApiRequest(ADMIN_SHOP_ITEMS_UPSERT_PATH, "POST", {
              idempotencyKey: newIdempotencyKey(),
              body: {
                code: numberCode,
                title: `EFHC VIP NFT #${number}`,
                description: "Номер временно или постоянно недоступен для публикации.",
                item_type: "NFT_VIP_NUMBER",
                quantity_efhc: null,
                image_url: null,
                status: "hidden",
                price_efhc: selectedPrices.efhc,
                price_ton: selectedPrices.ton,
                price_usdt: selectedPrices.usdt,
                pay_currencies: ["TON", "USDT", "EFHC"],
                category: "vip_number",
                badge: number,
                action_mode: "checkout",
                external_url: null,
                delivery_mode: "manual",
                sort_order: 2100 + Number(number),
              },
            });
          }
        }
        // M11-85: omission is not removal. Only explicitly unavailable/owned numbers are hidden.
      }
      setMessage(
        normalizedType === "NFT_VIP"
          ? `VIP NFT сохранён: шесть цен, ${vipNumbers.length} доступных и ${vipUnavailableNumbers.length} явно недоступных номеров.`
          : "Карточка товара сохранена.",
      );
      setSelectedSku(body.code);
      await loadCatalog();
    } catch (e: any) {
      setMessage(adminUiErrorMessage(e, t));
    } finally {
      setSaving(false);
    }
  }

  async function saveCurrentItem() {
    await saveItemContent();
  }

  async function saveItemStatus(status: string, code?: string) {
    const itemCode = code || editor.code;
    if (!itemCode) return;
    setSaving(true);
    setMessage(null);
    try {
      await adminApiRequest(ADMIN_SHOP_ITEMS_STATUS_PATH, "POST", {
        idempotencyKey: newIdempotencyKey(),
        body: { code: itemCode, status },
      });
      if (String(editor.item_type || "").trim().toUpperCase() === "NFT_VIP") {
        const companionCodes = catalog
          .filter((candidate) => {
            const candidateCode = catalogCode(candidate);
            return candidateCode === `${itemCode}${VIP_SELECTED_PRICE_SUFFIX}`
              || candidateCode.startsWith(`${itemCode}${VIP_NUMBER_MARKER}`);
          })
          .map(catalogCode);
        for (const companionCode of companionCodes) {
          await adminApiRequest(ADMIN_SHOP_ITEMS_STATUS_PATH, "POST", {
            idempotencyKey: newIdempotencyKey(),
            body: { code: companionCode, status },
          });
        }
      }
      if (itemCode === editor.code) {
        setEditor((prev) => ({
          ...prev,
          status,
          is_active: status === "live",
        }));
      }
      setMessage(`Статус карточки обновлён: ${status}.`);
      await loadCatalog();
    } catch (e: any) {
      setMessage(adminUiErrorMessage(e, t));
    } finally {
      setSaving(false);
    }
  }

  function selectItem(item: CatalogItem, openEditor = true) {
    const nextEditor = toEditor(item);
    if (String(item.item_type || "").trim().toUpperCase() === "NFT_VIP") {
      const baseCode = catalogCode(item);
      const selectedTier = catalog.find(
        (candidate) => catalogCode(candidate) === `${baseCode}${VIP_SELECTED_PRICE_SUFFIX}`,
      );
      const availableNumbers = catalog
        .filter((candidate) => {
          const code = catalogCode(candidate);
          return String(candidate.item_type || "").trim().toUpperCase() === "NFT_VIP_NUMBER"
            && code.startsWith(`${baseCode}${VIP_NUMBER_MARKER}`)
            && statusOf(candidate) === "live";
        })
        .map((candidate) => catalogCode(candidate).slice(`${baseCode}${VIP_NUMBER_MARKER}`.length))
        .filter((number) => /^\d{4}$/.test(number) && number !== "0000")
        .sort();
      const unavailableNumbers = catalog
        .filter((candidate) => {
          const code = catalogCode(candidate);
          return String(candidate.item_type || "").trim().toUpperCase() === "NFT_VIP_NUMBER"
            && code.startsWith(`${baseCode}${VIP_NUMBER_MARKER}`)
            && statusOf(candidate) !== "live";
        })
        .map((candidate) => catalogCode(candidate).slice(`${baseCode}${VIP_NUMBER_MARKER}`.length))
        .filter((number) => /^\d{4}$/.test(number) && number !== "0000")
        .sort();
      nextEditor.vip_selected_price_efhc = selectedTier?.price_efhc || selectedTier?.methods?.EFHC?.price || "";
      nextEditor.vip_selected_price_ton = nextEditor.price_ton;
      nextEditor.vip_selected_price_usdt = nextEditor.price_usdt;
      nextEditor.vip_available_numbers = availableNumbers.join("\n");
      nextEditor.vip_unavailable_numbers = unavailableNumbers.join("\n");
    }
    setSelectedSku(item.sku);
    setEditor(nextEditor);
    setActiveTab("catalog");
    setEditorOpen(openEditor);
  }

  const ownerCatalog = useMemo(() => ownerShopCatalogPositions(catalog), [catalog]);
  const requestedShopView = Array.isArray(router.query.view) ? router.query.view[0] : router.query.view;
  const shopView = requestedShopView === "vip-input" || requestedShopView === "vip-map" ? requestedShopView : "products";
  const vipProduct = ownerCatalog.find((item) => String(item.item_type || "").trim().toUpperCase() === "NFT_VIP") || null;

  const selectedItem = useMemo(() => {
    if (!selectedSku) return null;
    return ownerCatalog.find((item) => item.sku === selectedSku) || null;
  }, [ownerCatalog, selectedSku]);
  const ordersWindow = useAdminListWindow(orders, "shop-orders");
  const selectedUserOrdersWindow = useAdminListWindow(
    selectedUserOrders,
    `shop-user-orders:${selectedUserOrders[0]?.global_id || "none"}`,
  );

  const vipNumberMap = useMemo(() => {
    const baseCode = editor.item_type.trim().toUpperCase() === "NFT_VIP" ? editor.code.trim() : "";
    if (!baseCode) return [] as Array<{ number: string; state: "available" | "unavailable" | "occupied" | "not-listed"; owner: string; deliveryWallet: string }>;
    const byNumber = new Map<string, CatalogItem>();
    for (const item of catalog) {
      if (String(item.item_type || "").trim().toUpperCase() !== "NFT_VIP_NUMBER") continue;
      const number = vipNumberFromCatalog(item, baseCode);
      if (number) byNumber.set(number, item);
    }
    const query = vipMapSearch.trim();
    return Array.from({ length: 9999 }, (_, index) => {
      const number = String(index + 1).padStart(4, "0");
      const item = byNumber.get(number);
      const owner = String(item?.owner_global_id || item?.vip_owner_global_id || "").trim();
      const deliveryWallet = String(item?.delivery_wallet_address || "").trim();
      const state = !item
        ? "not-listed" as const
        : isOwnedVipNumberItem(item)
          ? "occupied" as const
          : statusOf(item) === "live"
            ? "available" as const
            : "unavailable" as const;
      return { number, state, owner, deliveryWallet };
    }).filter((entry) => (!query || entry.number.includes(query)) && (vipMapFilter === "all" || entry.state === vipMapFilter));
  }, [catalog, editor.code, editor.item_type, vipMapFilter, vipMapSearch]);
  const vipNumberMapPage = vipNumberMap.slice(vipMapPage * 100, vipMapPage * 100 + 100);
  const vipNumberStateCounts = useMemo(() => {
    const baseCode = editor.item_type.trim().toUpperCase() === "NFT_VIP" ? editor.code.trim() : "";
    const result = { available: 0, unavailable: 0, occupied: 0, notListed: 9999 };
    if (!baseCode) return result;
    const seen = new Set<string>();
    result.notListed = 9999;
    for (const item of catalog) {
      if (String(item.item_type || "").trim().toUpperCase() !== "NFT_VIP_NUMBER") continue;
      const number = vipNumberFromCatalog(item, baseCode);
      if (!number || seen.has(number)) continue;
      seen.add(number);
      result.notListed -= 1;
      if (isOwnedVipNumberItem(item)) result.occupied += 1;
      else if (statusOf(item) === "live") result.available += 1;
      else result.unavailable += 1;
    }
    return result;
  }, [catalog, editor.code, editor.item_type]);

  useEffect(() => {
    void loadOrders();
    void loadOrderCounters();
    void loadCatalog();
  }, []);

  useEffect(() => {
    if (!router.isReady) return;
    const requestedModule = Array.isArray(router.query.module)
      ? router.query.module[0]
      : router.query.module;
    if (requestedModule === "orders" || requestedModule === "catalog") {
      setActiveTab(requestedModule);
    }
  }, [router.isReady, router.query.module]);

  useEffect(() => {
    setVipMapPage(0);
  }, [editor.code, vipMapFilter, vipMapSearch]);

  useEffect(() => {
    if (!router.isReady || activeTab !== "catalog" || shopView === "products" || !vipProduct) return;
    if (selectedSku !== vipProduct.sku) selectItem(vipProduct, false);
  }, [router.isReady, activeTab, shopView, selectedSku, vipProduct]);

  function openShopView(view: "products" | "vip-input" | "vip-map") {
    if (view !== "products" && vipProduct && selectedSku !== vipProduct.sku) selectItem(vipProduct, false);
    const query = view === "products" ? {} : { view };
    void router.push({ pathname: "/admin/shop", query }, undefined, { shallow: true });
  }

  function exportVipNumberMap(format: "json" | "csv" | "xlsx") {
    const scopedGlobalId = /^\d{10}$/.test(String(selectedGlobalId || "")) ? String(selectedGlobalId) : "";
    if (scopedGlobalId) {
      setMessage("Scoped export карты VIP номеров заблокирован: отдельный server-side Global ID contract не подтверждён.");
      return;
    }
    const rows: Array<Array<unknown>> = [["vip_number", "state", "global_id", "delivery_wallet"]];
    for (const entry of vipNumberMap) rows.push([entry.number, entry.state, entry.owner, entry.deliveryWallet]);
    const date = new Date().toISOString().slice(0, 10);
    const base = `efhc-vip-number-map-${date}`;
    if (format === "json") {
      downloadBlob(buildJsonBlobFromTable(rows, {
        kind: "efhc_admin_vip_number_map_export",
        generated_at: new Date().toISOString(),
        filter: vipMapFilter,
        search: vipMapSearch.trim(),
      }), `${base}.json`);
    } else if (format === "csv") {
      const text = `\uFEFF${rows.map((row) => row.map(csvCell).join(";")).join("\r\n")}`;
      downloadBlob(new Blob([text], { type: "text/csv;charset=utf-8" }), `${base}.csv`);
    } else {
      downloadBlob(buildSimpleXlsx(rows, "VIP number map"), `${base}.xlsx`);
    }
  }

  const pageTitle = activeTab === "orders"
    ? "Заказы"
    : shopView === "vip-input"
      ? "Магазин · Управление номерами VIP NFT"
      : shopView === "vip-map"
        ? "Магазин · Карта номеров VIP NFT"
        : "Магазин · Товары и цены";

  return (
    <AdminPage title={pageTitle} backHref="/admin">
      <div data-admin-shop-cycle="FRONTEND_ADMIN_CYCLE_0082" />

      {activeTab === "catalog" ? (
        <div className="space-y-4" data-admin-shop-composition="15-fixed-plus-custom-plus-one-vip-owner-catalog">
          <AdminSectionCard
            title="Магазин"
            
            actions={
              <Button variant="secondary" onClick={() => void loadCatalog()} disabled={loading}>
                {loading ? "Обновляется" : "Обновить"}
              </Button>
            }
          >
            <div className="flex flex-wrap gap-2" role="navigation" aria-label="Подстраницы Магазина">
              <Button variant={shopView === "products" ? undefined : "secondary"} onClick={() => openShopView("products")}>Товары</Button>
              <Button variant={shopView === "vip-input" ? undefined : "secondary"} onClick={() => openShopView("vip-input")}>Управление номерами</Button>
              <Button variant={shopView === "vip-map" ? undefined : "secondary"} onClick={() => openShopView("vip-map")}>Карта номеров</Button>
            </div>
            {message ? <div className="mt-3 text-sm text-[color:var(--tg-link)]">{message}</div> : null}
          </AdminSectionCard>

          {shopView === "products" ? (
            <>
              <AdminSectionCard
                title="17 товарных позиций"
                subtitle="Нажмите строку товара — редактор откроется отдельным окном. В списке сразу видны название, тип/номинал, цены и статус."
              >
                <div className="efhc-admin-shop-product-list-v235" data-admin-shop-fixed-list="17-canonical-positions">
                  {ownerCatalog.map((item) => {
                    const currentStatus = statusOf(item);
                    const isVip = String(item.item_type || "").trim().toUpperCase() === "NFT_VIP";
                    const isCustomPackage = String(item.item_type || "").trim().toUpperCase() === "EFHC_PACKAGE" && catalogCode(item).toUpperCase() === CUSTOM_EFHC_PACKAGE_CODE;
                    const quantity = canonicalWholeEfhc(item.quantity_efhc);
                    const priceTon = item.price_ton || item.methods?.TON?.price || "—";
                    const priceUsdt = item.price_usdt || item.methods?.USDT?.price || "—";
                    const priceEfhc = item.price_efhc || item.methods?.EFHC?.price || "—";
                    const selected = selectedSku === item.sku;
                    return (
                      <button
                        key={item.sku}
                        type="button"
                        onClick={() => selectItem(item, true)}
                        data-admin-shop-fixed-product={item.sku}
                        data-selected={String(selected)}
                        className="efhc-admin-shop-product-row-v235"
                        aria-label={`Редактировать ${item.title}`}
                      >
                        <span className="efhc-admin-shop-product-main-v235">
                          <strong>{item.title}</strong>
                          <small>{isVip ? "EFHC VIP NFT" : isCustomPackage ? "Обмен EFHCm · курс за 1 EFHCm" : `${quantity || "—"} EFHCm`}</small>
                        </span>
                        <span className="efhc-admin-shop-product-prices-v235">
                          {isVip ? <small>EFHC <b>{priceEfhc}</b></small> : null}
                          <small>{isCustomPackage ? "TON/GRAM / 1" : "TON/GRAM"} <b>{priceTon}</b></small>
                          <small>{isCustomPackage ? "USDT / 1" : "USDT"} <b>{priceUsdt}</b></small>
                        </span>
                        <span className="efhc-admin-shop-product-status-v235">
                          <TelegramStatusBadge label={currentStatus === "live" ? "Доступно" : "Недоступно"} tone={currentStatus === "live" ? "connected" : "neutral"} />
                          <span aria-hidden="true">›</span>
                        </span>
                      </button>
                    );
                  })}
                </div>
              </AdminSectionCard>

              <Modal
                open={editorOpen && selectedItem !== null}
                onClose={() => setEditorOpen(false)}
                closeDisabled={saving}
                title={selectedItem ? `Редактор: ${selectedItem.title}` : "Редактор товара"}
              >
                {selectedItem ? (
                  <div className="grid gap-3" data-admin-shop-editor-modal="v235">
                    <p className="m-0 text-xs text-[color:var(--tg-hint)]">Редактируются только OWNER-approved поля. SKU/type/image/category/delivery/sort скрыты и сохраняются без изменения.</p>
                    <div className="grid gap-2 md:grid-cols-2" data-admin-shop-compact-editor="v235">
                      <label className="grid gap-1"><span className="text-xs text-[color:var(--tg-hint)]">Название</span><input className="efhc-input" value={editor.title} onChange={(e) => setEditor((prev) => ({ ...prev, title: e.target.value }))} /></label>
                      <label className="grid gap-1"><span className="text-xs text-[color:var(--tg-hint)]">Номинал EFHC</span>{editor.item_type.trim().toUpperCase() === "EFHC_PACKAGE" && editor.code.trim().toUpperCase() !== CUSTOM_EFHC_PACKAGE_CODE ? (<input className="efhc-input" value={editor.code.trim().toUpperCase().replace(/^EFHC_PACKAGE_/, "")} readOnly aria-label="Canonical fixed EFHCm denomination" />) : editor.code.trim().toUpperCase() === CUSTOM_EFHC_PACKAGE_CODE ? (<input className="efhc-input" value="1+ · выбирает пользователь" readOnly aria-label="Обмен EFHCm: количество от 1 EFHCm" />) : (<input className="efhc-input" value="—" readOnly aria-label="Для VIP NFT номинал EFHC не применяется" />)}</label>
                      <label className="grid gap-1 md:col-span-2"><span className="text-xs text-[color:var(--tg-hint)]">Описание</span><textarea className="efhc-input min-h-[74px]" value={editor.description} onChange={(e) => setEditor((prev) => ({ ...prev, description: e.target.value }))} placeholder="Можно оставить пустым" /></label>
                      <div className="grid gap-2 md:col-span-2" data-admin-shop-translations="16">
                        <label className="grid gap-1"><span className="text-xs text-[color:var(--tg-hint)]">Язык описания товара</span>
                          <select className="efhc-input" value={copyLocale} onChange={(e) => setCopyLocale(e.target.value)}>{["en","ru","uk","de","fr","es","it","tr","pl","da","hi","id","sw","pt","ko","ja"].map((code) => <option key={code} value={code}>{code.toUpperCase()}</option>)}</select>
                        </label>
                        <label className="grid gap-1"><span className="text-xs text-[color:var(--tg-hint)]">Название ({copyLocale.toUpperCase()})</span><input className="efhc-input" maxLength={128} value={editor.translations[copyLocale]?.title || ""} onChange={(e) => setEditor((prev) => ({ ...prev, translations: { ...prev.translations, [copyLocale]: { ...prev.translations[copyLocale], title: e.target.value } } }))} /></label>
                        <label className="grid gap-1 md:col-span-2"><span className="text-xs text-[color:var(--tg-hint)]">Описание ({copyLocale.toUpperCase()})</span><textarea className="efhc-input min-h-[74px]" maxLength={512} value={editor.translations[copyLocale]?.description || ""} onChange={(e) => setEditor((prev) => ({ ...prev, translations: { ...prev.translations, [copyLocale]: { ...prev.translations[copyLocale], description: e.target.value } } }))} /></label>
                      </div>
                      {editor.item_type.trim().toUpperCase() === "NFT_VIP" ? (<label className="grid gap-1"><span className="text-xs text-[color:var(--tg-hint)]">Стандартная цена EFHC</span><input className="efhc-input" value={editor.price_efhc} onChange={(e) => { if (!isD8PriceInput(e.target.value)) return; setEditor((prev) => ({ ...prev, price_efhc: e.target.value })); }} /></label>) : null}
                      <label className="grid gap-1"><span className="text-xs text-[color:var(--tg-hint)]">{editor.code.trim().toUpperCase() === CUSTOM_EFHC_PACKAGE_CODE ? "Курс TON / GRAM за 1 EFHCm" : "Цена TON / GRAM"}</span><input className="efhc-input" inputMode="decimal" value={editor.price_ton} onChange={(e) => { if (!isD2PriceInput(e.target.value)) return; setEditor((prev) => ({ ...prev, price_ton: e.target.value })); }} /></label>
                      <label className="grid gap-1"><span className="text-xs text-[color:var(--tg-hint)]">{editor.code.trim().toUpperCase() === CUSTOM_EFHC_PACKAGE_CODE ? "Курс USDT за 1 EFHCm" : "Цена USDT"}</span><input className="efhc-input" inputMode="decimal" value={editor.price_usdt} onChange={(e) => { if (!isD2PriceInput(e.target.value)) return; setEditor((prev) => ({ ...prev, price_usdt: e.target.value })); }} /></label>
                      <div className="grid gap-1"><span className="text-xs text-[color:var(--tg-hint)]">Методы оплаты</span><div className="flex flex-wrap gap-3 rounded-xl border border-[color:var(--tg-hint)]/20 p-2">{(editor.item_type.trim().toUpperCase() === "NFT_VIP" ? ["EFHC", "TON", "USDT"] : ["TON", "USDT"]).map((method) => (<label key={method} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={editor.pay_currencies.includes(method)} onChange={(e) => setEditor((prev) => ({ ...prev, pay_currencies: e.target.checked ? Array.from(new Set([...prev.pay_currencies, method])) : prev.pay_currencies.filter((value) => value !== method) }))} />{method}</label>))}</div></div>
                      <label className="grid gap-1"><span className="text-xs text-[color:var(--tg-hint)]">Метка на карточке</span><input className="efhc-input" value={editor.badge} onChange={(e) => setEditor((prev) => ({ ...prev, badge: e.target.value }))} placeholder="Можно оставить пустым" /></label>
                      <label className="grid gap-1"><span className="text-xs text-[color:var(--tg-hint)]">Режим карточки</span><select className="efhc-input" value={editor.action_mode} onChange={(e) => setEditor((prev) => ({ ...prev, action_mode: e.target.value }))}><option value="checkout">Оплата через EFHC Shop</option><option value="external_link">Внешняя ссылка</option></select></label>
                      <label className="grid gap-1 md:col-span-2"><span className="text-xs text-[color:var(--tg-hint)]">Внешняя ссылка</span><input className="efhc-input" value={editor.external_url} onChange={(e) => setEditor((prev) => ({ ...prev, external_url: e.target.value }))} placeholder="https://..." /></label>
                    </div>
                    <div className="flex flex-wrap gap-2"><Button onClick={() => void saveCurrentItem()} disabled={saving}>{saving ? t("admin.working") : "Сохранить товар"}</Button><Button variant="secondary" onClick={() => void saveItemStatus(editor.status === "live" ? "hidden" : "live")} disabled={saving || selectedItem.id == null}>{selectedItem.id == null ? "Сначала сохранить" : editor.status === "live" ? "Сделать недоступным" : "Сделать доступным"}</Button><Button variant="secondary" onClick={() => setEditorOpen(false)} disabled={saving}>Закрыть</Button></div>
                  </div>
                ) : null}
              </Modal>
            </>
          ) : null}

          {shopView === "vip-input" ? (
            <AdminSettingsCard
              title="Управление номерами EFHC VIP NFT"
            >
              {editor.item_type.trim().toUpperCase() === "NFT_VIP" ? (
                <>
                  <div className="grid gap-3 md:grid-cols-2" data-admin-shop-vip-input-page="v231">
                    <label className="grid gap-1"><span className="text-xs text-[color:var(--tg-hint)]">Выбор конкретного номера · цена EFHC</span><input className="efhc-input" value={editor.vip_selected_price_efhc} onChange={(e) => { if (!isD8PriceInput(e.target.value)) return; setEditor((prev) => ({ ...prev, vip_selected_price_efhc: e.target.value })); }} /><small className="text-xs text-[color:var(--tg-hint)]">TON / GRAM и USDT используют стандартные VIP цены без надбавки.</small></label>
                    <div className="rounded-xl border border-[color:var(--tg-hint)]/20 p-3 text-xs text-[color:var(--tg-hint)]"><strong className="block text-[color:var(--tg-text)]">Правило цены</strong><span>Отдельная надбавка применяется только к EFHC при выборе конкретного номера.</span></div>
                    <label className="grid gap-1"><span className="text-xs text-[color:var(--tg-hint)]">Сделать доступными</span><textarea className="efhc-input min-h-[260px] font-mono" value={editor.vip_available_numbers} onChange={(e) => setEditor((prev) => ({ ...prev, vip_available_numbers: e.target.value }))} placeholder={"0001\n0002\n0123"} /></label>
                    <label className="grid gap-1"><span className="text-xs text-[color:var(--tg-hint)]">Сделать недоступными</span><textarea className="efhc-input min-h-[260px] font-mono" value={editor.vip_unavailable_numbers} onChange={(e) => setEditor((prev) => ({ ...prev, vip_unavailable_numbers: e.target.value }))} placeholder={"0007\n0042\n9999"} /><small className="text-xs text-[color:var(--tg-hint)]">Номера сохраняются в карте, но не показываются покупателю.</small></label>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2"><Button onClick={() => void saveCurrentItem()} disabled={saving}>{saving ? t("admin.working") : "Сохранить списки номеров"}</Button><Button variant="secondary" onClick={() => openShopView("vip-map")}>Открыть карту номеров</Button></div>
                </>
              ) : <TelegramEmptyState title="VIP NFT загружается" detail="Обновите каталог, если карточка VIP NFT ещё не получена." />}
            </AdminSettingsCard>
          ) : null}

          {shopView === "vip-map" ? (
            <AdminSectionCard
              title="Карта EFHC VIP NFT · 0001–9999"
              subtitle="Отдельная подстраница реестра. Здесь остаются поиск, фильтр, 100 номеров на страницу и JSON/CSV/XLSX export."
            >
              <div className="efhc-admin-vip-number-map" data-admin-vip-number-map="0001-9999" data-admin-shop-vip-map-page="v231">
                <div className="efhc-admin-vip-number-map_summary"><span>Доступно <b>{vipNumberStateCounts.available}</b></span><span>Недоступно <b>{vipNumberStateCounts.unavailable}</b></span><span>Занято <b>{vipNumberStateCounts.occupied}</b></span><span>Не выставлено <b>{vipNumberStateCounts.notListed}</b></span></div>
                <div className="efhc-admin-vip-number-map_controls"><input className="efhc-input" value={vipMapSearch} inputMode="numeric" maxLength={4} onChange={(event) => setVipMapSearch(event.target.value.replace(/\D/g, ""))} placeholder="Поиск 0001–9999" /><select className="efhc-input" value={vipMapFilter} onChange={(event) => setVipMapFilter(event.target.value as typeof vipMapFilter)}><option value="all">Все 9999</option><option value="available">Доступные</option><option value="unavailable">Недоступные</option><option value="occupied">Занятые</option><option value="not-listed">Не выставленные</option></select><Button variant="secondary" disabled={Boolean(selectedGlobalId)} title={selectedGlobalId ? "Selected-user export требует отдельного server-side scope." : undefined} onClick={() => exportVipNumberMap("json")}>Карта JSON</Button><Button variant="secondary" disabled={Boolean(selectedGlobalId)} title={selectedGlobalId ? "Selected-user export требует отдельного server-side scope." : undefined} onClick={() => exportVipNumberMap("csv")}>Карта CSV</Button><Button variant="secondary" disabled={Boolean(selectedGlobalId)} title={selectedGlobalId ? "Selected-user export требует отдельного server-side scope." : undefined} onClick={() => exportVipNumberMap("xlsx")}>Карта XLSX</Button></div>
                <div className="efhc-admin-vip-number-map_grid" role="list" aria-label="Карта номеров EFHC VIP NFT">{vipNumberMapPage.map((entry) => (<div key={entry.number} role="listitem" data-vip-number-state={entry.state} title={entry.owner ? `Global ID ${entry.owner}${entry.deliveryWallet ? ` · ${entry.deliveryWallet}` : ""}` : entry.state}><strong>{entry.number}</strong><small>{entry.state === "available" ? "доступен" : entry.state === "occupied" ? `занят${entry.owner ? ` · ${entry.owner}` : ""}` : entry.state === "unavailable" ? "недоступен" : "не выставлен"}</small></div>))}</div>
                <div className="efhc-admin-vip-number-map_pager"><Button variant="secondary" disabled={vipMapPage <= 0} onClick={() => setVipMapPage((page) => Math.max(0, page - 1))}>Предыдущие 100</Button><span>{vipNumberMap.length ? `${vipMapPage * 100 + 1}–${Math.min(vipNumberMap.length, vipMapPage * 100 + 100)} из ${vipNumberMap.length}` : "Нет номеров"}</span><Button variant="secondary" disabled={(vipMapPage + 1) * 100 >= vipNumberMap.length} onClick={() => setVipMapPage((page) => page + 1)}>Следующие 100</Button></div>
                <p>Owner/Global ID/wallet показываются только из физически подтверждённых catalog/order/ownership полей.</p>
              </div>
            </AdminSectionCard>
          ) : null}
        </div>
      ) : null}

      {/* OWNER v237: Admin Shop = 17 canonical product rows + modal editor; VIP input/map remain separate subpages. */}

      {activeTab === "orders" ? (
        <div className="grid gap-4">
          <AdminSectionCard
            title="Поиск заказа"
          >
            <div
              className="space-y-3"
              data-admin-orders-search="v389"
              data-admin-orders-search-width="v443"
              data-admin-selected-global-id={selectedGlobalId || "none"}
              data-eam-family="EAM-ADMIN-022"
              data-admin-visual-primitive="ADMIN_CONTROL"
              data-admin-instance="orders-search-production-v389"
              data-admin-orders-state="orders"
            >
              <div
                className="grid grid-cols-2 items-end"
                data-admin-orders-search-mode="universal"
                data-admin-search-geometry="v425-v430"
                data-admin-global-id-search-canon="v435"
                style={{ gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: ".45rem" }}
              >
                <input
                  className="efhc-input col-span-2 w-full"
                  value={orderSearchInput}
                  onChange={(event) => {
                    setOrderSearchInput(event.target.value);
                    if (userSearchState === "invalid" || userSearchState === "error") setUserSearchState("idle");
                  }}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !loading && orderSearchInput.trim()) void runUniversalOrderSearch();
                  }}
                  placeholder="Global ID, ShopOrder ID или TON-кошелёк"
                  autoCapitalize="none"
                  autoCorrect="off"
                  spellCheck={false}
                  autoComplete="off"
                  data-admin-orders-search-input="universal"
                  style={{ minHeight: "2.25rem", padding: ".52rem .62rem", borderRadius: ".68rem" }}
                />
                <Button
                  className="w-full min-w-0"
                  variant="secondary"
                  disabled={loading || (!orderSearchInput && !selectedGlobalId && !selectedOrder && !selectedUserOrders.length)}
                  onClick={resetOrderOwnerSelection}
                  data-admin-orders-search-action="reset"
                  data-admin-visual-primitive="ADMIN_BUTTON_SECONDARY"
                  style={{ minHeight: "2.25rem", padding: ".52rem .68rem", borderRadius: ".68rem" }}
                >
                  Сбросить
                </Button>
                <Button
                  className="w-full min-w-0"
                  variant="secondary"
                  disabled={loading || !orderSearchInput.trim()}
                  onClick={() => void runUniversalOrderSearch()}
                  data-admin-orders-search-action="universal"
                  data-admin-visual-primitive="ADMIN_BUTTON_SECONDARY"
                  style={{ minHeight: "2.25rem", padding: ".52rem .68rem", borderRadius: ".68rem" }}
                >
                  {loading ? "Поиск…" : "Найти"}
                </Button>
              </div>

              {userSearchState === "invalid" && orderSearchInput ? (
                <div className="text-xs efhc-text-muted2" data-admin-orders-search-state="invalid">Некорректный запрос.</div>
              ) : null}
              {userSearchState === "empty" ? (
                <TelegramEmptyState
                  title={`Оплаченных заказов Global ID ${searchedGlobalId} нет`}
                  detail="API вернул пользователя без оплаченных ShopOrder в этом контуре."
                />
              ) : null}
              {userSearchState === "error" ? (
                <div className="text-sm efhc-text-muted2" data-admin-orders-search-state="error">Ошибка API при поиске заказа или владельца.</div>
              ) : null}

              {selectedOrder ? (
                <TelegramSectionRow
                  compact
                  title={`Заказ №${selectedOrder.order_id}`}
                  subtitle={
                    `Состояние: ${selectedOrder.status} · Тип: ${selectedOrder.type}`
                    + ` · Товар: ${selectedOrder.item_title || selectedOrder.item_code || "—"}`
                    + ` · Оплата: ${selectedOrder.payment_method || "—"}`
                    + ` · Сумма: ${selectedOrder.expected_amount || selectedOrder.quantity_efhc || "—"}`
                    + ` · Создан: ${selectedOrder.created_at || "—"}`
                    + ` · Оплачен: ${selectedOrder.paid_at || "—"}`
                    + ` · Выполнен: ${selectedOrder.fulfilled_at || selectedOrder.fulfillment_state || "—"}`
                    + ` · Memo: ${selectedOrder.memo || "—"}`
                  }
                  rightSlot={
                    <TelegramStatusBadge
                      label={selectedOrder.tx_hash || "нет хэша"}
                      tone="neutral"
                    />
                  }
                />
              ) : null}
              {selectedUserOrdersWindow.visibleItems.length ? (
                <AdminCompactOperationList
                  rows={selectedUserOrdersWindow.visibleItems.map((row) => ({
                    id: row.order_id,
                    operation: `Заказ №${row.order_id} · ${row.status} · ${row.item_title || row.item_code || row.type || "—"}`,
                    amount: `${row.expected_amount || row.quantity_efhc || "—"}${row.payment_method ? ` ${row.payment_method}` : ""}`,
                    subject: `Global ID ${row.global_id || "—"} · TX ${row.tx_hash || "—"}`,
                    time: row.fulfilled_at || row.paid_at || row.created_at || row.updated_at || "—",
                    onClick: () => setSelectedOrder(row),
                    ariaLabel: `Открыть детали заказа ${row.order_id}`,
                  }))}
                />
              ) : null}
              {selectedUserOrders.length ? (
                <>
                  <AdminListExpandControl
                    shown={selectedUserOrdersWindow.visibleCount}
                    total={selectedUserOrdersWindow.totalCount}
                    onExpand={selectedUserOrdersWindow.expand}
                    onCollapse={selectedUserOrdersWindow.collapse}
                  />
                  <div className="flex flex-wrap gap-2" data-admin-orders-selected-global-export={searchedGlobalId}>
                    <Button
                      variant="secondary"
                      disabled={Boolean(userOrdersExporting)}
                      onClick={() => void exportSelectedUserOrders("json")}
                      data-admin-orders-export-filter="global-id-json"
                    >
                      {userOrdersExporting === "json" ? "Скачивание…" : "Скачать JSON по Global ID"}
                    </Button>
                    <Button
                      variant="secondary"
                      disabled={Boolean(userOrdersExporting)}
                      onClick={() => void exportSelectedUserOrders("csv")}
                      data-admin-orders-export-filter="global-id-csv"
                    >
                      {userOrdersExporting === "csv" ? "Скачивание…" : "Скачать CSV по Global ID"}
                    </Button>
                    <Button
                      variant="secondary"
                      disabled={Boolean(userOrdersExporting)}
                      onClick={() => void exportSelectedUserOrders("xlsx")}
                      data-admin-orders-export-filter="global-id-xlsx"
                    >
                      {userOrdersExporting === "xlsx" ? "Скачивание…" : "Скачать XLSX по Global ID"}
                    </Button>
                  </div>
                </>
              ) : null}
              {!selectedOrder && userSearchState === "idle" ? (
                <TelegramEmptyState
                  title="Поиск заказа"
                  detail="Один поисковый контур: точный 10-значный Global ID, ShopOrder ID или серверно однозначно привязанный TON-кошелёк. Показываются только оплаченные заказы."
                />
              ) : null}
            </div>
          </AdminSectionCard>

          <AdminSectionCard
            title="Логи заказов"
            subtitle="Полный оплаченный журнал, независимо от 20 строк на экране."
          >
            <div className="efhc-admin-export-controls-v445 efhc-admin-orders-log-export-v443" data-admin-shop-orders-log-export="json-csv-xlsx-paid-only-v445">
              <select className="efhc-admin-export-rows-v445" value={ordersExportRows} onChange={(event) => setOrdersExportRows(event.target.value as AdminLogExportRows)} disabled={Boolean(ordersExporting)} aria-label="Строк экспорта"><option value="100">100</option><option value="1000">1 000</option><option value="100000">100 000</option><option value="1000000">1 000 000</option><option value="all">Все</option></select>
              <div className="efhc-admin-log-export-strip efhc-admin-orders-export-strip-v443">
                <Button variant="secondary" disabled={Boolean(ordersExporting)} onClick={() => void exportPaidOrders("json")} aria-busy={ordersExporting === "json"}>JSON</Button>
                <Button variant="secondary" disabled={Boolean(ordersExporting)} onClick={() => void exportPaidOrders("csv")} aria-busy={ordersExporting === "csv"}>CSV</Button>
                <Button variant="secondary" disabled={Boolean(ordersExporting)} onClick={() => void exportPaidOrders("xlsx")} aria-busy={ordersExporting === "xlsx"}>XLSX</Button>
              </div>
            </div>
          </AdminSectionCard>

          <AdminSectionCard
            title="Заказы"
          >
            {orders.length ? (
              <div className="space-y-2">
                <AdminCompactOperationList
                  rows={ordersWindow.visibleItems.map((row, idx) => {
                    const orderId = String(row.id || row.order_id || idx);
                    const orderType = String(row.type || "").trim().toUpperCase();
                    const amount = String(row.expected_amount || row.quantity_efhc || "—");
                    const payment = String(row.payment_method || "");
                    return {
                      id: orderId,
                      operation: `Заказ №${orderId} · ${formatUnknown(row.status)}`,
                      amount: `${amount}${payment ? ` ${payment}` : ""}`,
                      subject: `Global ID ${formatUnknown(row.global_id)}`,
                      time: formatUnknown(row.created_at || row.updated_at),
                      action: orderType.includes("NFT") ? (
                        <Button variant="secondary" onClick={() => setActiveTab("nft")}>Выдача NFT</Button>
                      ) : (
                        <Button
                          variant="secondary"
                          onClick={() => {
                            setFulfillForm({
                              order_id: orderId,
                              reason: "Ручное завершение подтверждённого заказа",
                            });
                            setFulfillModalOpen(true);
                          }}
                        >
                          Завершить
                        </Button>
                      ),
                    };
                  })}
                />
                <AdminListExpandControl
                  shown={ordersWindow.visibleCount}
                  total={ordersWindow.totalCount}
                  hasServerMore={Boolean(ordersCursor)}
                  loadingMore={ordersLoadingMore}
                  onExpand={() => {
                    if (ordersWindow.hasMore) ordersWindow.expand();
                    else if (ordersCursor) void loadOrders(ordersCursor);
                  }}
                  onCollapse={ordersWindow.collapse}
                />
              </div>
            ) : (
              <TelegramEmptyState
                title="Заказы ещё не загружены"
                actionLabel="Загрузить"
                onAction={() => void loadOrders()}
              />
            )}
          </AdminSectionCard>
        </div>
      ) : null}

      <AdminPromptModal
        open={fulfillModalOpen}
        title="Принудительно исполнить заказ"
        submitLabel="Зачислить вручную"
        busy={loading}
        values={fulfillForm}
        fields={[
          { key: "order_id", label: "ID заказа" },
          { key: "reason", label: "Причина" },
        ]}
        onChange={(key, value) => {
          setFulfillForm((prev) => ({ ...prev, [key]: value }));
        }}
        onClose={() => setFulfillModalOpen(false)}
        onSubmit={() => void forceFulfillOrder()}
      />
 
    </AdminPage>
  );
}
