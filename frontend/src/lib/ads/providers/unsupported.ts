import type { AdProviderClientAdapter } from "../types";

export function unsupportedProviderAdapter(code: string): AdProviderClientAdapter {
  return {
    code,
    async show() {
      throw new Error("NOT_SUPPORTED");
    },
  };
}
