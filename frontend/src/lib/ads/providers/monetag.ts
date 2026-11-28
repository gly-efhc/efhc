import { loadProviderScript } from "../loadScript";
import type { AdProviderClientAdapter, ProviderShowResult } from "../types";

type MonetagResult = {
  reward_event_type?: string;
  estimated_price?: number;
  sub_zone_id?: number;
  zone_id?: number;
  request_var?: string;
  ymid?: string;
};

type MonetagShow = (args: Record<string, unknown> | string) => Promise<MonetagResult>;

export const monetagClientAdapter: AdProviderClientAdapter = {
  code: "monetag",
  async show(publicConfig): Promise<ProviderShowResult> {
    const zoneId = String(publicConfig.zone_id || "").trim();
    const sdkSrc = String(publicConfig.sdk_src || "").trim();
    const showFunction = String(publicConfig.show_function || `show_${zoneId}`);
    if (!zoneId || !sdkSrc) throw new Error("NOT_CONFIGURED");
    await loadProviderScript(sdkSrc, {
      "data-zone": zoneId,
      "data-sdk": showFunction,
    });
    const show = (window as unknown as Record<string, unknown>)[showFunction] as MonetagShow | undefined;
    if (typeof show !== "function") throw new Error("SDK_LOAD_FAILED");
    const common = {
      ymid: String(publicConfig.ymid || ""),
      requestVar: String(publicConfig.request_var || "efhc_tasks"),
      catchIfNoFeed: publicConfig.catch_if_no_feed !== false,
    };
    if (publicConfig.preload !== false) {
      await show({ ...common, type: "preload", timeout: 5 });
    }
    const result = await show({ ...common, type: "end" });
    const valued = String(result?.reward_event_type || "").toLowerCase() === "valued";
    return {
      completed: true,
      shown: true,
      payload: {
        shown: true,
        completed: true,
        reward_event_type: result?.reward_event_type,
        estimated_price: result?.estimated_price,
        sub_zone_id: result?.sub_zone_id,
        zone_id: result?.zone_id,
        request_var: result?.request_var,
        ymid: result?.ymid || common.ymid,
        client_valued: valued,
      },
    };
  },
};
