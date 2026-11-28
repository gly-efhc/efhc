import { getAuthAuthorizationHeader } from "../lib/auth-session";
import { getApiBase, normalizeApiPath, performProductionHttpRequest } from "../lib/api";
import { registerTransport, type ApiTransport } from "./transport";

export const productionTransport: ApiTransport = {
  request: performProductionHttpRequest,
  async requestRaw(path, method, options) {
    const headers: Record<string, string> = { ...(options.headers || {}) };
    const bearer = getAuthAuthorizationHeader();
    if (bearer && !headers.Authorization) headers.Authorization = bearer;
    if (options.idempotencyKey) headers["Idempotency-Key"] = options.idempotencyKey;
    if (options.requestId) headers["X-Request-ID"] = options.requestId;
    return fetch(getApiBase() + normalizeApiPath(path), {
      method, headers, credentials: "include", signal: options.signal,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
  },
};
export function register(): void { registerTransport(productionTransport); }
