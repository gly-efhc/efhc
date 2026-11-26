import {
  parseGlobalId,
  type GlobalId,
} from "../types/identity";

export type AuthSessionCredential = {
  access_token: string;
  token_type: "Bearer";
  expires_at: string;
};

export type AuthSessionContext = {
  global_id: GlobalId;
  provider: string;
  roles: string[];
};

const STORAGE_KEY = "efhc.auth.session.v1";
const TOKEN_PATTERN = /^[A-Za-z0-9_-]{32,128}$/;
let sessionRevision = 0;

export function getAuthSessionRevision(): number {
  return sessionRevision;
}

const invalidationListeners = new Set<() => void>();

function getSessionStorage(): Storage | null {
  try {
    const storage = globalThis.sessionStorage;
    return storage ?? null;
  } catch {
    return null;
  }
}

function isCredential(value: unknown): value is AuthSessionCredential {
  if (!value || typeof value !== "object") return false;
  const record = value as Record<string, unknown>;
  if (record.token_type !== "Bearer") return false;
  if (
    typeof record.access_token !== "string" ||
    !TOKEN_PATTERN.test(record.access_token)
  ) {
    return false;
  }
  if (typeof record.expires_at !== "string") return false;
  const expiresAt = Date.parse(record.expires_at);
  return Number.isFinite(expiresAt) && expiresAt > Date.now();
}

export function storeAuthSession(
  credential: AuthSessionCredential,
): void {
  if (!isCredential(credential)) {
    throw new Error("AUTH_SESSION_CREDENTIAL_INVALID");
  }
  const storage = getSessionStorage();
  if (!storage) throw new Error("AUTH_SESSION_STORAGE_UNAVAILABLE");
  storage.setItem(STORAGE_KEY, JSON.stringify(credential));
  sessionRevision++;
}

export function readAuthSession(): AuthSessionCredential | null {
  const storage = getSessionStorage();
  if (!storage) return null;
  const raw = storage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (isCredential(parsed)) return parsed;
  } catch {
    // Повреждённая запись удаляется fail closed.
  }
  clearAuthSession();
  return null;
}

export function clearAuthSession(): void {
  sessionRevision++;
  getSessionStorage()?.removeItem(STORAGE_KEY);
  for (const listener of invalidationListeners) listener();
}

export function subscribeAuthSessionInvalidation(
  listener: () => void,
): () => void {
  invalidationListeners.add(listener);
  return () => invalidationListeners.delete(listener);
}

export function getAuthAuthorizationHeader(): string | null {
  const credential = readAuthSession();
  if (!credential) return null;
  return `${credential.token_type} ${credential.access_token}`;
}

export function validateAuthSessionContext(
  value: unknown,
): AuthSessionContext {
  if (!value || typeof value !== "object") {
    throw new Error("AUTH_SESSION_CONTEXT_INVALID");
  }
  const record = value as Record<string, unknown>;
  let globalId: GlobalId;
  try {
    globalId = parseGlobalId(record.global_id);
  } catch {
    throw new Error("AUTH_SESSION_GLOBAL_ID_INVALID");
  }
  if (typeof record.provider !== "string" || !record.provider) {
    throw new Error("AUTH_SESSION_PROVIDER_INVALID");
  }
  if (
    !Array.isArray(record.roles) ||
    record.roles.some((role) => typeof role !== "string")
  ) {
    throw new Error("AUTH_SESSION_ROLES_INVALID");
  }
  const roles = record.roles as string[];
  return {
    global_id: globalId,
    provider: record.provider,
    roles: [...roles],
  };
}
