/** Neon TEST remote API: same route + payload + response schemas as production. */
import { getAuthAuthorizationHeader } from "../lib/auth-session";
import { ApiError, normalizeApiPath, type ApiRequestOptions, type HttpMethod } from "../lib/api";
import { type ApiTransport } from "../data/transport";
import { demoApiOrigin } from "./config";
import { invalidateDemoCredential, currentDemoSessionScope, sessionCsrf } from "./session";
import { demoFetch } from "./request";

export async function demoRawRequest(
  path: string, method: HttpMethod, options: ApiRequestOptions = {},
): Promise<Response> {
  const guest = ["guest", "visual"].includes(currentDemoSessionScope() || "");
  const normalized = normalizeApiPath(path);
  // C0034 preview writes use canonical TEST APIs, guest scope remains read-only.
  // Both are enforced on the isolated Neon TEST backend.
  const endpoint = guest && method === "POST" && normalized.split("?")[0] === "/api/sync/me"
    ? "/api/sync/me?fresh=0" : normalized;
  const headers: Record<string, string> = { ...(options.headers || {}) };
  const bearer = getAuthAuthorizationHeader();
  if (bearer && !headers.Authorization) headers.Authorization = bearer;
  if (options.idempotencyKey) headers["Idempotency-Key"] = options.idempotencyKey;
  if (options.requestId) headers["X-Request-ID"] = options.requestId;
  // The isolated Genesis TEST guest can submit wallet ownership evidence only
  // to the two canonical proof-verified routes. All other guest writes retain
  // the existing server-side read-only/financial guards.
  const guestTonProofWrite = currentDemoSessionScope() === "guest"
    && method === "POST"
    && [
      "/api/wallets/tonconnect/check-proof",
      "/api/wallets/connect",
    ].includes(normalized.split("?")[0]);
  const guestActivityWrite = currentDemoSessionScope() === "guest"
    && method === "POST"
    && normalized.split("?")[0] === "/api/deposit/direct-check";
  if (guestTonProofWrite || guestActivityWrite || (
      method !== "GET" && !guest &&
      normalized !== "/api/staging/login" && normalized !== "/api/staging/guest"
  )) {
    headers["X-EFHC-Test-CSRF"] = await sessionCsrf();
  }
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  const response = await demoFetch(`${demoApiOrigin()}${endpoint}`, {
    method, headers, credentials: "include", cache: "no-store", signal: options.signal,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
  if (response.status === 401) invalidateDemoCredential(headers.Authorization || null);
  return response;
}

export const demoBackendTransport: ApiTransport = {
  async request<T>(path: string, method: HttpMethod, options: ApiRequestOptions): Promise<T> {
    const response = await demoRawRequest(path, method, options);
    if (!response.ok) {
      const payload: unknown = await response.json().catch(() => null);
      const errorCode = payload && typeof payload === "object"
        ? String((payload as Record<string, unknown>).code || (payload as Record<string, unknown>).detail || "DEMO_API_FAILED")
        : "DEMO_API_FAILED";
      throw new ApiError({ status: response.status, code: errorCode, payload });
    }
    if (response.status === 204) return undefined as T;
    const type = response.headers.get("content-type") || "";
    if (!type.includes("application/json")) return undefined as T;
    return await response.json() as T;
  },
  requestRaw: demoRawRequest,
};
