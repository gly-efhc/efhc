import { loadProviderScript } from "../loadScript";
import type { AdProviderClientAdapter, ProviderShowResult } from "../types";

type AdexiumWidgetLike = {
  requestAd(format: string): void;
  displayAd(ad: unknown): void;
  on(event: string, callback: (...args: unknown[]) => void): void;
};

declare global {
  interface Window {
    AdexiumWidget?: new (args: Record<string, unknown>) => AdexiumWidgetLike;
  }
}

export const adexiumClientAdapter: AdProviderClientAdapter = {
  code: "adexium",
  async show(publicConfig): Promise<ProviderShowResult> {
    const widgetId = String(publicConfig.widget_id || "").trim();
    const sdkSrc = String(publicConfig.sdk_src || "").trim();
    if (!widgetId || !sdkSrc) throw new Error("NOT_CONFIGURED");
    await loadProviderScript(sdkSrc);
    if (!window.AdexiumWidget) throw new Error("SDK_LOAD_FAILED");
    const widget = new window.AdexiumWidget({
      wid: widgetId,
      adFormat: "interstitial",
      debug: false,
    });
    return await new Promise<ProviderShowResult>((resolve, reject) => {
      let providerTaskId = "";
      let settled = false;
      const finish = (value: ProviderShowResult): void => {
        if (settled) return;
        settled = true;
        resolve(value);
      };
      widget.on("adReceived", (...args) => {
        const ad = args[0] as { id?: string } | undefined;
        providerTaskId = String(ad?.id || "");
        try {
          widget.displayAd(ad);
        } catch {
          reject(new Error("PROVIDER_ERROR"));
        }
      });
      widget.on("noAdFound", () => finish({ completed: false, noFill: true }));
      widget.on("adPlaybackCompleted", () => finish({
        completed: true,
        shown: true,
        payload: {
          shown: true,
          completed: true,
          provider_task_id: providerTaskId,
        },
      }));
      try {
        widget.requestAd("interstitial");
      } catch {
        reject(new Error("PROVIDER_ERROR"));
      }
    });
  },
};
