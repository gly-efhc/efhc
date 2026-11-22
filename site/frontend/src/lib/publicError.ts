import { ApiError } from "./api";

export type UiErrorKind =
  | "validation"
  | "auth"
  | "permission"
  | "not_found"
  | "conflict"
  | "rate_limit"
  | "offline"
  | "server"
  | "unknown";

export type UiError = {
  kind: UiErrorKind;
  i18nKey: string;
  fallbackText: string;
  retryable: boolean;
  severity: "silent" | "inline" | "toast" | "page";
  requestId?: string;
  technical?: unknown;
};

const OFFLINE_RE = new RegExp(
  [
    "failed to fetch",
    "networkerror",
    "network request failed",
    "load failed",
  ].join("|"),
  "i",
);

const FALLBACKS = {
  auth: "Сессию нужно обновить. Перезапустите приложение.",
  permission: "Действие сейчас недоступно для этой учётной записи.",
  notFound: "Раздел не найден.",
  conflict: [
    "Действие сейчас недоступно.",
    "Обновите экран и попробуйте снова.",
  ].join(" "),
  rateLimit: "Слишком много действий. Попробуйте немного позже.",
  server: "Сервис обновляется. Попробуйте ещё раз.",
  validation: [
    "Действие требует уточнения.",
    "Проверьте данные и попробуйте снова.",
  ].join(" "),
  offline: [
    "Подключение нестабильно.",
    "Проверьте интернет и повторите действие.",
  ].join(" "),
  unknown: "Данные временно недоступны. Попробуйте обновить экран.",
};

function looksOffline(error: unknown): boolean {
  if (!error) return false;
  if (typeof navigator !== "undefined" && navigator.onLine === false) {
    return true;
  }
  const name = error instanceof Error ? error.name : "";
  if (name === "AbortError") return true;
  const text = error instanceof Error
    ? error.message
    : String(error || "");
  return OFFLINE_RE.test(text);
}

function apiUi(
  error: ApiError,
  kind: UiErrorKind,
  i18nKey: string,
  fallbackText: string,
  retryable: boolean,
  severity: UiError["severity"],
): UiError {
  return {
    kind,
    i18nKey,
    fallbackText,
    retryable,
    severity,
    requestId: error.requestId,
    technical: error.payload,
  };
}

export function mapErrorToUi(
  error: unknown,
  fallbackKey = "common.load_error",
): UiError {
  if (error instanceof ApiError) {
    if (error.status === 401) {
      return apiUi(
        error,
        "auth",
        "common.session_expired",
        FALLBACKS.auth,
        true,
        "page",
      );
    }
    if (error.status === 403) {
      return apiUi(
        error,
        "permission",
        "common.action_not_available_now",
        FALLBACKS.permission,
        true,
        "page",
      );
    }
    if (error.status === 404) {
      return apiUi(
        error,
        "not_found",
        "common.not_found",
        FALLBACKS.notFound,
        false,
        "page",
      );
    }
    if (error.status === 409) {
      return apiUi(
        error,
        "conflict",
        "common.action_not_available_now",
        FALLBACKS.conflict,
        true,
        "inline",
      );
    }
    if (error.status === 429) {
      return apiUi(
        error,
        "rate_limit",
        "common.try_later",
        FALLBACKS.rateLimit,
        true,
        "inline",
      );
    }
    if (error.status >= 500 || error.status === 408) {
      return apiUi(
        error,
        "server",
        "common.service_temporarily_unavailable",
        FALLBACKS.server,
        true,
        "page",
      );
    }
    if (error.status === 400 || error.status === 422) {
      return apiUi(
        error,
        "validation",
        "common.action_not_available_now",
        FALLBACKS.validation,
        false,
        "inline",
      );
    }
  }
  if (looksOffline(error)) {
    return {
      kind: "offline",
      i18nKey: "common.offline",
      fallbackText: FALLBACKS.offline,
      retryable: true,
      severity: "page",
      technical: error,
    };
  }
  return {
    kind: "unknown",
    i18nKey: fallbackKey,
    fallbackText: FALLBACKS.unknown,
    retryable: true,
    severity: "inline",
    technical: error,
  };
}

export function publicApiErrorMessage(
  error: unknown,
  t: (key: string) => string,
  fallbackKey = "common.load_error",
): string {
  const ui = mapErrorToUi(error, fallbackKey);
  const translated = t(ui.i18nKey);
  if (translated && translated !== ui.i18nKey) return translated;
  const fallback = t(fallbackKey);
  return fallback && fallback !== fallbackKey
    ? fallback
    : ui.fallbackText;
}
