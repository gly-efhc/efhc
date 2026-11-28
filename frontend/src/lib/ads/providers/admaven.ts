import { loadProviderScript } from "../loadScript";
import type { AdProviderClientAdapter, ProviderShowResult } from "../types";

declare global {
  interface Window {
    postbackValue?: string;
    manualTasks?: Array<{ title?: string }>;
    runTask?: (index: number) => void;
    taskCompleted?: (index: number) => void;
  }
}

export const admavenClientAdapter: AdProviderClientAdapter = {
  code: "admaven",
  async show(publicConfig): Promise<ProviderShowResult> {
    const scriptSrc = String(publicConfig.script_src || "").trim();
    const postbackValue = String(publicConfig.postback_value || "").trim();
    if (!scriptSrc || !postbackValue) throw new Error("NOT_CONFIGURED");
    window.postbackValue = postbackValue;
    await loadProviderScript(scriptSrc);

    const deadline = Date.now() + 8000;
    while (Date.now() < deadline) {
      if (Array.isArray(window.manualTasks) && window.manualTasks.length > 0 && typeof window.runTask === "function") break;
      await new Promise((resolve) => window.setTimeout(resolve, 150));
    }
    if (!Array.isArray(window.manualTasks) || window.manualTasks.length === 0 || typeof window.runTask !== "function") {
      return { completed: false, noFill: true };
    }

    return await new Promise<ProviderShowResult>((resolve, reject) => {
      const original = window.taskCompleted;
      let settled = false;
      const finish = (): void => {
        if (settled) return;
        settled = true;
        window.taskCompleted = original;
        resolve({
          completed: true,
          shown: true,
          payload: { shown: true, completed: true, postback_value: postbackValue },
        });
      };
      window.taskCompleted = (index: number) => {
        try { original?.(index); } finally { finish(); }
      };
      try {
        window.runTask?.(0);
      } catch {
        window.taskCompleted = original;
        reject(new Error("PROVIDER_ERROR"));
      }
    });
  },
};
