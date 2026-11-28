import { ApiError } from "./api";
import { getTelegramWebApp } from "./telegram";

const STORAGE_KEY = "efhc.referral.start.v1";
const REFERRAL_PATTERN = /^[A-Za-z0-9_-]{4,64}$/;
const QUERY_KEYS = [
  "referral_start_param",
  "tgWebAppStartParam",
  "startapp",
  "start",
  "ref",
] as const;

type StoredReferralStart =
  | Readonly<{ status: "ready"; code: string }>
  | Readonly<{ status: "invalid" }>;

function getSessionStorage(): Storage | null {
  try {
    return globalThis.sessionStorage ?? null;
  } catch {
    return null;
  }
}

function normalizeReferralStartParam(value: unknown): string | null {
  if (typeof value !== "string") return null;
  let code = value.trim();
  if (!code) return null;
  if (code.toLowerCase().startsWith("ref_")) {
    code = code.slice(4).trim();
  }
  if (!REFERRAL_PATTERN.test(code)) return null;
  return code;
}

function readStoredState(): StoredReferralStart | null {
  const storage = getSessionStorage();
  const raw = storage?.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    if (
      parsed.status === "ready"
      && typeof parsed.code === "string"
      && REFERRAL_PATTERN.test(parsed.code)
    ) {
      return { status: "ready", code: parsed.code };
    }
    if (parsed.status === "invalid") return { status: "invalid" };
  } catch {
    // Повреждённая transport-запись удаляется fail closed.
  }
  storage?.removeItem(STORAGE_KEY);
  return null;
}

function writeStoredState(state: StoredReferralStart): void {
  const storage = getSessionStorage();
  if (!storage) return;
  storage.setItem(STORAGE_KEY, JSON.stringify(state));
}

function telegramStartParam(): unknown {
  try {
    return getTelegramWebApp()?.initDataUnsafe?.start_param;
  } catch {
    return null;
  }
}

type FirstEntryCandidate = Readonly<{
  supplied: boolean;
  value: unknown;
}>;

function queryStartParam(): FirstEntryCandidate {
  try {
    const url = new URL(window.location.href);
    for (const key of QUERY_KEYS) {
      if (url.searchParams.has(key)) {
        return { supplied: true, value: url.searchParams.get(key) };
      }
    }
  } catch {
    // URL недоступен — transport остаётся пустым.
  }
  return { supplied: false, value: null };
}

function firstEntryCandidate(): FirstEntryCandidate {
  const telegramValue = telegramStartParam();
  if (
    telegramValue !== null
    && telegramValue !== undefined
    && telegramValue !== ""
  ) {
    return { supplied: true, value: telegramValue };
  }
  return queryStartParam();
}

function scrubReferralQuery(): void {
  try {
    const url = new URL(window.location.href);
    let changed = false;
    for (const key of QUERY_KEYS) {
      if (url.searchParams.has(key)) {
        url.searchParams.delete(key);
        changed = true;
      }
    }
    if (changed) {
      window.history.replaceState(
        window.history.state,
        "",
        `${url.pathname}${url.search}${url.hash}`,
      );
    }
  } catch {
    // Удаление query — privacy best effort.
  }
}

export function captureReferralStartParamFromFirstEntry(): void {
  if (typeof window === "undefined") return;
  if (readStoredState()) {
    scrubReferralQuery();
    return;
  }
  const candidate = firstEntryCandidate();
  if (!candidate.supplied) return;
  const normalized = normalizeReferralStartParam(candidate.value);
  writeStoredState(
    normalized === null
      ? { status: "invalid" }
      : { status: "ready", code: normalized },
  );
  scrubReferralQuery();
}

export function readReferralStartParamForLogin(): string | null {
  const state = readStoredState();
  if (!state) return null;
  if (state.status === "invalid") {
    throw new Error("REFERRAL_START_PARAM_INVALID");
  }
  return state.code;
}

export function clearReferralStartParam(): void {
  getSessionStorage()?.removeItem(STORAGE_KEY);
}

function backendErrorReason(error: ApiError): string | null {
  if (!error.payload || typeof error.payload !== "object") return null;
  const payload = error.payload as Record<string, unknown>;
  const detail = payload.detail;
  if (!detail || typeof detail !== "object") return null;
  const detailRecord = detail as Record<string, unknown>;
  const direct = detailRecord.error;
  if (typeof direct === "string") return direct;
  const details = detailRecord.details;
  if (!details || typeof details !== "object") return null;
  const reason = (details as Record<string, unknown>).reason;
  return typeof reason === "string" ? reason : null;
}

export function clearReferralStartParamAfterFinalError(
  error: unknown,
): void {
  if (
    error instanceof Error
    && error.message === "REFERRAL_START_PARAM_INVALID"
  ) {
    clearReferralStartParam();
    return;
  }
  if (!(error instanceof ApiError)) return;
  const reason = backendErrorReason(error);
  const finalReasons = new Set([
    "auth.referral_start_invalid",
    "invalid_code",
    "REFERRAL_CODE_INVALID",
    "REFERRAL_CODE_NOT_FOUND",
  ]);
  if (error.status === 400 || error.status === 422) {
    clearReferralStartParam();
    return;
  }
  if (reason && finalReasons.has(reason)) {
    clearReferralStartParam();
  }
}

export function buildReferralStartTransportContract():
  Record<string, unknown> {
  return {
    cycle: 1638,
    storage: "sessionStorage",
    persistentStorage: false,
    rawValueStored: false,
    queryScrubbed: true,
    existingAccountLateBind: false,
  };
}
