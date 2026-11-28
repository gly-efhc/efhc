import type { Lang } from "./i18n";

import {
  getTelegramLang as tgGetLang,
  getTelegramUser,
} from "./telegram";

// Guard: do not access window Telegram directly outside telegram.ts.

export function getTelegramUserId(): number | null {
  const u = getTelegramUser();
  return u?.id ?? null;
}

export function getTelegramLang(): Lang | null {
  return tgGetLang();
}
