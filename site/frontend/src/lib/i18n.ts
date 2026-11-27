import { publicAssetPath } from "./publicAssetPath";
import enEmbedded from "../../public/locale/en.json";
import ruEmbedded from "../../public/locale/ru.json";

export type Lang =
  | "ru"
  | "en"
  | "uk"
  | "de"
  | "fr"
  | "es"
  | "it"
  | "tr"
  | "pl"
  | "da"
  | "hi"
  | "id"
  | "sw"
  | "pt"
  | "ko"
  | "ja";

// Order is UX-only (language selector). Default language is still RU.
// Per product requirement: the selector starts with EN.
export const SUPPORTED_LANGS: Lang[] = [
  "en",
  "ru",
  "uk",
  "de",
  "fr",
  "es",
  "it",
  "tr",
  "pl",
  "da",
  "hi",
  "id",
  "sw",
  "pt",
  "ko",
  "ja",
];

export function normalizeLang(input?: string | null): Lang {
  const lc = (input || "").toLowerCase();
  if (lc.startsWith("uk")) return "uk";
  if (lc.startsWith("ru")) return "ru";
  if (lc.startsWith("en")) return "en";
  if (lc.startsWith("de")) return "de";
  if (lc.startsWith("fr")) return "fr";
  if (lc.startsWith("es")) return "es";
  if (lc.startsWith("it")) return "it";
  if (lc.startsWith("tr")) return "tr";
  if (lc.startsWith("pl")) return "pl";
  if (lc.startsWith("da")) return "da";
  if (lc.startsWith("hi")) return "hi";
  if (lc.startsWith("id")) return "id";
  if (lc.startsWith("sw")) return "sw";
  if (lc.startsWith("pt")) return "pt";
  if (lc.startsWith("ko")) return "ko";
  if (lc.startsWith("ja")) return "ja";
  return "ru";
}

export type Dict = Record<string, string>;

const EMBEDDED_DICTS: Partial<Record<Lang, Dict>> = {
  en: enEmbedded as unknown as Dict,
  ru: ruEmbedded as unknown as Dict,
};

const I18N_KEY_PATTERN = /^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$/;

export function getEmbeddedDict(lang: Lang): Dict {
  return EMBEDDED_DICTS[lang] || EMBEDDED_DICTS.en || {};
}

export async function loadDict(lang: Lang): Promise<Dict> {
  try {
    const response = await fetch(publicAssetPath(`/locale/${lang}.json`), {
      cache: "default",
    });
    if (!response.ok) throw new Error(`LOCALE_HTTP_${response.status}`);
    return await response.json() as Dict;
  } catch (error) {
    const fallback = getEmbeddedDict(lang);
    if (Object.keys(fallback).length > 0) return fallback;
    throw error;
  }
}

export function isRawI18nKey(value: string): boolean {
  return I18N_KEY_PATTERN.test(value.trim());
}

export function humanizeMissingI18nKey(key: string): string {
  if (!isRawI18nKey(key)) return key;
  const tail = key.split(".").pop() || key;
  return tail
    .replace(/_/g, " ")
    .replace(/\b\w/g, (part) => part.toUpperCase());
}

export function tFromDicts(k: string, dict: Dict, ru: Dict): string {
  void ru;
  const embeddedEn = getEmbeddedDict("en");
  return (dict[k] || embeddedEn[k] || humanizeMissingI18nKey(k)).replace(/kWh\/[cс]/gi, "kWh/s");
}
