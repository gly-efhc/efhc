import type { AdProviderClientAdapter } from "../types";
import { adexiumClientAdapter } from "./adexium";
import { admavenClientAdapter } from "./admaven";
import { adsgramClientAdapter } from "./adsgram";
import { builtinTimerClientAdapter } from "./builtinTimer";
import { monetagClientAdapter } from "./monetag";
import { richadsClientAdapter } from "./richads";
import { unsupportedProviderAdapter } from "./unsupported";

const adapters: Record<string, AdProviderClientAdapter> = {
  adsgram: adsgramClientAdapter,
  monetag: monetagClientAdapter,
  richads: richadsClientAdapter,
  admaven: admavenClientAdapter,
  adexium: adexiumClientAdapter,
  tads: unsupportedProviderAdapter("tads"),
  mybid: unsupportedProviderAdapter("mybid"),
  builtin_timer: builtinTimerClientAdapter,
};

export function getClientAdProvider(code: string): AdProviderClientAdapter {
  return adapters[String(code || "").trim().toLowerCase()] || unsupportedProviderAdapter(code);
}
