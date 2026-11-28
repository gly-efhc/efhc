import { mapErrorToUi, type UiError } from "./publicError";

type Translator = (key: string) => string;

const ACTION_FAILED = [
  "Действие временно недоступно.",
  "Обновите данные и попробуйте снова.",
].join(" ");

const LOAD_FAILED = [
  "Данные временно недоступны.",
  "Обновите раздел.",
].join(" ");

const SAFE_DETAIL = "Данные временно недоступны.";

const FALLBACKS: Record<string, string> = {
  "admin.errors.action_failed": ACTION_FAILED,
  "admin.errors.load_failed": LOAD_FAILED,
  "admin.errors.data_unavailable_detail": SAFE_DETAIL,
};

export function adminUiError(
  error: unknown,
  fallbackKey = "admin.errors.action_failed",
): UiError {
  const ui = mapErrorToUi(error, fallbackKey);
  const isAuth = ui.kind === "auth" || ui.kind === "permission";
  return {
    ...ui,
    i18nKey: isAuth ? "common.session_expired" : fallbackKey,
    fallbackText: FALLBACKS[fallbackKey] || ACTION_FAILED,
    severity: ui.severity === "silent" ? "inline" : ui.severity,
  };
}

export function adminUiErrorMessage(
  error: unknown,
  t?: Translator,
  fallbackKey = "admin.errors.action_failed",
): string {
  const ui = adminUiError(error, fallbackKey);
  if (t) {
    const translated = t(ui.i18nKey);
    if (translated && translated !== ui.i18nKey) return translated;
  }
  return ui.fallbackText;
}

export function adminSafeLoadError(
  error: unknown,
  t?: Translator,
): string {
  return adminUiErrorMessage(error, t, "admin.errors.load_failed");
}
