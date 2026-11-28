import { apiRequest } from "../lib/api";
import {
  SHOPFRONT_ACCESS_KEY_PATH,
  SHOPFRONT_BOOTSTRAP_PATH,
  SHOPFRONT_CATALOG_PATH,
  SHOPFRONT_CREATE_INTENT_PATH,
  SHOPFRONT_INTENT_STATUS_PATH,
  SHOPFRONT_PROFILE_PATH,
  type BrowserShopBootstrapResponse,
  type BrowserShopCatalogItem,
  type BrowserShopCreateIntentRequest,
  type BrowserShopProfileResponse,
  type BrowserShopCreateIntentResponse,
  type PaymentIntentStatusResponse,
  type ShopfrontAccessResponse,
} from "../lib/api/generated/economicUserSeams";
import {
  ensureBrowserShopCreateIntentRequest,
  parseBrowserShopBootstrapResponse,
  parseBrowserShopCatalogResponse,
  parseBrowserShopCreateIntentResponse,
  parseBrowserShopProfileResponse,
  parsePaymentIntentStatusResponse,
  parseShopfrontAccessResponse,
} from "../lib/api/generated/economicUserSeamValidators";
import type { DbId } from "../types/db-id";


export async function createBrowserShopAccessKey(): Promise<
  ShopfrontAccessResponse
> {
  const raw = await apiRequest<unknown>(
    SHOPFRONT_ACCESS_KEY_PATH,
    "POST",
  );
  return parseShopfrontAccessResponse(raw);
}

function handoffHeaders(token: string): Record<string, string> {
  return token ? { "X-EFHC-Handoff": token } : {};
}

export async function getBrowserShopBootstrap(
  token: string,
): Promise<BrowserShopBootstrapResponse> {
  const raw = await apiRequest<unknown>(
    SHOPFRONT_BOOTSTRAP_PATH,
    "GET",
    { headers: handoffHeaders(token) },
  );
  return parseBrowserShopBootstrapResponse(raw);
}

export async function getBrowserShopCatalog(): Promise<
  BrowserShopCatalogItem[]
> {
  const raw = await apiRequest<unknown>(SHOPFRONT_CATALOG_PATH, "GET");
  return parseBrowserShopCatalogResponse(raw).items || [];
}

export async function getBrowserShopProfile(
  token: string,
): Promise<BrowserShopProfileResponse> {
  const raw = await apiRequest<unknown>(
    SHOPFRONT_PROFILE_PATH,
    "GET",
    { headers: handoffHeaders(token) },
  );
  return parseBrowserShopProfileResponse(raw);
}

export async function getBrowserShopIntentStatus(args: {
  token: string;
  intentId: DbId;
}): Promise<PaymentIntentStatusResponse> {
  const query = new URLSearchParams({
    intent_id: String(args.intentId),
  });
  const raw = await apiRequest<unknown>(
    `${SHOPFRONT_INTENT_STATUS_PATH}?${query.toString()}`,
    "GET",
    { headers: handoffHeaders(args.token) },
  );
  return parsePaymentIntentStatusResponse(raw);
}

export async function createBrowserShopIntent(
  request: BrowserShopCreateIntentRequest,
): Promise<BrowserShopCreateIntentResponse> {
  const body = ensureBrowserShopCreateIntentRequest(request);
  const raw = await apiRequest<unknown>(
    SHOPFRONT_CREATE_INTENT_PATH,
    "POST",
    { body },
  );
  return parseBrowserShopCreateIntentResponse(raw);
}

export type BrowserShopEfhcPurchaseRequest = {
  sku: string;
  quantity: 1;
  idempotencyKey: string;
};

export type BrowserShopEfhcPurchaseResponse = Record<string, unknown>;

export async function purchaseBrowserShopWithEfhc(
  request: BrowserShopEfhcPurchaseRequest,
): Promise<BrowserShopEfhcPurchaseResponse> {
  return await apiRequest<BrowserShopEfhcPurchaseResponse>(
    "/shop/purchase-efhc",
    "POST",
    {
      idempotencyKey: request.idempotencyKey,
      body: {
        sku: request.sku,
        quantity: request.quantity,
      },
    },
  );
}
