import type { GlobalThemeId } from "./globalThemeRegistry";

export const COLOR_THEME_CATALOG = Object.freeze([
  { id: "CT-01", slot: "01", name: "Blue", nameRu: "Голубой", accent: "#6EA8FF" },
  { id: "CT-02", slot: "02", name: "Light Blue", nameRu: "Светло-синий", accent: "#73AEFC" },
  { id: "CT-03", slot: "03", name: "Violet", nameRu: "Фиолетовый", accent: "#A78BFA" },
  { id: "CT-04", slot: "04", name: "Azure", nameRu: "Лазурный", accent: "#229ED9" },
  { id: "CT-05", slot: "05", name: "Gold", nameRu: "Золотой", accent: "#E5BF58" },
  { id: "CT-06", slot: "06", name: "Fuchsia", nameRu: "Фуксия", accent: "#D946EF" },
  { id: "CT-07", slot: "07", name: "Sky Blue", nameRu: "Небесно-голубой", accent: "#7FB4FF" },
  { id: "CT-08", slot: "08", name: "Indigo", nameRu: "Индиго", accent: "#8F86FF" },
  { id: "CT-09", slot: "09", name: "Teal", nameRu: "Бирюзовый", accent: "#58C7B4" },
  { id: "CT-10", slot: "10", name: "Muted Gold", nameRu: "Приглушённое золото", accent: "#C5A15A" },
] as const);

export type ColorThemeId = (typeof COLOR_THEME_CATALOG)[number]["id"];

export const LEGACY_GLOBAL_THEME_TO_COLOR_THEME = Object.freeze({
  "01": "CT-01",
  "02": "CT-02",
  "03": "CT-03",
  "04": "CT-04",
  "05": "CT-05",
  "06": "CT-06",
  "07": "CT-07",
  "08": "CT-08",
  "09": "CT-09",
  "10": "CT-06",
  "11": "CT-03",
  "12": "CT-03",
  "13": "CT-10",
} satisfies Record<string, ColorThemeId>);

export const COLOR_THEME_TO_RUNTIME_LEGACY_THEME = Object.freeze({
  "CT-01": "01",
  "CT-02": "02",
  "CT-03": "03",
  "CT-04": "04",
  "CT-05": "05",
  "CT-06": "06",
  "CT-07": "07",
  "CT-08": "08",
  "CT-09": "09",
  "CT-10": "10",
} satisfies Record<ColorThemeId, GlobalThemeId>);

const COLOR_THEME_IDS = new Set<string>(COLOR_THEME_CATALOG.map((row) => row.id));

export function normalizeColorThemeId(value: unknown): ColorThemeId {
  const candidate = typeof value === "string" ? value.toUpperCase() : "";
  return COLOR_THEME_IDS.has(candidate) ? candidate as ColorThemeId : "CT-01";
}


export function getColorThemeDefinition(id: unknown) {
  const normalized = normalizeColorThemeId(id);
  return COLOR_THEME_CATALOG.find((theme) => theme.id === normalized)!;
}

export function cycleColorThemeRecord(currentId: unknown, direction: 1 | -1) {
  const current = normalizeColorThemeId(currentId);
  const index = COLOR_THEME_CATALOG.findIndex((theme) => theme.id === current);
  const next = (index + direction + COLOR_THEME_CATALOG.length) % COLOR_THEME_CATALOG.length;
  return COLOR_THEME_CATALOG[next] || COLOR_THEME_CATALOG[0];
}

export function colorThemeIdFromLegacyGlobalTheme(themeId: GlobalThemeId | "13"): ColorThemeId {
  return LEGACY_GLOBAL_THEME_TO_COLOR_THEME[themeId];
}

export function runtimeLegacyThemeIdForColorTheme(colorThemeId: ColorThemeId): GlobalThemeId {
  return COLOR_THEME_TO_RUNTIME_LEGACY_THEME[colorThemeId];
}

export function normalizeRuntimeLegacyThemeForColor(
  legacyThemeId: GlobalThemeId,
  colorThemeId: ColorThemeId,
): GlobalThemeId {
  return legacyThemeId === "10" && colorThemeId === "CT-10"
    ? "10"
    : LEGACY_GLOBAL_THEME_TO_COLOR_THEME[legacyThemeId] === colorThemeId
    ? legacyThemeId
    : runtimeLegacyThemeIdForColorTheme(colorThemeId);
}

// Cycle0464/08 OWNER exception to v17 chroma-only switching: just the two
// progress-bar design selections reset on a real color-theme change.
// Other independent designs, including EI, remain untouched.
export const COLOR_THEME_PROGRESS_STARTER = Object.freeze({
  "CT-01": "PB-01", "CT-02": "PB-28", "CT-03": "PB-22",
  "CT-04": "PB-23", "CT-05": "PB-24", "CT-06": "PB-25",
  "CT-07": "PB-29", "CT-08": "PB-30", "CT-09": "PB-26",
  "CT-10": "PB-27",
} satisfies Record<ColorThemeId, string>);
