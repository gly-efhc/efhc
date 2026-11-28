import type { AdProviderClientAdapter } from "../types";

export const builtinTimerClientAdapter: AdProviderClientAdapter = {
  code: "builtin_timer",
  async show(publicConfig) {
    const seconds = Math.max(1, Number(publicConfig.min_view_sec || 20));
    await new Promise((resolve) => window.setTimeout(resolve, seconds * 1000));
    return { completed: true, shown: true, payload: { shown: true, completed: true } };
  },
};
