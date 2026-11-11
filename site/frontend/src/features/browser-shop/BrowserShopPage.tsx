import { publicRuntimeValue } from "../../lib/public-runtime";
import React, { useContext, useEffect, useMemo, useRef, useState } from "react";
import { LayoutContext } from "../../components/Layout";
import { useRouter } from "next/router";
import { Button } from "../../components/ui/Button";
import { RouteSkeleton } from "../../components/ui/RouteSkeleton";
import { useT } from "../../hooks/useT";
import { useSnapshot } from "../../hooks/useSnapshot";
import { useCurrentAccountBalances } from "../../hooks/useCurrentAccountBalances";
import {
  useBrowserShopAccessKey,
  useBrowserShopBootstrap,
  useBrowserShopCatalog,
  useBrowserShopCreateIntent,
  useBrowserShopEfhcPurchase,
  useBrowserShopIntentStatus,
  useBrowserShopProfile,
} from "../../queries/useBrowserShop";
import { normalizeTonConnectTx } from "./browserShopTonTx";
import { BrowserShopPreSignChecklist } from "./BrowserShopPreSignChecklist";
import { buildUsdtTransferPlanFromBrowserShopIntent } from "../../lib/ton/browser-shop-intent";
import { buildJettonTransferTonConnectTx, resolveSenderJettonWallet } from "../../lib/ton/jetton-transfer-builder";
import { isGenesisTestRuntime } from "../../lib/ton/testnet-guard";
import type {
  BrowserShopCatalogItem,
  BrowserShopProfileOrder,
  BrowserShopProfileWallet,
  PaymentIntentStatusResponse,
} from "../../lib/api/generated/economicUserSeams";
import type { DbId } from "../../types/db-id";
import {
  useWalletProvider,
  type PreparedWalletProof,
  type WalletTransactionPhase,
} from "../../lib/wallet-provider";
import { useAuthState } from "../../hooks/auth/useAuthState";
import { newIdempotencyKey } from "../../lib/idempotency";
import { ApiError } from "../../lib/api";
import { makePrimaryWallet } from "../../services/profile.service";
import {
  primaryLinkedWallet,
  routePrimaryWalletExecution,
  sameTonAddress,
  type PrimaryWalletExecutionReason,
} from "../../lib/wallet-provider/primaryWalletRouting";

const TOKEN_KEY = "efhc.browserShop.token.v1";
const SKU_KEY = "efhc.browserShop.sku.v1";
const METHOD_KEY = "efhc.browserShop.method.v1";
const VIP_NUMBER_PAGE = 100;
const ORDERS_PAGE = 20;
const VIP_0000_IMAGE = "/assets/efhc/efhc_vip_nft_0000.jpg";

type PayMethod = "TON" | "USDT" | "EFHC";
export type ShopPageView = "shop" | "orders" | "profile";
type VipMode = "any" | "selected";
type InitialContext = { token: string; sku: string; method: PayMethod };
type CheckoutSelection = {
  item: BrowserShopCatalogItem;
  method: PayMethod;
  vipMode?: VipMode;
  vipNumber?: string;
  customEfhcAmountD8?: string;
};
type PaymentUiState = "idle" | "pending" | "checking" | "done" | "error";

const FIXED_EFHC_PACKAGE_AMOUNTS = ["10", "50", "100", "150", "200", "250", "300", "350", "500", "750", "1000", "1500", "2000", "2500", "3000"] as const;
const FIXED_EFHC_PACKAGE_AMOUNT_SET = new Set<string>(FIXED_EFHC_PACKAGE_AMOUNTS);
const FIXED_EFHC_PACKAGE_SKU_SET = new Set<string>(FIXED_EFHC_PACKAGE_AMOUNTS.map((amount) => `EFHC_PACKAGE_${amount}`));
const CUSTOM_EFHC_PACKAGE_SKU = "EFHC_PACKAGE_CUSTOM";
const LEGACY_VIP_PAYMENT_SKUS = new Set(["VIP_NFT_TON", "VIP_NFT_USDT", "VIP_NFT_EFHC"]);

function safeSessionRead(key: string): string {
  if (typeof window === "undefined") return "";
  try { return window.sessionStorage.getItem(key) || ""; } catch { return ""; }
}

function readInitialContext(): InitialContext {
  if (typeof window === "undefined") return { token: "", sku: "", method: "TON" };
  const params = new URLSearchParams(window.location.search);
  const fragment = new URLSearchParams(window.location.hash.replace(/^#/, ""));
  const method = params.get("method") || safeSessionRead(METHOD_KEY);
  return {
    token: fragment.get("token") || params.get("token") || safeSessionRead(TOKEN_KEY),
    sku: params.get("sku") || safeSessionRead(SKU_KEY),
    method: method === "USDT" ? "USDT" : method === "EFHC" ? "EFHC" : "TON",
  };
}

function rememberCheckout(token: string, sku: string, method: PayMethod) {
  if (typeof window === "undefined") return;
  try {
    if (token) window.sessionStorage.setItem(TOKEN_KEY, token);
    if (sku) window.sessionStorage.setItem(SKU_KEY, sku);
    window.sessionStorage.setItem(METHOD_KEY, method);
  } catch {
    // Browser privacy modes may deny storage.
  }
  const url = new URL(window.location.href);
  url.searchParams.delete("token");
  const fragment = new URLSearchParams(url.hash.replace(/^#/, ""));
  fragment.delete("token");
  url.hash = fragment.toString() ? `#${fragment.toString()}` : "";
  if (sku) url.searchParams.set("sku", sku);
  url.searchParams.set("method", method);
  window.history.replaceState({}, "", url.toString());
}

function checkoutReturnUrl(rawUrl: string, sku: string, method: PayMethod): string {
  const url = new URL(rawUrl, typeof window === "undefined" ? "https://efhc.invalid" : window.location.href);
  const fragment = new URLSearchParams(url.hash.replace(/^#/, ""));
  const accessToken = fragment.get("token") || url.searchParams.get("token");
  url.searchParams.delete("token");
  if (accessToken) fragment.set("token", accessToken);
  url.hash = fragment.toString() ? `#${fragment.toString()}` : "";
  if (sku) url.searchParams.set("sku", sku);
  url.searchParams.set("method", method);
  return url.toString();
}

function openExternal(url: string) {
  if (typeof window === "undefined") return;
  const tg = (globalThis as any)?.Telegram?.WebApp;
  if (typeof tg?.openLink === "function") { tg.openLink(url); return; }
  window.open(url, "_blank", "noopener,noreferrer");
}

function itemType(item: BrowserShopCatalogItem): string {
  return String(item.item_type || "").trim().toUpperCase();
}
function isVipAnyItem(item: BrowserShopCatalogItem): boolean { return itemType(item) === "NFT_VIP"; }
function isVipSelectedPriceItem(item: BrowserShopCatalogItem): boolean { return itemType(item) === "NFT_VIP_SELECTED_PRICE"; }
function isVipNumberItem(item: BrowserShopCatalogItem): boolean { return itemType(item) === "NFT_VIP_NUMBER"; }
function isPublished(item: BrowserShopCatalogItem): boolean {
  return !["draft", "hidden", "archived", "inactive", "sold"].includes(String(item.status || "live").trim().toLowerCase());
}
function vipNumberFromItem(item: BrowserShopCatalogItem): string {
  for (const candidate of [item.sku, item.title]) {
    const match = String(candidate || "").match(/(?:^|[_#\s-])(\d{4})$/);
    if (match && match[1] !== "0000") return match[1];
  }
  return "";
}
function wholeEfhcPackageAmount(value: unknown): string | null {
  const match = String(value ?? "").trim().match(/^(\d+)(?:\.(\d{1,8}))?$/);
  if (!match || (match[2] && /[1-9]/.test(match[2]))) return null;
  const whole = match[1].replace(/^0+(?=\d)/, "");
  try { return BigInt(whole) > 0n ? whole : null; } catch { return null; }
}
function fixedEfhcPackageSlot(item: BrowserShopCatalogItem): string | null {
  const sku = String(item.sku || "").trim().toUpperCase();
  if (FIXED_EFHC_PACKAGE_SKU_SET.has(sku)) return sku.replace(/^EFHC_PACKAGE_/, "");
  const legacyQuantity = wholeEfhcPackageAmount(item.quantity_efhc);
  return legacyQuantity && FIXED_EFHC_PACKAGE_AMOUNT_SET.has(legacyQuantity) ? legacyQuantity : null;
}
function isCustomEfhcPackage(item: BrowserShopCatalogItem): boolean {
  return itemType(item) === "EFHC_PACKAGE" && String(item.sku || "").trim().toUpperCase() === CUSTOM_EFHC_PACKAGE_SKU;
}
function isCanonicalFixedEfhcPackage(item: BrowserShopCatalogItem): boolean {
  return itemType(item) !== "EFHC_PACKAGE" || isCustomEfhcPackage(item) || Boolean(fixedEfhcPackageSlot(item));
}
function normalizedCustomEfhcWhole(value: unknown): string | null {
  const raw = String(value ?? "").trim();
  if (!/^\d+$/.test(raw)) return null;
  const whole = raw.replace(/^0+(?=\d)/, "");
  try { return BigInt(whole) > 0n ? whole : null; } catch { return null; }
}
function customEfhcAmountD8(value: unknown): string | null {
  const whole = normalizedCustomEfhcWhole(value);
  return whole ? `${whole}.00000000` : null;
}
function multiplyD2ByWhole(rate: unknown, amount: unknown): string | null {
  const rateText = String(rate ?? "").trim().replace(",", ".");
  const amountText = normalizedCustomEfhcWhole(amount);
  const match = rateText.match(/^(\d+)(?:\.(\d{1,2}))?$/);
  if (!match || !amountText) return null;
  try {
    const cents = BigInt(match[1]) * 100n + BigInt((match[2] || "").padEnd(2, "0"));
    if (cents <= 0n) return null;
    const total = cents * BigInt(amountText);
    return `${total / 100n}.${String(total % 100n).padStart(2, "0")}`;
  } catch { return null; }
}
function positiveFixedPoint(value: unknown, decimals: number): boolean {
  const text = String(value ?? "").trim().replace(",", ".");
  const match = text.match(new RegExp(`^(\\d+)(?:\\.(\\d{1,${decimals}}))?$`));
  if (!match) return false;
  const fraction = (match[2] || "").padEnd(decimals, "0");
  try { return BigInt(`${match[1]}${fraction}`) > 0n; } catch { return false; }
}
function methodAllowed(item: BrowserShopCatalogItem, method: PayMethod): boolean {
  if (method === "EFHC" && itemType(item) === "EFHC_PACKAGE") return false;
  const price = item.methods?.[method]?.price;
  return method === "EFHC" ? positiveFixedPoint(price, 8) : positiveFixedPoint(price, 2);
}
function methodLabel(method: PayMethod): string { return method === "TON" ? "TON / GRAM" : method; }
function priceLabel(item: BrowserShopCatalogItem, method: PayMethod): string {
  const price = String(item.methods?.[method]?.price || "").trim();
  return price ? `${methodLabel(method)} ${price}` : "—";
}
function priceAmountOnly(item: BrowserShopCatalogItem, method: PayMethod): string {
  return String(item.methods?.[method]?.price || "").trim() || "—";
}
function customRateLabel(item: BrowserShopCatalogItem, method: PayMethod): string {
  const rate = String(item.methods?.[method]?.price || "").trim();
  return rate ? `${methodLabel(method)} ${rate} / 1 EFHCm` : "—";
}
function customTotalLabel(item: BrowserShopCatalogItem, method: PayMethod, amountD8?: string): string {
  const amount = normalizedCustomEfhcWhole(String(amountD8 || "").split(".")[0]);
  const total = multiplyD2ByWhole(item.methods?.[method]?.price, amount);
  return total ? `${methodLabel(method)} ${total}` : "—";
}
function checkoutPriceLabel(selection: CheckoutSelection): string {
  return isCustomEfhcPackage(selection.item)
    ? customTotalLabel(selection.item, selection.method, selection.customEfhcAmountD8)
    : priceLabel(selection.item, selection.method);
}
function shopOrderIdFromUnknown(value: unknown): string {
  if (!value || typeof value !== "object") return "";
  const orderId = (value as Record<string, unknown>).order_id;
  return orderId === null || orderId === undefined ? "" : String(orderId).trim();
}
function isInsufficientEfhcFunds(error: unknown): boolean {
  if (!(error instanceof ApiError)) return false;
  return ["INSUFFICIENT_EFHC_MAIN_BALANCE", "INSUFFICIENT_EFHC_BALANCE", "INSUFFICIENT_FUNDS"]
    .includes(String(error.code || "").trim().toUpperCase());
}
function paymentUiState(status: PaymentIntentStatusResponse | null, creating: boolean): PaymentUiState {
  if (creating) return "pending";
  if (!status) return "idle";
  const raw = String(status.status || "").trim().toUpperCase();
  const product = String(status.flow_truth?.product_state || "").trim();
  if (raw === "CONFIRMED" || product === "terminal_success") return "done";
  if (["EXPIRED", "CANCELED", "FAILED"].includes(raw) || ["terminal_failed", "expired"].includes(product)) return "error";
  return "checking";
}
function formatRemaining(expiresAt: string, nowMs: number): string {
  const expiryMs = Date.parse(expiresAt);
  if (!Number.isFinite(expiryMs)) return "—";
  const seconds = Math.max(0, Math.ceil((expiryMs - nowMs) / 1000));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}
function isPaidOrder(order: BrowserShopProfileOrder): boolean {
  return !["", "PENDING", "UNPAID", "CREATED"].includes(String(order.status || "").trim().toUpperCase());
}
function orderStatusLabel(status: string, tr: (key: string) => string): string {
  const normalized = String(status || "").trim().toUpperCase();
  if (["PAID_PENDING_MANUAL", "PENDING_MANUAL"].includes(normalized)) return tr("portal.browser_shop.status_waiting_issuance");
  if (["FULFILLED", "APPROVED", "ISSUED", "PAID_AUTO"].includes(normalized)) return tr("portal.browser_shop.status_completed");
  if (normalized === "REJECTED") return tr("portal.browser_shop.status_rejected");
  return normalized || tr("portal.browser_shop.status_paid");
}

function walletPrivateSuffix(address: string | null | undefined): string {
  const compact = String(address || "").trim();
  return compact ? compact.slice(-4) : "";
}

const SHOP_CHECKOUT_TABBABLE_SELECTOR = [
  "a[href]",
  "area[href]",
  "button:not([disabled])",
  "input:not([disabled]):not([type=\"hidden\"])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "iframe",
  "[contenteditable=\"true\"]",
  "[tabindex]:not([tabindex=\"-1\"])",
].join(",");

type ShopCheckoutInertSnapshot = { hadAttribute: boolean; value: string | null };

function shopCheckoutTabbables(root: HTMLElement): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>(SHOP_CHECKOUT_TABBABLE_SELECTOR))
    .filter((element) => {
      if (element.matches(":disabled")) return false;
      if (element.closest('[hidden], [aria-hidden="true"]')) return false;
      const style = window.getComputedStyle(element);
      return style.display !== "none" && style.visibility !== "hidden" && element.getClientRects().length > 0;
    })
    .map((element, index) => ({ element, index }))
    .sort((a, b) => {
      const aTabIndex = a.element.tabIndex;
      const bTabIndex = b.element.tabIndex;
      const aPositive = aTabIndex > 0;
      const bPositive = bTabIndex > 0;
      if (aPositive && bPositive && aTabIndex !== bTabIndex) return aTabIndex - bTabIndex;
      if (aPositive !== bPositive) return aPositive ? -1 : 1;
      return a.index - b.index;
    })
    .map(({ element }) => element);
}

function shopRenderedDialogs(): HTMLElement[] {
  return Array.from(document.querySelectorAll<HTMLElement>('[role="dialog"]')).filter((dialog) => {
    if (dialog.closest("[hidden]")) return false;
    const style = window.getComputedStyle(dialog);
    return style.display !== "none" && style.visibility !== "hidden" && dialog.getClientRects().length > 0;
  });
}

function shopCheckoutBackgroundTargets(backdrop: HTMLElement): Set<HTMLElement> {
  const targets = new Set<HTMLElement>();
  let current: HTMLElement = backdrop;
  while (current.parentElement && current.parentElement !== document.documentElement) {
    const parent = current.parentElement;
    for (const child of Array.from(parent.children)) {
      if (child instanceof HTMLElement && child !== current) targets.add(child);
    }
    if (parent === document.body) break;
    current = parent;
  }
  return targets;
}

export default function BrowserShopPage({ view = "shop" }: { view?: ShopPageView }) {
  const t = useT();
  const { lang } = useContext(LayoutContext);
  const localized = (item: BrowserShopCatalogItem, field: "title" | "description", fallback: string): string => {
    const entry = item.translations?.[lang]?.[field];
    return typeof entry === "string" && entry.trim() ? entry : fallback;
  };
  const router = useRouter();
  const activeTab: ShopPageView = view;
  const auth = useAuthState();
  const snapshot = useSnapshot();
  const accountBalances = useCurrentAccountBalances();
  const {
    address: walletAddress,
    listWallets,
    prepareProof,
    connect: connectWallet,
    disconnect: disconnectWallet,
    bindWallet,
    sendTransaction,
    isUserRejected,
  } = useWalletProvider();
  const [visualProof, setVisualProof] = useState(process.env.NEXT_PUBLIC_EFHC_PAGES_PREVIEW !== "1" && process.env.NEXT_PUBLIC_EFHC_OBSERVABILITY_VISUAL_PROOF === "1");
  const [token, setToken] = useState("");
  const [selectedSku, setSelectedSku] = useState("");
  const [globalMethod, setGlobalMethod] = useState<PayMethod>("TON");
  const [activeIntentId, setActiveIntentId] = useState<DbId | null>(null);
  const [createdExpiresAt, setCreatedExpiresAt] = useState("");
  const [localError, setLocalError] = useState("");
  const [localNotice, setLocalNotice] = useState("");
  const [walletTxPhase, setWalletTxPhase] = useState<WalletTransactionPhase>("idle");
  const [nowMs, setNowMs] = useState(Date.now());
  const [efhcVipPurchased, setEfhcVipPurchased] = useState(false);
  const [confirmedOrderId, setConfirmedOrderId] = useState("");
  const [checkout, setCheckout] = useState<CheckoutSelection | null>(null);
  const [pendingWalletPayment, setPendingWalletPayment] = useState<CheckoutSelection | null>(null);
  const [walletChooserOpen, setWalletChooserOpen] = useState(false);
  const walletChooserBackdropRef = useRef<HTMLDivElement>(null);
  const walletChooserDialogRef = useRef<HTMLElement>(null);
  const walletChooserCloseButtonRef = useRef<HTMLButtonElement>(null);
  const walletChooserInitiatorRef = useRef<HTMLElement | null>(null);
  const walletChooserWasOpenRef = useRef(false);
  const walletChooserInertSnapshotsRef = useRef(new Map<HTMLElement, ShopCheckoutInertSnapshot>());
  const [pendingPrimaryPayment, setPendingPrimaryPayment] = useState<CheckoutSelection | null>(null);
  const [tonConnectProofState, setTonConnectProofState] = useState<PreparedWalletProof | null>(null);
  const [tonConnectBindingRequested, setTonConnectBindingRequested] = useState(false);
  const [pendingInitialSessionAddress, setPendingInitialSessionAddress] = useState("");
  const [pendingSawDisconnect, setPendingSawDisconnect] = useState(false);
  const shopBindingAttemptRef = useRef("");
  const [selectedOrder, setSelectedOrder] = useState<BrowserShopProfileOrder | null>(null);
  const orderDetailBackdropRef = useRef<HTMLDivElement>(null);
  const orderDetailDialogRef = useRef<HTMLElement>(null);
  const orderDetailCloseButtonRef = useRef<HTMLButtonElement>(null);
  const orderDetailInitiatorRef = useRef<HTMLElement | null>(null);
  const orderDetailReturnOrderIdRef = useRef("");
  const orderDetailWasOpenRef = useRef(false);
  const orderDetailInertSnapshotsRef = useRef(new Map<HTMLElement, ShopCheckoutInertSnapshot>());
  const [vipSearch, setVipSearch] = useState("");
  const [selectedVipNumber, setSelectedVipNumber] = useState("");
  const [customEfhcAmount, setCustomEfhcAmount] = useState("");
  const [reservedVipNumber, setReservedVipNumber] = useState("");
  const [ordersVisibleCount, setOrdersVisibleCount] = useState(ORDERS_PAGE);
  const checkoutBackdropRef = useRef<HTMLDivElement>(null);
  const checkoutDialogRef = useRef<HTMLElement>(null);
  const checkoutCloseButtonRef = useRef<HTMLButtonElement>(null);
  const checkoutInitiatorRef = useRef<HTMLElement | null>(null);
  const checkoutWasOpenRef = useRef(false);
  const checkoutInertSnapshotsRef = useRef(new Map<HTMLElement, ShopCheckoutInertSnapshot>());

  const bootstrapQ = useBrowserShopBootstrap(token);
  const catalogQ = useBrowserShopCatalog();
  const profileQ = useBrowserShopProfile(token);
  const accessKey = useBrowserShopAccessKey();
  const createIntent = useBrowserShopCreateIntent(token);
  const purchaseEfhc = useBrowserShopEfhcPurchase();
  const statusQ = useBrowserShopIntentStatus(token, activeIntentId);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const restoreContext = () => {
      const restored = readInitialContext();
      setToken(restored.token);
      setSelectedSku(restored.sku);
      setGlobalMethod(restored.method);
    };
    restoreContext();
    // A return to the same checkout URL with an issued token fragment does
    // not reload the document. Consume it through the same restoration path.
    window.addEventListener("hashchange", restoreContext);
    const proofWindow = window as Window & { __EFHC_PUBLIC_VISUAL_PROOF__?: boolean };
    const localHost = ["localhost", "127.0.0.1", "::1"].includes(window.location.hostname);
    if (proofWindow.__EFHC_PUBLIC_VISUAL_PROOF__ === true && navigator.webdriver === true && localHost) setVisualProof(true);
    return () => window.removeEventListener("hashchange", restoreContext);
  }, []);

  const proofBootstrap = visualProof ? {
    mode: "handoff_bound" as const, tg_linked: true, global_id: "0000001568", wallet_linked: true,
    active_wallet_address: "EQ_VISUAL_PROOF", wallets: [], wallet_sync_required: false,
    bot_open_url: null, telegram_sync_url: null, wallet_sync_url: null,
    storefront_mode: "browser_shop_mvp" as const, access_mode: "telegram_handoff" as const,
    future_game_entry_enabled: false, available_modules: ["catalog", "checkout"],
    flow_truth: null, active_payment: null, intent_history: [],
  } : null;
  const proofCatalog: BrowserShopCatalogItem[] = visualProof ? [
    ...FIXED_EFHC_PACKAGE_AMOUNTS.map((amountText, index) => {
      const amount = Number(amountText);
      return {
        sku: `EFHC_PACKAGE_${amount}`, title: `${amount} EFHCm`, description: t("portal.browser_shop.package_default_subtitle"),
        item_type: "EFHC_PACKAGE", ton_enabled: true, usdt_enabled: true,
        methods: { TON: { price: `${index + 1}.00` }, USDT: { price: (amount * 0.3).toFixed(2) } },
        image_url: null, status: "live", action_mode: "checkout", delivery_mode: "bank_credit",
        quantity_efhc: `${amount}.00000000`, sort_order: amount,
      };
    }),
    {
      sku: CUSTOM_EFHC_PACKAGE_SKU, title: t("portal.browser_shop.custom_exchange_title"), description: t("portal.browser_shop.custom_exchange_detail"),
      item_type: "EFHC_PACKAGE", ton_enabled: true, usdt_enabled: true,
      methods: { TON: { price: "0.01" }, USDT: { price: "0.30" } },
      image_url: null, status: "live", action_mode: "checkout", delivery_mode: "bank_credit",
      quantity_efhc: null, sort_order: 1500,
    },
    {
      sku: "EFHC_VIP_NFT_ANY", title: "EFHC VIP NFT", description: t("portal.browser_shop.nft_waiting_delivery_short"),
      item_type: "NFT_VIP", ton_enabled: true, usdt_enabled: true,
      methods: { TON: { price: "100.00" }, USDT: { price: "150.00" }, EFHC: { price: "500.00000000" } },
      image_url: VIP_0000_IMAGE, status: "live", action_mode: "checkout", delivery_mode: "manual",
      quantity_efhc: null, sort_order: 2000,
    },
    {
      sku: "EFHC_VIP_NFT_SELECTED_PRICE", title: t("portal.browser_shop.vip_selected_price_title"), description: null,
      item_type: "NFT_VIP_SELECTED_PRICE", ton_enabled: true, usdt_enabled: true,
      methods: { TON: { price: "100.00" }, USDT: { price: "150.00" }, EFHC: { price: "750.00000000" } },
      status: "live", quantity_efhc: null, sort_order: 2010,
    },
    ...Array.from({ length: 130 }, (_, index) => {
      const number = String(index + 1).padStart(4, "0");
      return {
        sku: `EFHC_VIP_NFT_NUMBER_${number}`, title: `EFHC VIP NFT #${number}`, description: null,
        item_type: "NFT_VIP_NUMBER", ton_enabled: true, usdt_enabled: true,
        methods: { TON: { price: "100.00" }, USDT: { price: "150.00" }, EFHC: { price: "750.00000000" } },
        status: "live", quantity_efhc: null, sort_order: 2100 + index,
      };
    }),
  ] : [];
  const bootstrap = proofBootstrap || bootstrapQ.data || null;
  const catalogSource = proofCatalog.length ? proofCatalog : catalogQ.data || [];
  const publishedCatalog = useMemo(() => catalogSource
    .filter(isPublished)
    .filter(isCanonicalFixedEfhcPackage)
    .filter((item) => !LEGACY_VIP_PAYMENT_SKUS.has(String(item.sku || "").trim().toUpperCase())), [catalogSource]);
  const packageCatalog = useMemo(
    () => publishedCatalog.filter((item) => itemType(item) === "EFHC_PACKAGE").sort((a, b) => Number(a.sort_order || 0) - Number(b.sort_order || 0)),
    [publishedCatalog],
  );
  const vipAnyItem = useMemo(() => publishedCatalog.find(isVipAnyItem) || null, [publishedCatalog]);
  const vipSelectedPriceItem = useMemo(() => publishedCatalog.find(isVipSelectedPriceItem) || null, [publishedCatalog]);
  const vipNumberItems = useMemo(() => {
    const seen = new Set<string>();
    return publishedCatalog.filter(isVipNumberItem).map((item) => ({ item, number: vipNumberFromItem(item) }))
      .filter((entry) => {
        if (!entry.number || seen.has(entry.number)) return false;
        seen.add(entry.number); return true;
      }).sort((a, b) => a.number.localeCompare(b.number));
  }, [publishedCatalog]);
  const visibleVipNumbers = useMemo(() => {
    const query = vipSearch.trim().toLowerCase();
    return vipNumberItems.filter((entry) => !query || entry.number.includes(query) || entry.item.sku.toLowerCase().includes(query)).slice(0, VIP_NUMBER_PAGE);
  }, [vipNumberItems, vipSearch]);

  const flowTruth = bootstrap?.flow_truth || null;
  const readinessState = String(flowTruth?.readiness_state || "");
  const walletSyncRequired = readinessState === "wallet_sync_required" || Boolean(bootstrap?.wallet_sync_required);
  const resumeIntent = flowTruth?.next_step === "resume_intent";
  const actionDenied = Boolean(flowTruth?.action_denied);
  const canonicalCenter = flowTruth?.canonical_center || "web_profile";
  const activeStatus = statusQ.data || bootstrap?.active_payment || null;
  const state = paymentUiState(activeStatus, createIntent.isPending);
  const expiresAt = activeStatus?.expires_at || createdExpiresAt;
  const ttl = expiresAt ? formatRemaining(expiresAt, nowMs) : "";

  useEffect(() => {
    if (!bootstrap?.active_payment || activeIntentId) return;
    setActiveIntentId(bootstrap.active_payment.id);
  }, [activeIntentId, bootstrap?.active_payment]);
  useEffect(() => { rememberCheckout(token, selectedSku, globalMethod); }, [globalMethod, selectedSku, token]);
  useEffect(() => {
    if (!expiresAt || ["done", "error"].includes(state)) return;
    const id = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [expiresAt, state]);
  useEffect(() => {
    if (state !== "done") return;
    setLocalError(""); setLocalNotice("");
    // Intent creation fetched the profile before Watcher confirmation. Shared
    // query defaults do not refetch it when the orders page mounts.
    void profileQ.refetch();
    const orderId = activeStatus?.flow_truth?.order_id;
    if (orderId !== null && orderId !== undefined) {
      setConfirmedOrderId(String(orderId));
      // OWNER v224: после подтверждённой покупки сразу открыть отдельную страницу «Мои заказы».
      if (router.pathname !== "/browser-shop/orders") void router.push("/browser-shop/orders");
    }
  }, [activeStatus?.flow_truth?.order_id, profileQ.refetch, router, state]);
  useEffect(() => {
    if (String(activeStatus?.status || "").trim().toUpperCase() !== "EXPIRED") return;
    setSelectedVipNumber("");
    setReservedVipNumber("");
    setCheckout(null);
    setLocalNotice(t("portal.browser_shop.reservation_expired"));
  }, [activeStatus?.status]);

  const loading = !visualProof && (catalogQ.isLoading || (Boolean(token) && (bootstrapQ.isLoading || profileQ.isLoading)));
  const loadError = visualProof ? null : catalogQ.error || (Boolean(token) ? bootstrapQ.error || profileQ.error : null);
  const accountLinked = visualProof || auth.authenticated || Boolean(token && (profileQ.data?.global_id || bootstrap?.global_id));
  const linkedGlobalId = visualProof ? "0000001568" : profileQ.data?.global_id || bootstrap?.global_id || auth.globalId || "";
  const walletLinked = visualProof || Boolean(token && bootstrap?.wallet_linked && !walletSyncRequired);
  const mainBalance = visualProof ? "1250.00000000"
    : auth.authenticated && linkedGlobalId && accountBalances.data?.global_id === linkedGlobalId
      ? accountBalances.data.main_balance
      : snapshot.snap?.profile.main_balance || "—";
  const username = visualProof ? "EFHC Player" : snapshot.snap?.profile.username || (linkedGlobalId ? `ID ${linkedGlobalId}` : "EFHC");
  const paidOrders = useMemo(
    () => (profileQ.data?.orders || []).filter(isPaidOrder).sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at)),
    [profileQ.data?.orders],
  );
  const linkedWalletChoices = useMemo(
    () => (profileQ.data?.wallets || []).filter((wallet: BrowserShopProfileWallet) => wallet.is_active && wallet.proof_verified && Boolean(String(wallet.wallet_address || "").trim())),
    [profileQ.data?.wallets],
  );
  const selectedPaymentWallet = primaryLinkedWallet(linkedWalletChoices);
  const paymentWalletAddress = selectedPaymentWallet?.wallet_address || "";
  const primaryPaymentSessionReady = Boolean(
    selectedPaymentWallet
    && sameTonAddress(walletAddress, selectedPaymentWallet.wallet_address),
  );

  useEffect(() => {
    if (!pendingPrimaryPayment || !primaryPaymentSessionReady) return;
    const queued = pendingPrimaryPayment;
    setPendingPrimaryPayment(null);
    setPendingInitialSessionAddress("");
    setPendingSawDisconnect(false);
    void executePayment(queued);
  }, [pendingPrimaryPayment, primaryPaymentSessionReady]);

  useEffect(() => {
    if ((!pendingPrimaryPayment && !tonConnectBindingRequested) || selectedPaymentWallet || !walletAddress) return;
    const linked = linkedWalletChoices.find((wallet) => (
      sameTonAddress(wallet.wallet_address, walletAddress)
    ));
    const attemptKey = `${walletAddress}:${linked ? String(linked.id) : "bind"}`;
    if (shopBindingAttemptRef.current === attemptKey) return;

    if (linked) {
      shopBindingAttemptRef.current = attemptKey;
      void makePrimaryWallet(linked.id)
        .then(() => {
          setTonConnectBindingRequested(false);
          return Promise.all([profileQ.refetch(), bootstrapQ.refetch()]);
        })
        .catch(() => {
          shopBindingAttemptRef.current = "";
          setLocalError(t("portal.browser_shop.wallet_address_select_failed"));
        });
      return;
    }
    if (!tonConnectProofState) return;
    shopBindingAttemptRef.current = attemptKey;
    void bindWallet(tonConnectProofState)
      .then((bound) => {
        if (!bound?.is_connected) throw new Error("WALLET_BIND_FAILED");
        setTonConnectBindingRequested(false);
        return Promise.all([profileQ.refetch(), bootstrapQ.refetch()]);
      })
      .catch(() => {
        shopBindingAttemptRef.current = "";
        setTonConnectBindingRequested(false);
        setPendingPrimaryPayment(null);
        setWalletTxPhase("error");
        setLocalError(t("wallet.proof_failed"));
      });
  }, [
    bindWallet,
    bootstrapQ,
    linkedWalletChoices,
    pendingPrimaryPayment,
    tonConnectBindingRequested,
    profileQ,
    selectedPaymentWallet,
    t,
    tonConnectProofState,
    walletAddress,
  ]);

  useEffect(() => {
    if (!pendingPrimaryPayment || primaryPaymentSessionReady) return;
    if (!walletAddress) {
      setPendingSawDisconnect(true);
      return;
    }
    if (
      selectedPaymentWallet
      && (pendingSawDisconnect || !pendingInitialSessionAddress)
    ) {
      setPendingPrimaryPayment(null);
      setWalletTxPhase("error");
      setLocalError(t("wallet.primary_mismatch"));
    }
  }, [
    pendingInitialSessionAddress,
    pendingPrimaryPayment,
    pendingSawDisconnect,
    primaryPaymentSessionReady,
    selectedPaymentWallet,
    t,
    walletAddress,
  ]);

  const pendingIntentVisible = Boolean(activeStatus && !["done", "error"].includes(state));
  const nftPaymentConfirmed = Boolean(
    selectedSku && publishedCatalog.find((item) => item.sku === selectedSku && itemType(item) !== "EFHC_PACKAGE") && state === "done",
  ) || efhcVipPurchased;

  function openWebProfile() {
    rememberCheckout(token, selectedSku, globalMethod);
    const returnTo = typeof window === "undefined" ? "/browser-shop" : window.location.pathname + window.location.search;
    void router.push(`/web-profile?return_to=${encodeURIComponent(returnTo)}`);
  }
  async function linkWebAccount(selection?: CheckoutSelection) {
    setLocalError(""); setLocalNotice("");
    if (selection) { setSelectedSku(selection.item.sku); setGlobalMethod(selection.method); }
    if (!auth.authenticated) { openWebProfile(); return; }
    try {
      const out = await accessKey.mutateAsync();
      const sku = selection?.item.sku || selectedSku;
      const method = selection?.method || globalMethod;
      window.location.assign(checkoutReturnUrl(out.redirect_url, sku, method));
    } catch { setLocalError(t("portal.browser_shop.open_from_hub_detail")); }
  }
  function openTelegramLink() {
    const url = bootstrap?.telegram_sync_url || bootstrap?.bot_open_url || "";
    if (!url) return; rememberCheckout(token, selectedSku, globalMethod); openExternal(url);
  }
  function syncWallet() {
    const url = bootstrap?.wallet_sync_url || bootstrap?.telegram_sync_url || bootstrap?.bot_open_url || "";
    if (!url) return; rememberCheckout(token, selectedSku, globalMethod); openExternal(url);
  }
  async function copyConfirmedOrderId() {
    if (!confirmedOrderId) return;
    try { await navigator.clipboard.writeText(confirmedOrderId); setLocalNotice(t("portal.browser_shop.order_id_copied")); }
    catch { setLocalError(t("portal.browser_shop.order_id_copy_failed")); }
  }
  function navigateShopPage(page: ShopPageView) {
    const path = page === "orders" ? "/browser-shop/orders" : page === "profile" ? "/browser-shop/profile" : "/browser-shop";
    rememberCheckout(token, selectedSku, globalMethod);
    void router.push(path);
  }
  function chooseGlobalMethod(method: PayMethod) { setGlobalMethod(method); rememberCheckout(token, selectedSku, method); }
  function openCheckout(selection: CheckoutSelection) {
    setSelectedSku(selection.item.sku); setGlobalMethod(selection.method); setCheckout(selection); setLocalError(""); setLocalNotice("");
  }
  function openOrderDetail(order: BrowserShopProfileOrder, initiator: HTMLElement | null) {
    orderDetailInitiatorRef.current = initiator;
    orderDetailReturnOrderIdRef.current = String(order.id);
    setSelectedOrder(order);
  }
  function closeOrderDetail() {
    setSelectedOrder(null);
  }
  function openCustomExchange(item: BrowserShopCatalogItem) {
    setCustomEfhcAmount("");
    openCheckout({ item, method: globalMethod });
  }
  function updateCustomExchangeAmount(value: string) {
    const normalized = /^\d*$/.test(value) ? value.replace(/^0+(?=\d)/, "") : customEfhcAmount;
    setCustomEfhcAmount(normalized);
    const amountD8 = customEfhcAmountD8(normalized);
    setCheckout((current) => current && isCustomEfhcPackage(current.item)
      ? { ...current, customEfhcAmountD8: amountD8 || undefined }
      : current);
  }
  function openVipNumberCheckout() {
    const selected = vipNumberItems.find((entry) => entry.number === selectedVipNumber);
    if (!selected) { setLocalError(t("portal.browser_shop.choose_vip_number_error")); return; }
    if (!methodAllowed(selected.item, globalMethod)) { setLocalError(t("portal.browser_shop.selected_price_missing")); return; }
    openCheckout({ item: selected.item, method: globalMethod, vipMode: "selected", vipNumber: selected.number });
  }
  function closeWalletChooser() {
    setWalletChooserOpen(false);
    setPendingWalletPayment(null);
  }
  function openWalletChooser(selection: CheckoutSelection | null) {
    if (selection) setPendingWalletPayment(selection);
    setLocalError("");
    if (!linkedWalletChoices.length) {
      setPendingWalletPayment(null);
      if (selection) {
        setPendingPrimaryPayment(selection);
        setPendingInitialSessionAddress(walletAddress);
        setPendingSawDisconnect(!String(walletAddress || "").trim());
      }
      setTonConnectBindingRequested(true);
      void openTonConnectExecutionChooser("no_primary");
      return;
    }
    setWalletChooserOpen(true);
  }
  async function chooseLinkedWallet(wallet: BrowserShopProfileWallet) {
    setLocalError("");
    try {
      // OWNER v223: выбор кошелька в Shop = смена основного кошелька всего EFHC-аккаунта.
      await makePrimaryWallet(wallet.id);
      await Promise.all([profileQ.refetch(), bootstrapQ.refetch()]);
      setWalletChooserOpen(false);
      setLocalNotice(t("portal.browser_shop.payment_wallet_selected"));
      const queued = pendingWalletPayment;
      setPendingWalletPayment(null);
      if (queued) setCheckout(queued);
    } catch {
      setLocalError(t("portal.browser_shop.wallet_address_select_failed"));
    }
  }

  async function openTonConnectExecutionChooser(
    reason: PrimaryWalletExecutionReason,
  ) {
    if (reason === "primary_transport_unavailable") {
      setLocalError(t("wallet.primary_transport_fallback"));
    } else {
      setLocalError("");
    }
    const requireProof = reason === "no_primary";
    if (requireProof) setTonConnectBindingRequested(true);
    const proof = requireProof
      ? await prepareProof().catch(() => null)
      : null;
    setTonConnectProofState(proof);
    // A new account binding must have a fresh, server-authorized challenge.
    // Keep checkout visible so a failed challenge does not strand payment.
    if (requireProof && !proof) {
      setTonConnectBindingRequested(false);
      setPendingPrimaryPayment(null);
      setWalletTxPhase("error");
      setLocalError(t("wallet.restore_requires_proof"));
      return;
    }
    try {
      // Close the local checkout overlay so it cannot mark the official
      // wallet modal portal inert. Preserve pending intent for verification.
      setCheckout(null);
      await connectWallet();
    } catch (caught) {
      setTonConnectBindingRequested(false);
      setPendingPrimaryPayment(null);
      setWalletTxPhase(isUserRejected(caught) ? "rejected" : "error");
      setLocalError(t(isUserRejected(caught)
        ? "wallet.connection_rejected"
        : "wallet.connection_failed"));
    }
  }


  async function performExternalPayment(
    selection: CheckoutSelection,
    primary: BrowserShopProfileWallet,
  ) {
    const { item, method } = selection;
    const expectedAddress = String(primary.wallet_address || "").trim();
    if (!expectedAddress || !sameTonAddress(walletAddress, expectedAddress)) {
      setWalletTxPhase("error");
      setLocalError(t("wallet.primary_mismatch"));
      return;
    }
    try {
      const parsed = await createIntent.mutateAsync({
        token,
        sku: item.sku,
        quantity: 1,
        pay_method: method,
        custom_efhc_amount_d8: isCustomEfhcPackage(item) ? selection.customEfhcAmountD8 || null : null,
        client_nonce: globalThis.crypto?.randomUUID?.(),
      });
      setActiveIntentId(parsed.intent_id); setCreatedExpiresAt(parsed.expires_at);
      if (selection.vipNumber) setReservedVipNumber(selection.vipNumber);
      setCheckout(null);
      let tx = normalizeTonConnectTx(parsed.tonconnect_tx);
      if (method === "USDT") {
        const plan = buildUsdtTransferPlanFromBrowserShopIntent(parsed, {
          senderOwnerAddress: expectedAddress,
          recipientPolicy: { strategy: "owner_derived_wallet", ownerAddress: parsed.to_wallet },
        });
        const endpoint = publicRuntimeValue("NEXT_PUBLIC_TON_RPC_ENDPOINT")
          || (isGenesisTestRuntime()
            ? "https://testnet.toncenter.com/api/v2/jsonRPC"
            : "https://toncenter.com/api/v2/jsonRPC");
        const senderJettonWallet = await resolveSenderJettonWallet({ endpoint, ownerAddress: expectedAddress, jettonMasterAddress: plan.jettonMasterAddress });
        tx = buildJettonTransferTonConnectTx(plan, senderJettonWallet);
      }
      if (!tx) throw new Error("WALLET_TX_MISSING");
      if (!sameTonAddress(walletAddress, expectedAddress)) {
        throw new Error("PRIMARY_WALLET_MISMATCH");
      }
      setWalletTxPhase("signing"); await sendTransaction(tx); setWalletTxPhase("signed");
    } catch (caught) {
      if (caught instanceof Error && caught.message === "PRIMARY_WALLET_MISMATCH") {
        setWalletTxPhase("error");
        setLocalError(t("wallet.primary_mismatch"));
      } else if (isUserRejected(caught)) {
        setWalletTxPhase("rejected");
        setLocalError(t("wallet.transaction_rejected"));
      } else {
        setWalletTxPhase("error");
        setLocalError(t("wallet.transaction_failed"));
      }
    }
  }

  async function executePayment(selection: CheckoutSelection) {
    const { item, method } = selection;
    setSelectedSku(item.sku); rememberCheckout(token, item.sku, method);
    setLocalError(""); setLocalNotice(""); setWalletTxPhase("idle"); setEfhcVipPurchased(false); setConfirmedOrderId("");
    const vip = itemType(item) !== "EFHC_PACKAGE";
    if (vip && !token) { await linkWebAccount(selection); return; }
    if (vip && walletSyncRequired && linkedWalletChoices.length > 0) {
      setLocalError(t("portal.browser_shop.wallet_sync_detail")); return;
    }
    if (method === "EFHC") {
      if (!vip) { setLocalError(t("portal.browser_shop.efhc_vip_only")); return; }
      if (!auth.authenticated || !auth.globalId) { setLocalError(t("portal.browser_shop.efhc_auth_required")); return; }
      const handoffGlobalId = String(bootstrap?.global_id || "").trim();
      if (handoffGlobalId && handoffGlobalId !== String(auth.globalId)) { setLocalError(t("portal.browser_shop.efhc_auth_mismatch")); return; }
      try {
        const result = await purchaseEfhc.mutateAsync({ sku: item.sku, quantity: 1, idempotencyKey: newIdempotencyKey() });
        const orderId = shopOrderIdFromUnknown(result);
        setConfirmedOrderId(orderId); setEfhcVipPurchased(true);
        if (selection.vipNumber) setReservedVipNumber(selection.vipNumber);
        setCheckout(null);
        // OWNER v224: подтверждённый ShopOrder сразу показываем в отдельном журнале заказов.
        if (orderId) void router.push("/browser-shop/orders");
      } catch (caught) {
        if (isInsufficientEfhcFunds(caught)) setLocalNotice(t("portal.browser_shop.insufficient_funds"));
        else setLocalError(t("portal.browser_shop.efhc_purchase_failed"));
      }
      return;
    }
    if (!token) { await linkWebAccount(selection); return; }
    if (walletSyncRequired && linkedWalletChoices.length > 0) { setLocalError(t("portal.browser_shop.wallet_sync_detail")); return; }

    try {
      await routePrimaryWalletExecution({
        wallets: linkedWalletChoices,
        currentSessionAddress: walletAddress,
        listWallets,
        connectWallet,
        disconnectWallet,
        markPending: () => {
          setPendingPrimaryPayment(selection);
          setPendingInitialSessionAddress(walletAddress);
          setPendingSawDisconnect(!String(walletAddress || "").trim());
        },
        openChooser: openTonConnectExecutionChooser,
        execute: async (primary) => {
          setPendingPrimaryPayment(null);
          await performExternalPayment(selection, primary);
        },
      });
    } catch (caught) {
      setPendingPrimaryPayment(null);
      if (isUserRejected(caught)) {
        setWalletTxPhase("rejected");
        setLocalError(t("wallet.transaction_rejected"));
      } else {
        setWalletTxPhase("error");
        setLocalError(t("wallet.connection_failed"));
      }
    }
  }
  async function payCheckout() {
    if (!checkout) return;
    await executePayment(checkout);
  }

  const busy = createIntent.isPending || purchaseEfhc.isPending || walletTxPhase === "signing" || state === "checking" || state === "pending" || actionDenied || resumeIntent;
  const checkoutOpen = Boolean(checkout);

  useEffect(() => {
    if (typeof document === "undefined") return;
    if (checkoutOpen && !checkoutWasOpenRef.current) {
      checkoutInitiatorRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      const initialTarget =
        checkoutDialogRef.current?.querySelector<HTMLElement>("[data-shop-checkout-initial-focus]") ??
        checkoutCloseButtonRef.current;
      initialTarget?.focus({ preventScroll: true });
    }
    if (!checkoutOpen && checkoutWasOpenRef.current) {
      const initiator = checkoutInitiatorRef.current;
      checkoutInitiatorRef.current = null;
      if (initiator?.isConnected) initiator.focus({ preventScroll: true });
    }
    checkoutWasOpenRef.current = checkoutOpen;
  }, [checkoutOpen]);

  useEffect(() => {
    if (typeof document === "undefined") return;
    const snapshots = checkoutInertSnapshotsRef.current;
    const restoreElement = (element: HTMLElement, snapshot: ShopCheckoutInertSnapshot) => {
      if (snapshot.hadAttribute) element.setAttribute("inert", snapshot.value ?? "");
      else element.removeAttribute("inert");
    };
    const restoreAll = () => {
      for (const [element, snapshot] of snapshots) restoreElement(element, snapshot);
      snapshots.clear();
    };
    const sync = () => {
      const backdrop = checkoutBackdropRef.current;
      const dialog = checkoutDialogRef.current;
      const topDialog = shopRenderedDialogs().at(-1) ?? null;
      const desired = checkoutOpen && backdrop && dialog && topDialog === dialog
        ? shopCheckoutBackgroundTargets(backdrop)
        : new Set<HTMLElement>();
      for (const [element, snapshot] of snapshots) {
        if (desired.has(element)) continue;
        restoreElement(element, snapshot);
        snapshots.delete(element);
      }
      for (const element of desired) {
        if (!snapshots.has(element)) snapshots.set(element, { hadAttribute: element.hasAttribute("inert"), value: element.getAttribute("inert") });
        element.setAttribute("inert", "");
      }
    };
    if (!checkoutOpen) { restoreAll(); return; }
    sync();
    const observer = new MutationObserver(sync);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => { observer.disconnect(); restoreAll(); };
  }, [checkoutOpen, walletChooserOpen]);

  useEffect(() => {
    if (!checkoutOpen || typeof document === "undefined") return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Tab" && event.key !== "Escape") return;
      const dialog = checkoutDialogRef.current;
      if (!dialog || shopRenderedDialogs().at(-1) !== dialog) return;
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        if (!busy) setCheckout(null);
        return;
      }
      const tabbables = shopCheckoutTabbables(dialog);
      if (tabbables.length === 0) {
        event.preventDefault();
        dialog.focus({ preventScroll: true });
        return;
      }
      const first = tabbables[0];
      const last = tabbables[tabbables.length - 1];
      const active = document.activeElement;
      if (!(active instanceof HTMLElement) || !dialog.contains(active)) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus({ preventScroll: true });
      } else if (event.shiftKey && active === first) {
        event.preventDefault();
        last.focus({ preventScroll: true });
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus({ preventScroll: true });
      }
    };
    document.addEventListener("keydown", onKeyDown, true);
    return () => document.removeEventListener("keydown", onKeyDown, true);
  }, [busy, checkoutOpen]);

  const orderDetailOpen = Boolean(selectedOrder);

  useEffect(() => {
    if (typeof document === "undefined") return;
    if (walletChooserOpen && !walletChooserWasOpenRef.current) {
      walletChooserInitiatorRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      const initialTarget =
        walletChooserDialogRef.current?.querySelector<HTMLElement>('[data-linked-wallet-id][data-active="true"]') ??
        walletChooserDialogRef.current?.querySelector<HTMLElement>('[data-linked-wallet-id]') ??
        walletChooserCloseButtonRef.current;
      initialTarget?.focus({ preventScroll: true });
    }
    if (!walletChooserOpen && walletChooserWasOpenRef.current) {
      const initiator = walletChooserInitiatorRef.current;
      walletChooserInitiatorRef.current = null;
      if (initiator?.isConnected) initiator.focus({ preventScroll: true });
    }
    walletChooserWasOpenRef.current = walletChooserOpen;
  }, [walletChooserOpen]);

  useEffect(() => {
    if (typeof document === "undefined") return;
    const snapshots = walletChooserInertSnapshotsRef.current;
    const restoreElement = (element: HTMLElement, snapshot: ShopCheckoutInertSnapshot) => {
      if (snapshot.hadAttribute) element.setAttribute("inert", snapshot.value ?? "");
      else element.removeAttribute("inert");
    };
    const restoreAll = () => {
      for (const [element, snapshot] of snapshots) restoreElement(element, snapshot);
      snapshots.clear();
    };
    const sync = () => {
      const backdrop = walletChooserBackdropRef.current;
      const dialog = walletChooserDialogRef.current;
      const topDialog = shopRenderedDialogs().at(-1) ?? null;
      const desired = walletChooserOpen && backdrop && dialog && topDialog === dialog
        ? shopCheckoutBackgroundTargets(backdrop)
        : new Set<HTMLElement>();
      for (const [element, snapshot] of snapshots) {
        if (desired.has(element)) continue;
        restoreElement(element, snapshot);
        snapshots.delete(element);
      }
      for (const element of desired) {
        if (!snapshots.has(element)) snapshots.set(element, { hadAttribute: element.hasAttribute("inert"), value: element.getAttribute("inert") });
        element.setAttribute("inert", "");
      }
    };
    if (!walletChooserOpen) { restoreAll(); return; }
    sync();
    const observer = new MutationObserver(sync);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => { observer.disconnect(); restoreAll(); };
  }, [checkoutOpen, orderDetailOpen, walletChooserOpen]);

  useEffect(() => {
    if (!walletChooserOpen || typeof document === "undefined") return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Tab" && event.key !== "Escape") return;
      const dialog = walletChooserDialogRef.current;
      if (!dialog || shopRenderedDialogs().at(-1) !== dialog) return;
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        closeWalletChooser();
        return;
      }
      const tabbables = shopCheckoutTabbables(dialog);
      if (tabbables.length === 0) {
        event.preventDefault();
        dialog.focus({ preventScroll: true });
        return;
      }
      const first = tabbables[0];
      const last = tabbables[tabbables.length - 1];
      const active = document.activeElement;
      if (!(active instanceof HTMLElement) || !dialog.contains(active)) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus({ preventScroll: true });
      } else if (event.shiftKey && active === first) {
        event.preventDefault();
        last.focus({ preventScroll: true });
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus({ preventScroll: true });
      }
    };
    document.addEventListener("keydown", onKeyDown, true);
    return () => document.removeEventListener("keydown", onKeyDown, true);
  }, [walletChooserOpen]);

  useEffect(() => {
    if (typeof document === "undefined") return;
    if (orderDetailOpen && !orderDetailWasOpenRef.current) {
      if (!orderDetailInitiatorRef.current) {
        orderDetailInitiatorRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      }
      orderDetailCloseButtonRef.current?.focus({ preventScroll: true });
    }
    if (!orderDetailOpen && orderDetailWasOpenRef.current) {
      let target = orderDetailInitiatorRef.current;
      if (!target?.isConnected && orderDetailReturnOrderIdRef.current) {
        target = Array.from(document.querySelectorAll<HTMLElement>("[data-order-detail-id]")).find(
          (element) => element.dataset.orderDetailId === orderDetailReturnOrderIdRef.current,
        ) ?? null;
      }
      orderDetailInitiatorRef.current = null;
      orderDetailReturnOrderIdRef.current = "";
      if (target?.isConnected) target.focus({ preventScroll: true });
    }
    orderDetailWasOpenRef.current = orderDetailOpen;
  }, [orderDetailOpen]);

  useEffect(() => {
    if (typeof document === "undefined") return;
    const snapshots = orderDetailInertSnapshotsRef.current;
    const restoreElement = (element: HTMLElement, snapshot: ShopCheckoutInertSnapshot) => {
      if (snapshot.hadAttribute) element.setAttribute("inert", snapshot.value ?? "");
      else element.removeAttribute("inert");
    };
    const restoreAll = () => {
      for (const [element, snapshot] of snapshots) restoreElement(element, snapshot);
      snapshots.clear();
    };
    const sync = () => {
      const backdrop = orderDetailBackdropRef.current;
      const dialog = orderDetailDialogRef.current;
      const topDialog = shopRenderedDialogs().at(-1) ?? null;
      const desired = orderDetailOpen && backdrop && dialog && topDialog === dialog
        ? shopCheckoutBackgroundTargets(backdrop)
        : new Set<HTMLElement>();
      for (const [element, snapshot] of snapshots) {
        if (desired.has(element)) continue;
        restoreElement(element, snapshot);
        snapshots.delete(element);
      }
      for (const element of desired) {
        if (!snapshots.has(element)) snapshots.set(element, { hadAttribute: element.hasAttribute("inert"), value: element.getAttribute("inert") });
        element.setAttribute("inert", "");
      }
    };
    if (!orderDetailOpen) { restoreAll(); return; }
    sync();
    const observer = new MutationObserver(sync);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => { observer.disconnect(); restoreAll(); };
  }, [orderDetailOpen]);

  useEffect(() => {
    if (!orderDetailOpen || typeof document === "undefined") return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Tab" && event.key !== "Escape") return;
      const dialog = orderDetailDialogRef.current;
      if (!dialog || shopRenderedDialogs().at(-1) !== dialog) return;
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        closeOrderDetail();
        return;
      }
      const tabbables = shopCheckoutTabbables(dialog);
      if (tabbables.length === 0) {
        event.preventDefault();
        dialog.focus({ preventScroll: true });
        return;
      }
      const first = tabbables[0];
      const last = tabbables[tabbables.length - 1];
      const active = document.activeElement;
      if (!(active instanceof HTMLElement) || !dialog.contains(active)) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus({ preventScroll: true });
      } else if (event.shiftKey && active === first) {
        event.preventDefault();
        last.focus({ preventScroll: true });
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus({ preventScroll: true });
      }
    };
    document.addEventListener("keydown", onKeyDown, true);
    return () => document.removeEventListener("keydown", onKeyDown, true);
  }, [orderDetailOpen]);




  return (
    <main
      id="top" className="efhc-browser-shop-landing" data-public-surface="browser-shop"
      data-browser-shop-composition="compact-catalog-sections-v218" data-browser-shop-product-surface="separate-standard-shop-v248"
      data-browser-shop-checkout="global-currency-modal"
      data-browser-shop-linking="telegram-web-return" data-browser-shop-polling="react-query-5000ms"
      data-browser-shop-ttl={ttl || "none"} data-wallet-transaction={walletTxPhase} data-tonconnect-transaction={walletTxPhase}
      data-browser-shop-no-bottom-menu="true" data-browser-shop-readiness={readinessState || "unknown"}
      data-browser-shop-resume-intent={resumeIntent ? "true" : "false"} data-browser-shop-canonical-center={canonicalCenter}
      data-browser-shop-public-route={activeTab === "orders" ? "/browser-shop/orders" : activeTab === "profile" ? "/browser-shop/profile" : "/browser-shop"} data-browser-shop-renderer="canonical-production-external"
      data-browser-shop-vps-surface="separate-document-same-host" data-browser-shop-fixed-packages="10-50-100-150-200-250-300-350-500-750-1000-1500-2000-2500-3000" data-browser-shop-package-model="15-fixed-plus-exchange-plus-vip-17-total"
      data-browser-shop-vip-number-model="four-digit-sku-0001-9999-0000-display-only"
      data-browser-shop-vip-price-model="six-admin-prices-two-sku-tiers"
      data-browser-shop-vip-wallet-gate="required-before-payment"
      data-browser-shop-wallet-choice="primary-wallet-execution-router-v241"
      data-browser-shop-vip-reservation="atomic-backend-lock-active"
      data-browser-shop-vip-visible-limit="100-no-expansion" data-browser-shop-external-payment="payment-intent-chain-reconciliation-active"
    >
      <div className="efhc-browser-shop-landing_container">
        {loadError ? <section className="efhc-shop-landing_notice is-error" role="status"><div><strong>{t("portal.browser_shop.open_failed_title")}</strong><p>{t("portal.browser_shop.open_failed_clean_detail")}</p></div>{bootstrap?.bot_open_url ? <Button onClick={openTelegramLink}>{t("portal.browser_shop.open_bot")}</Button> : null}</section> : null}
        <section className="efhc-shop-catalog-toolbar" aria-label={t("portal.browser_shop.shop_navigation")}>
          <div className="efhc-shop-catalog-tabs" role="tablist">
            <button type="button" role="tab" aria-selected={activeTab === "shop"} onClick={() => navigateShopPage("shop")}>{t("portal.browser_shop.nav_shop")}</button>
            <button type="button" role="tab" aria-selected={activeTab === "orders"} onClick={() => navigateShopPage("orders")}>{t("portal.browser_shop.nav_orders")}</button>
            <button type="button" role="tab" aria-selected={activeTab === "profile"} onClick={() => navigateShopPage("profile")}>{t("portal.browser_shop.nav_profile")}</button>
          </div>
          {activeTab === "shop" ? <div className="efhc-shop-currency-switch" role="group" aria-label={t("portal.browser_shop.currency_label")}>
            {(["TON", "USDT", "EFHC"] as PayMethod[]).map((method) => <button key={method} type="button" aria-pressed={globalMethod === method} onClick={() => chooseGlobalMethod(method)}>{methodLabel(method)}</button>)}
          </div> : null}
        </section>

        {loading ? <RouteSkeleton kind="cards" rows={3} /> : null}
        <section className="efhc-shop-landing_account" data-account-linked={accountLinked ? "true" : "false"} data-browser-shop-profile={accountLinked ? "connected" : "guest"} data-profile-global-id={linkedGlobalId || "none"} data-wallet-linked={walletLinked ? "true" : "false"}>
          <div className="efhc-shop-landing_account-copy"><span>{accountLinked ? t("portal.browser_shop.linked") : t("portal.browser_shop.guest")}</span><strong>{username} {linkedGlobalId ? `· Global ID ${linkedGlobalId}` : ""}</strong><small>EFHCm {mainBalance}</small></div>
          <div className="efhc-shop-landing_account-actions">
            {!accountLinked ? <Button onClick={openWebProfile}>{t("portal.browser_shop.login_or_create_profile")}</Button> : null}
            {accountLinked && !token ? <Button onClick={() => void linkWebAccount()} disabled={accessKey.isPending}>{t("portal.browser_shop.connect_web_profile")}</Button> : null}
            {token && !walletLinked ? <Button onClick={syncWallet}>{t("portal.browser_shop.open_sync")}</Button> : null}
            <Button variant="secondary" onClick={() => openWalletChooser(null)} disabled={walletTxPhase === "signing"} data-linked-wallet-address-choice="true">{paymentWalletAddress ? t("portal.browser_shop.change_wallet") : t("portal.browser_shop.choose_wallet")}</Button>
          </div>
        </section>

        <div className="efhc-shop-landing_status-stack" aria-live="polite">
          {pendingIntentVisible ? <section className="efhc-shop-landing_notice"><div><strong>{t("portal.browser_shop.awaiting_payment")}</strong><p>{ttl ? `${ttl}. ` : ""}{t("portal.browser_shop.intent_not_order")}</p></div>{activeIntentId ? <Button variant="secondary" onClick={() => void statusQ.refetch()} disabled={statusQ.isFetching}>{t("common.refresh")}</Button> : null}</section> : null}
          {nftPaymentConfirmed ? <section className="efhc-shop-landing_notice is-success"><div><strong>{t("portal.browser_shop.nft_waiting_delivery_short")}</strong><p>{reservedVipNumber ? `VIP NFT #${reservedVipNumber}. ` : ""}{t("portal.browser_shop.nft_waiting_delivery")}</p></div></section> : null}
          {confirmedOrderId ? <section className="efhc-shop-landing_notice is-success" data-browser-shop-confirmed-order-id={confirmedOrderId}><div><strong>{t("portal.browser_shop.order_id_title")}</strong><p>#{confirmedOrderId}</p></div><Button variant="secondary" onClick={() => void copyConfirmedOrderId()}>{t("portal.browser_shop.copy_order_id")}</Button></section> : null}
          {walletTxPhase === "signing" ? <section className="efhc-shop-landing_notice"><div><strong>{t("wallet.transaction_signing")}</strong><p>{t("wallet.transaction_signing_detail")}</p></div></section> : null}
          {localError ? <section className="efhc-shop-landing_notice is-error"><div><strong>{t("common.error")}</strong><p>{localError}</p></div></section> : null}
          {localNotice ? <section className="efhc-shop-landing_notice is-success"><strong>{localNotice}</strong></section> : null}
        </div>

        {activeTab === "shop" ? <div className="efhc-shop-catalog-stack">
          <section id="packages" className="efhc-shop-catalog-section" aria-labelledby="packagesTitle">
            <div className="efhc-shop-catalog-heading"><figure className="efhc-shop-catalog-visual is-coin"><img src={"/assets/efhc/efhc_coin_256.png"} alt="EFHC" /><figcaption>EFHC</figcaption></figure><header className="efhc-shop-catalog-heading-copy"><span>EFHC</span><h1 id="packagesTitle">{t("portal.browser_shop.coins_title")}</h1><p>{t("portal.browser_shop.coins_detail")}</p></header></div>
            <div className="efhc-shop-catalog-copy">
              <div className="efhc-shop-text-products" data-browser-shop-product-count={FIXED_EFHC_PACKAGE_AMOUNTS.length + 1} data-browser-shop-total-products="17" data-browser-shop-desktop-layout="8-left-8-right">
                {FIXED_EFHC_PACKAGE_AMOUNTS.map((amount) => {
                  const item = packageCatalog.find((candidate) => fixedEfhcPackageSlot(candidate) === amount) || null;
                  const enabled = Boolean(item && methodAllowed(item, globalMethod) && !busy);
                  const displayTitle = `${amount} EFHCm`;
                  return <button key={amount} type="button" className="efhc-shop-text-product" data-checkout-sku={item?.sku || `EFHC_PACKAGE_${amount}`} data-browser-shop-pay-method={globalMethod} data-browser-shop-package-slot={amount} disabled={!enabled} onClick={() => { if (item) openCheckout({ item, method: globalMethod }); }}><span className="efhc-shop-product-main"><img className="efhc-shop-package-thumb" src="/assets/efhc/efhc_coin_256.png" alt="" /><span className="efhc-shop-product-copy"><strong>{displayTitle}</strong><small>{item ? localized(item, "description", t("portal.browser_shop.package_default_subtitle")) : t("portal.browser_shop.package_default_subtitle")}</small></span></span><span className="efhc-shop-product-price"><small>{methodLabel(globalMethod)}</small><b>{item && enabled ? priceAmountOnly(item, globalMethod) : t("portal.browser_shop.unavailable")}</b></span></button>;
                })}
                {(() => {
                  const item = packageCatalog.find(isCustomEfhcPackage) || null;
                  const enabled = Boolean(item && methodAllowed(item, globalMethod) && !busy);
                  return <button type="button" className="efhc-shop-text-product" data-checkout-sku={CUSTOM_EFHC_PACKAGE_SKU} data-browser-shop-package-slot="exchange" disabled={!enabled} onClick={() => { if (item) openCustomExchange(item); }}><span className="efhc-shop-product-main"><img className="efhc-shop-package-thumb" src="/assets/efhc/efhc_coin_256.png" alt="" /><span className="efhc-shop-product-copy"><strong>{t("portal.browser_shop.custom_exchange_title")}</strong><small>{t("portal.browser_shop.custom_exchange_detail")}</small></span></span><span className="efhc-shop-product-price"><small>{item ? customRateLabel(item, globalMethod) : t("portal.browser_shop.unavailable")}</small><b>{enabled ? "1+ EFHCm" : t("portal.browser_shop.unavailable")}</b></span></button>;
                })()}
              </div>
            </div>
          </section>

          <section id="vip" className="efhc-shop-catalog-section is-vip" aria-labelledby="vipTitle">
            <div className="efhc-shop-catalog-heading"><figure className="efhc-shop-catalog-visual is-nft" data-vip-display-number="0000-unavailable"><img src={VIP_0000_IMAGE} alt="EFHC VIP NFT 0000" referrerPolicy="no-referrer" onError={(event) => { const image = event.currentTarget; if (image.dataset.fallback === "true") return; image.dataset.fallback = "true"; image.src = "/assets/efhc/efhc_coin_256.png"; }} /><figcaption>EFHC VIP NFT · 0000</figcaption></figure><header className="efhc-shop-catalog-heading-copy"><span>VIP NFT</span><h2 id="vipTitle">EFHC VIP NFT</h2><p>{t("portal.browser_shop.vip_0000_detail")}</p></header></div>
            <div className="efhc-shop-catalog-copy">
              <div className="efhc-shop-vip-modes">
                {vipAnyItem ? <button type="button" className="efhc-shop-text-product" disabled={!methodAllowed(vipAnyItem, globalMethod) || busy} onClick={() => openCheckout({ item: vipAnyItem, method: globalMethod, vipMode: "any" })}><span className="efhc-shop-product-copy"><strong>{t("portal.browser_shop.vip_any_title")}</strong><small>{t("portal.browser_shop.vip_any_detail")}</small></span><span className="efhc-shop-product-price"><small>{methodLabel(globalMethod)}</small><b>{methodAllowed(vipAnyItem, globalMethod) ? priceAmountOnly(vipAnyItem, globalMethod) : t("portal.browser_shop.unavailable")}</b></span></button> : null}
                <button type="button" className="efhc-shop-text-product" disabled={!vipSelectedPriceItem || !vipNumberItems.length || !methodAllowed(vipSelectedPriceItem, globalMethod) || busy} onClick={() => document.getElementById("vipNumberChooser")?.scrollIntoView({ behavior: "smooth", block: "center" })}><span className="efhc-shop-product-copy"><strong>{t("portal.browser_shop.vip_select_title")}</strong><small>{t("portal.browser_shop.vip_select_detail")}</small></span><span className="efhc-shop-product-price"><small>{methodLabel(globalMethod)}</small><b>{vipSelectedPriceItem && methodAllowed(vipSelectedPriceItem, globalMethod) ? priceAmountOnly(vipSelectedPriceItem, globalMethod) : t("portal.browser_shop.unavailable")}</b></span></button>
              </div>
              <div id="vipNumberChooser" className="efhc-shop-number-chooser" data-vip-inventory-count={vipNumberItems.length}>
                <div className="efhc-shop-number-chooser-head"><div><strong>{t("portal.browser_shop.vip_numbers_title")}</strong><small>{Math.min(vipNumberItems.length, VIP_NUMBER_PAGE)} {t("portal.browser_shop.vip_numbers_shown_suffix")}</small></div><input value={vipSearch} onChange={(event) => setVipSearch(event.target.value)} inputMode="numeric" maxLength={4} placeholder={t("portal.browser_shop.vip_number_search")} aria-label={t("portal.browser_shop.vip_number_search_aria")} /></div>
                <div className="efhc-shop-number-grid" role="listbox" aria-label={t("portal.browser_shop.vip_numbers_aria")}>{visibleVipNumbers.map(({ number }) => <button key={number} type="button" role="option" aria-selected={selectedVipNumber === number} onClick={() => setSelectedVipNumber(number)}>{number}</button>)}</div>
                {!visibleVipNumbers.length ? <p className="efhc-shop-catalog-empty">{t("portal.browser_shop.vip_numbers_empty")}</p> : null}
                <div className="efhc-shop-number-actions"><Button onClick={openVipNumberCheckout} disabled={!selectedVipNumber || busy || !vipSelectedPriceItem}>{t("portal.browser_shop.continue_with_number")} {selectedVipNumber || "—"}</Button></div>
              </div>
            </div>
          </section>
        </div> : null}

        {activeTab === "orders" ? <section className="efhc-shop-account-panel" aria-labelledby="ordersTitle"><header><span>EFHC</span><h1 id="ordersTitle">{t("portal.browser_shop.nav_orders")}</h1><p>{t("portal.browser_shop.orders_detail")}</p></header><div className="efhc-shop-order-list">{paidOrders.slice(0, ordersVisibleCount).map((order) => { const vipMatch = String(order.sku || "").match(/_NUMBER_(\d{4})$/); const vipAny = /VIP.*(?:ANY|NFT)$/i.test(String(order.sku || "")); return <article key={String(order.id)} data-order-detail="true" data-order-detail-id={String(order.id)} tabIndex={0} role="button" onClick={(event) => openOrderDetail(order, event.currentTarget)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); openOrderDetail(order, event.currentTarget); } }}><div><strong>#{String(order.id)} · {order.sku}</strong><small>{vipMatch ? `VIP NFT #${vipMatch[1]}` : vipAny ? t("portal.browser_shop.vip_number_admin_assigns") : new Date(order.created_at).toLocaleString()}</small></div><span>{orderStatusLabel(order.status, t)}</span></article>; })}{!paidOrders.length ? <p className="efhc-shop-catalog-empty">{t("portal.browser_shop.orders_empty")}</p> : null}</div>{ordersVisibleCount < paidOrders.length ? <div className="efhc-shop-profile-actions"><Button variant="secondary" onClick={() => setOrdersVisibleCount((count) => count + ORDERS_PAGE)}>{t("portal.browser_shop.show_more_20")}</Button></div> : null}</section> : null}

        {activeTab === "profile" ? <section className="efhc-shop-account-panel" aria-labelledby="profileTitle"><header><span>EFHC</span><h1 id="profileTitle">{t("portal.browser_shop.nav_profile")}</h1><p>{t("portal.browser_shop.profile_detail")}</p></header><div className="efhc-shop-profile-grid"><article><small>{t("portal.browser_shop.name_label")}</small><strong>{username}</strong></article><article><small>Global ID</small><strong>{linkedGlobalId || "—"}</strong></article><article><small>{t("portal.browser_shop.main_balance_label")}</small><strong>{mainBalance} EFHCm</strong></article><article><small>{t("portal.browser_shop.payment_wallet_label")}</small><strong>{paymentWalletAddress ? t("portal.browser_shop.payment_wallet_selected") : t("portal.browser_shop.not_connected")}</strong></article></div><div className="efhc-shop-profile-wallets">{(profileQ.data?.wallets || []).map((wallet, index) => <article key={String(wallet.id)} data-wallet-private-label={String(wallet.id)}><div><strong>{wallet.is_primary ? t("portal.browser_shop.primary_wallet") : `${t("portal.browser_shop.additional_wallet")} ${index + 1}`}</strong><small>{walletPrivateSuffix(wallet.wallet_address) ? `•••• ${walletPrivateSuffix(wallet.wallet_address)}` : t("portal.browser_shop.wallet_address_private")}</small></div></article>)}{!profileQ.data?.wallets?.length ? <p className="efhc-shop-catalog-empty">{t("portal.browser_shop.linked_wallets_empty")}</p> : null}</div><div className="efhc-shop-profile-actions"><Button onClick={openWebProfile}>{t("portal.browser_shop.open_web_profile")}</Button><Button variant="secondary" onClick={() => openWalletChooser(null)}>{paymentWalletAddress ? t("portal.browser_shop.change_wallet") : t("portal.browser_shop.choose_wallet")}</Button></div></section> : null}

        <section className="efhc-shop-landing_security"><strong>{t("portal.browser_shop.payment_warning_title")}</strong><p>{t("portal.browser_shop.payment_warning_detail")}</p></section>
      </div>

      {checkout ? <div ref={checkoutBackdropRef} className="efhc-shop-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) setCheckout(null); }}><section ref={checkoutDialogRef} className="efhc-shop-checkout-modal" role="dialog" aria-modal="true" aria-labelledby="checkoutTitle" aria-describedby={localError ? "checkoutSummary checkoutError" : "checkoutSummary"} tabIndex={-1}><button ref={checkoutCloseButtonRef} className="efhc-shop-modal-close" type="button" disabled={busy} onClick={() => setCheckout(null)} aria-label={t("portal.browser_shop.close")}>×</button><span>EFHC · {t("portal.browser_shop.checkout_label")}</span>{isCustomEfhcPackage(checkout.item) ? <label className="efhc-shop-exchange-title" id="checkoutTitle"><span>{t("portal.browser_shop.custom_exchange_title")}</span><input data-shop-checkout-initial-focus inputMode="numeric" pattern="[0-9]*" value={customEfhcAmount} onChange={(event) => updateCustomExchangeAmount(event.target.value)} placeholder={t("portal.browser_shop.custom_amount_placeholder")} aria-label={t("portal.browser_shop.custom_amount_aria")} /></label> : <h2 id="checkoutTitle">{checkout.vipMode === "selected" ? `EFHC VIP NFT #${checkout.vipNumber}` : localized(checkout.item, "title", checkout.item.title)}</h2>}<div className="efhc-shop-checkout-summary" id="checkoutSummary">{isCustomEfhcPackage(checkout.item) ? <><div><small>{t("portal.browser_shop.custom_rate_label")}</small><strong>{customRateLabel(checkout.item, checkout.method)}</strong></div><div data-exchange-total="true"><small>{t("portal.browser_shop.custom_total_label")}</small><strong>{checkoutPriceLabel(checkout)}</strong></div></> : <div><small>{t("portal.browser_shop.price_label")}</small><strong>{checkoutPriceLabel(checkout)}</strong></div>}<div><small>{t("portal.browser_shop.profile_label")}</small><strong>{linkedGlobalId ? `Global ID ${linkedGlobalId}` : t("portal.browser_shop.login_required")}</strong></div>{checkout.vipMode ? <div><small>{t("portal.browser_shop.delivery_label")}</small><strong>{checkout.vipMode === "selected" ? `${t("portal.browser_shop.number_prefix")} ${checkout.vipNumber}` : t("portal.browser_shop.vip_any_title")}</strong></div> : null}{checkout.method !== "EFHC" ? <div><small>{t("portal.browser_shop.payment_wallet_label")}</small><strong className="is-wallet">{paymentWalletAddress ? t("portal.browser_shop.payment_wallet_selected") : t("portal.browser_shop.choose_ton_wallet")}</strong></div> : <div><small>{t("portal.browser_shop.debit_label")}</small><strong>{t("portal.browser_shop.main_balance_d8")}</strong></div>}</div>{localError ? <section id="checkoutError" className="efhc-shop-landing_notice is-error efhc-shop-checkout-error" role="alert"><div><strong>{t("common.error")}</strong><p>{localError}</p></div></section> : null}{checkout.method !== "EFHC" ? <BrowserShopPreSignChecklist asset={checkout.method} amount={checkoutPriceLabel(checkout)} ready={Boolean(paymentWalletAddress)} /> : null}{checkout.method !== "EFHC" && paymentWalletAddress ? <Button variant="secondary" onClick={() => openWalletChooser(checkout)}>{t("portal.browser_shop.change_wallet")}</Button> : null}<Button onClick={() => void payCheckout()} disabled={busy || !methodAllowed(checkout.item, checkout.method) || (isCustomEfhcPackage(checkout.item) && !checkout.customEfhcAmountD8)}>{t("portal.browser_shop.pay_button")}</Button></section></div> : null}

      {walletChooserOpen ? <div ref={walletChooserBackdropRef} className="efhc-shop-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) closeWalletChooser(); }}><section ref={walletChooserDialogRef} className="efhc-shop-wallet-modal" role="dialog" aria-modal="true" aria-labelledby="walletChooserTitle" tabIndex={-1}><button ref={walletChooserCloseButtonRef} className="efhc-shop-modal-close" type="button" onClick={closeWalletChooser} aria-label={t("portal.browser_shop.close")}>×</button><span>EFHC</span><h2 id="walletChooserTitle">{t("portal.browser_shop.wallet_address_chooser_title")}</h2><p>{t("portal.browser_shop.wallet_address_chooser_detail")}</p><div className="efhc-shop-wallet-list">{linkedWalletChoices.map((wallet, index) => <button key={String(wallet.id)} type="button" data-linked-wallet-id={String(wallet.id)} data-active={String(wallet.wallet_address === paymentWalletAddress)} onClick={() => void chooseLinkedWallet(wallet)}><span>{wallet.is_primary ? "★" : String(index + 1)}</span><strong>{wallet.is_primary ? t("portal.browser_shop.primary_wallet") : `${t("portal.browser_shop.additional_wallet")} ${index + 1}`}</strong><small>{walletPrivateSuffix(wallet.wallet_address) ? `•••• ${walletPrivateSuffix(wallet.wallet_address)}` : t("portal.browser_shop.wallet_address_private")}</small></button>)}</div></section></div> : null}
      {selectedOrder ? <div ref={orderDetailBackdropRef} className="efhc-shop-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) closeOrderDetail(); }}><section ref={orderDetailDialogRef} className="efhc-shop-order-modal" role="dialog" aria-modal="true" aria-labelledby="orderDetailTitle" tabIndex={-1}><button ref={orderDetailCloseButtonRef} className="efhc-shop-modal-close" type="button" onClick={closeOrderDetail} aria-label={t("portal.browser_shop.close")}>×</button><span>EFHC · {t("portal.browser_shop.order_details_title")}</span><h2 id="orderDetailTitle">ShopOrder #{String(selectedOrder.id)}</h2><div className="efhc-shop-order-detail-grid"><div><small>{t("portal.browser_shop.order_id_label")}</small><strong>{String(selectedOrder.id)}</strong></div><div><small>SKU</small><strong>{selectedOrder.sku}</strong></div><div><small>{t("portal.browser_shop.status_label")}</small><strong>{orderStatusLabel(selectedOrder.status, t)}</strong></div><div><small>Global ID</small><strong>{selectedOrder.global_id}</strong></div><div><small>{t("portal.browser_shop.payment_method_title")}</small><strong>{selectedOrder.payment_method || "—"}</strong></div><div><small>{t("portal.browser_shop.price_label")}</small><strong>{selectedOrder.expected_amount || "—"}</strong></div><div><small>{t("portal.browser_shop.paid_at_label")}</small><strong>{selectedOrder.paid_at ? new Date(selectedOrder.paid_at).toLocaleString() : new Date(selectedOrder.created_at).toLocaleString()}</strong></div>{selectedOrder.tx_hash ? <div><small>{t("portal.browser_shop.tx_hash_label")}</small><code>{selectedOrder.tx_hash}</code></div> : null}<div><small>{t("portal.browser_shop.created_label")}</small><strong>{new Date(selectedOrder.created_at).toLocaleString()}</strong></div><div><small>{t("portal.browser_shop.updated_label")}</small><strong>{new Date(selectedOrder.updated_at).toLocaleString()}</strong></div></div></section></div> : null}

    </main>
  );
}
