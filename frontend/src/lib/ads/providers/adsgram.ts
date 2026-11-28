import { loadProviderScript } from "../loadScript";
import type { AdProviderClientAdapter, ProviderShowResult } from "../types";

declare global {
  interface Window {
    Adsgram?: {
      init(args: { blockId: string; debug?: boolean }): {
        show(): Promise<unknown>;
      };
    };
  }
}

const ADSGRAM_SDK = "https://sad.adsgram.ai/js/sad.min.js";

export const adsgramClientAdapter: AdProviderClientAdapter = {
  code: "adsgram",
  async show(publicConfig): Promise<ProviderShowResult> {
    await loadProviderScript(ADSGRAM_SDK);
    const blockId = String(publicConfig.block_id || "").trim();
    if (!blockId || !window.Adsgram?.init) throw new Error("NOT_CONFIGURED");
    const controller = window.Adsgram.init({
      blockId,
      debug: Boolean(publicConfig.debug),
    });
    await controller.show();
    return {
      completed: true,
      shown: true,
      payload: { done: true, shown: true },
    };
  },
};
