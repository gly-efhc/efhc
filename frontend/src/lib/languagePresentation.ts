import type { Lang } from "./i18n";

const FLAGS: Record<Lang, string> = {
  ru: "🇷🇺",
  en: "🇺🇸",
  uk: "🇺🇦",
  de: "🇩🇪",
  fr: "🇫🇷",
  es: "🇪🇸",
  it: "🇮🇹",
  tr: "🇹🇷",
  pl: "🇵🇱",
  da: "🇩🇰",
  hi: "🇮🇳",
  id: "🇮🇩",
  sw: "🇰🇪",
  pt: "🇵🇹",
  ko: "🇰🇷",
  ja: "🇯🇵",
};

const PENDING_LOCALE_NAMES: Partial<Record<Lang, string>> = {};

export function languageFlag(lang: Lang): string {
  return FLAGS[lang] || "🏳️";
}

export function languageDisplayName(lang: Lang, translatedName: string): string {
  return PENDING_LOCALE_NAMES[lang] || translatedName;
}
