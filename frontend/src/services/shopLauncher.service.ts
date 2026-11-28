import { apiRequest } from "../lib/api";
import {
  HUB_SHOP_TRUTH_PATH,
  SHOPFRONT_ACCESS_KEY_PATH,
  type HubShopTruthResponse,
  type ShopfrontAccessResponse,
} from "../lib/api/generated/economicUserSeams";
import {
  parseHubShopTruthResponse,
  parseShopfrontAccessResponse,
} from "../lib/api/generated/economicUserSeamValidators";

export async function getShopLauncherTruth(): Promise<
  HubShopTruthResponse
> {
  const raw = await apiRequest<unknown>(HUB_SHOP_TRUTH_PATH, "GET");
  return parseHubShopTruthResponse(raw);
}

export async function createShopLauncherAccess(): Promise<
  ShopfrontAccessResponse
> {
  const raw = await apiRequest<unknown>(
    SHOPFRONT_ACCESS_KEY_PATH,
    "POST",
  );
  return parseShopfrontAccessResponse(raw);
}
