/** DEMO operator session is server-authoritative. The bearer returned by the
 * TEST server is retained using the existing tab-scoped auth credential store.
 * This avoids depending solely on third-party cookies across Pages → Render.
 * No password, cookie, or bearer token is put in the public build or logs. */
import { clearAuthSession, getAuthAuthorizationHeader, storeAuthSession } from "../lib/auth-session";
import { demoApiOrigin } from "./config";
import { demoFetch } from "./request";
let csrf: string | null = null;
let sessionVersion = 0;
const DEMO_SCOPE_KEY = "efhc.demo.session.scope.v1";
const GUEST_RESUME_KEY = "efhc.demo.guest.resume";

function readGuestResumeToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    const token = window.localStorage.getItem(GUEST_RESUME_KEY);
    return token && /^[a-zA-Z0-9_-]{32,256}$/.test(token) ? token : null;
  } catch { return null; }
}

function saveGuestResumeToken(token: string | null): void {
  if (typeof window === "undefined") return;
  try {
    if (token) window.localStorage.setItem(GUEST_RESUME_KEY, token);
    else window.localStorage.removeItem(GUEST_RESUME_KEY);
  } catch { /* Local storage may be disabled; server always validates owners. */ }
}
type DemoScope = "guest" | "operator" | "visual";

export function currentDemoSessionScope(): DemoScope | null {
  if (typeof window === "undefined") return null;
  try {
    const value = window.sessionStorage.getItem(DEMO_SCOPE_KEY);
    return value === "guest" || value === "operator" || value === "visual" ? value : null;
  } catch { return null; }
}

function setDemoSessionScope(scope: DemoScope | null): void {
  if (typeof window === "undefined") return;
  try {
    if (scope) window.sessionStorage.setItem(DEMO_SCOPE_KEY, scope);
    else window.sessionStorage.removeItem(DEMO_SCOPE_KEY);
  } catch { /* Server validation is authoritative; client hint is optional. */ }
}

export function isDemoGuestSession(): boolean {
  return isDemoBackendMode() && ["guest", "visual"].includes(currentDemoSessionScope() || "");
}

type SessionInfo = { ok: boolean; global_id: string; csrf: string; mode: string };
type IssuedDemoSession = SessionInfo & {
  demo_bearer_token: string;
  expires_at_epoch: number;
  scope?: DemoScope;
  guest_resume_token?: string;
  guest_lease_expires_at?: string;
};

export function clearDemoSession(): void {
  sessionVersion++;
  csrf = null;
  setDemoSessionScope(null);
  saveGuestResumeToken(null);
}
/** Only the credential used by the failed request can be invalidated.
 * A delayed 401 must not revoke a newer login/owner selected in this tab. */
export function invalidateDemoCredential(authorization: string | null): void {
  if (!authorization || getAuthAuthorizationHeader() !== authorization) return;
  // Revoking this credential must not cancel a newer issuance in flight.
  csrf = null;
  setDemoSessionScope(null);
  clearAuthSession();
}
export function isDemoBackendMode(): boolean {
  return process.env.NEXT_PUBLIC_EFHC_DATA_SOURCE === "demo_backend";
}

function authorizationHeaders(): Record<string, string> {
  const bearer = getAuthAuthorizationHeader();
  return bearer ? { Authorization: bearer } : {};
}

function acceptIssuedDemoSession(value: IssuedDemoSession): SessionInfo {
  if (!value || typeof value.demo_bearer_token !== "string" ||
      !Number.isFinite(value.expires_at_epoch)) {
    throw new Error("DEMO_SESSION_CREDENTIAL_MISSING");
  }
  storeAuthSession({
    access_token: value.demo_bearer_token,
    token_type: "Bearer",
    expires_at: new Date(value.expires_at_epoch * 1000).toISOString(),
  });
  // A stable browser lease survives Render restarts; the actual bearer remains
  // session-scoped and never grants Admin or financial privileges.
  if (value.scope === "guest" &&
      (!value.guest_resume_token || !/^[a-zA-Z0-9_-]{32,256}$/.test(value.guest_resume_token))) {
    throw new Error("GENESIS_GUEST_LEASE_MISSING");
  }
  if (value.guest_resume_token) {
    if (!/^[a-zA-Z0-9_-]{32,256}$/.test(value.guest_resume_token)) {
      throw new Error("GENESIS_GUEST_LEASE_INVALID");
    }
    saveGuestResumeToken(value.guest_resume_token);
  }
  // Scope is only a UI hint; the TEST server checks session.scope and owner.
  setDemoSessionScope(value.scope === "guest" || value.scope === "visual" ? value.scope : "operator");
  // Never return the secret to the UI or console; the backend owns the identity.
  return {ok: value.ok, global_id: value.global_id, csrf: value.csrf, mode: value.mode};
}

export async function sessionInfo(): Promise<SessionInfo> {
  const headers = authorizationHeaders();
  const version = sessionVersion;
  const response = await demoFetch(`${demoApiOrigin()}/api/staging/session`, {
    credentials: "include", cache: "no-store", headers,
  });
  if (response.status === 401) {
    invalidateDemoCredential(headers.Authorization || null);
    throw new Error("EFHC_DEMO_SESSION_REQUIRED");
  }
  if (!response.ok) throw new Error(`EFHC_DEMO_SESSION_HTTP_${response.status}`);
  const result = await response.json() as SessionInfo;
  if (version !== sessionVersion || (headers.Authorization || null) !== getAuthAuthorizationHeader()) {
    throw new Error("DEMO_SESSION_REPLACED");
  }
  csrf = result.csrf;
  return result;
}
export async function sessionCsrf(): Promise<string> {
  if (!csrf) await sessionInfo();
  if (!csrf) throw new Error("EFHC_DEMO_CSRF_UNAVAILABLE");
  return csrf;
}

async function writeControl<T>(route: string, body?: unknown, login = false): Promise<T> {
  const version = sessionVersion;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(!login ? authorizationHeaders() : {}),
  };
  if (!login) headers["X-EFHC-Test-CSRF"] = await sessionCsrf();
  if (version !== sessionVersion) throw new Error("DEMO_SESSION_REPLACED");
  const response = await demoFetch(`${demoApiOrigin()}/api/staging/${route}`, {
    method: "POST", credentials: "include", cache: "no-store", headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (response.status === 401 && !login) invalidateDemoCredential(headers.Authorization || null);
  if (!response.ok) throw new Error(`EFHC_DEMO_${route.toUpperCase()}_HTTP_${response.status}`);
  const value = await response.json() as T;
  if (version !== sessionVersion) throw new Error("DEMO_SESSION_REPLACED");
  if (value && typeof value === "object" && "csrf" in value &&
      typeof value.csrf === "string") csrf = value.csrf;
  return value;
}

export async function loginDemoGuest(): Promise<SessionInfo> {
  sessionVersion++;
  const resume_token = readGuestResumeToken();
  const result = await writeControl<IssuedDemoSession>(
    "guest", resume_token ? {resume_token} : {}, true
  );
  if (result.scope !== "guest") throw new Error("DEMO_GUEST_SCOPE_INVALID");
  return acceptIssuedDemoSession(result);
}

export async function loginDemo(password: string): Promise<SessionInfo> {
  sessionVersion++;
  const resume_token = readGuestResumeToken();
  const result = await writeControl<IssuedDemoSession>(
    "login", resume_token ? {password, resume_token} : {password}, true
  );
  return acceptIssuedDemoSession(result);
}
/** Temporary server-validated frontend layout preview. NEVER an Admin role. */
export async function loginDemoVisual(key: string): Promise<SessionInfo> {
  sessionVersion++;
  const resume_token = readGuestResumeToken();
  const result = await writeControl<IssuedDemoSession>(
    "visual-access", resume_token ? {key, resume_token} : {key}, true
  );
  if (result.scope !== "visual") throw new Error("DEMO_VISUAL_SCOPE_INVALID");
  return acceptIssuedDemoSession(result);
}

export async function selectDemoGlobalId(global_id: string): Promise<SessionInfo> {
  if (!/^\d{10}$/.test(global_id) || global_id === "0000000000") throw new Error("INVALID_GLOBAL_ID");
  sessionVersion++;
  const result = await writeControl<IssuedDemoSession>("select-global-id", {global_id});
  return acceptIssuedDemoSession(result);
}
export async function logoutDemo(): Promise<void> {
  const resume_token = currentDemoSessionScope() ? readGuestResumeToken() : null;
  try { await writeControl("logout", resume_token ? {resume_token} : {}); }
  finally { clearDemoSession(); clearAuthSession(); }
}
