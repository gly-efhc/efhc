import { INTERFACE_VARIANT_REGISTRY, INTERFACE_VARIANT_STYLE_BINDINGS } from "./interfaceVariantRegistry";
import type { InterfaceVariantSettings } from "../types/interfaceCustomization";

export const GLOBAL_THEME_CATALOG = Object.freeze([
  { id: "01", name: "EFHC Canon", character: "Базовая синяя система EFHC. Главная тема." },
  { id: "02", name: "Deep Navy", character: "Насыщенная синяя система с объёмными active-состояниями." },
  { id: "03", name: "Violet Depth", character: "Глубокая фиолетовая система и мягкие радиальные засветки. Главная тема." },
  { id: "04", name: "Ocean Teal", character: "Тёмные морские поверхности и плотный teal." },
  { id: "05", name: "Gold Prestige", character: "Солнечная золотая статусная иерархия. Главная тема." },
  { id: "06", name: "Graphite Minimal", character: "Монохромные плоские поверхности и тонкие разделители." },
  { id: "07", name: "Aurora Glass", character: "Холодное стекло, blur и воздушное пространство." },
  { id: "08", name: "Compact Operator", character: "Плотная функциональная компоновка больших данных." },
  { id: "09", name: "Modular Dashboard", character: "Самостоятельные metric-модули и плиточный ритм." },
  { id: "10", name: "Linear Ledger", character: "Финансовые строки label/value и строгие разделители." },
  { id: "11", name: "Soft Pill", character: "Мягкие pill-формы и крупные touch-зоны." },
  { id: "12", name: "Split Focus", character: "Асимметричный ведущий показатель и вторичный контур." },
] as const);

export const GLOBAL_THEME_SLOT_CAPACITY = 15 as const;

export const GLOBAL_THEME_RESERVED_SLOT_CATALOG = Object.freeze([
  { id: "14", name: "Reserved 14", character: "Зарезервированный пустой слот для будущей Global Theme." },
  { id: "15", name: "Reserved 15", character: "Зарезервированный пустой слот для будущей Global Theme." },
] as const);

// OWNER Cycle0464: active Global Theme 13 retired. Runtime IDs are 01..12; CT10 projects to slot 10.
// Reserved catalog slots 14..15 remain capacity metadata only and must not
// participate in visible theme-dot row layout.
export const GLOBAL_THEME_SLOT_CATALOG = Object.freeze([
  ...GLOBAL_THEME_CATALOG.map((theme) => ({ ...theme, reserved: false as const })),
  ...GLOBAL_THEME_RESERVED_SLOT_CATALOG.map((theme) => ({ ...theme, reserved: true as const })),
]);

export type GlobalThemeId = (typeof GLOBAL_THEME_CATALOG)[number]["id"];

// FRONTEND_ADMIN_CYCLE_0452 — two-phase Energy PB ownership.
// A Global Theme change performs a one-time reset to the mapped starting PB ID.
// After that reset, PB remains a fully independent local control until the next
// Global Theme change. Every active Global Theme slot has its own starting PB ID even when two themes
// share the same accent. The starting geometry is common; IDs remain independent.
export const GLOBAL_THEME_ENERGY_PROGRESS_BASE = Object.freeze({
  "01": "PB-01",
  "02": "PB-28",
  "03": "PB-22",
  "04": "PB-23",
  "05": "PB-24",
  "06": "PB-25",
  "07": "PB-29",
  "08": "PB-30",
  "09": "PB-26",
  "10": "PB-27",
  "11": "PB-32",
  "12": "PB-33",
} satisfies Record<GlobalThemeId, string>);

export function getGlobalThemeEnergyProgressBase(themeId: GlobalThemeId): string {
  return GLOBAL_THEME_ENERGY_PROGRESS_BASE[themeId];
}

// FRONTEND_v127 owner decision: every authored Global Theme must cover every
// user-facing page family. Admin (AM) is explicitly excluded. Local element
// families (EI/PB/RP/XS/XA) remain independent controls inside the themed page.
export const GLOBAL_THEME_GROUPS = [
  "HS", "EG", "BN", "PH", "PT", "PC", "PA", "XH", "XC",
  "TG", "RG", "KG", "WG", "HU", "FQ", "PM", "HI", "WD",
  "AD", "BS", "ER",
] as const;

export type GlobalThemeGroup = (typeof GLOBAL_THEME_GROUPS)[number];
export type ThemeOverrideMap = Partial<Record<GlobalThemeGroup, string>>;
export type ThemeOverridesById = Partial<Record<GlobalThemeId, ThemeOverrideMap>>;
export type ThemeSlotStatus = "COMPLETE" | "INCOMPLETE";
export type ThemeCellStatus = "APPROVED" | "CANDIDATE" | "MISSING_TO_CREATE";
export type GlobalThemeSlot = {
  id: GlobalThemeId;
  name: string;
  status: ThemeSlotStatus;
  variants: Readonly<Record<GlobalThemeGroup, string | null>>;
  cells: Readonly<Record<GlobalThemeGroup, ThemeCellStatus>>;
};

// FRONTEND_v128 owner decision: Theme 13 is an approved Global Theme and every
// Historic Global Theme13 is no longer an active runtime slot. Its standalone
// design variants (WG-13, HS-13, etc.) remain valid independent user choices.
const SLOT_MATRIX: Readonly<Record<GlobalThemeId, Readonly<Record<GlobalThemeGroup, string | null>>>> = Object.freeze({
  "01": Object.freeze({
    HS: "HS-01",
    EG: "EG-01",
    BN: "BN-01",
    PH: "PH-01",
    PT: "PT-01",
    PC: "PC-01",
    PA: "PA-01",
    XH: "XH-01",
    XC: "XC-01",
    TG: "TG-01",
    RG: "RG-01",
    KG: "KG-01",
    WG: "WG-01",
    HU: "HU-01",
    FQ: "FQ-01",
    PM: "PM-01",
    HI: "HI-01",
    WD: "WD-01",
    AD: "AD-01",
    BS: "BS-01",
    ER: "ER-01",
  }),
  "02": Object.freeze({
    HS: "HS-02",
    EG: "EG-02",
    BN: "BN-02",
    PH: "PH-02",
    PT: "PT-02",
    PC: "PC-02",
    PA: "PA-02",
    XH: "XH-02",
    XC: "XC-02",
    TG: "TG-02",
    RG: "RG-02",
    KG: "KG-02",
    WG: "WG-02",
    HU: "HU-02",
    FQ: "FQ-02",
    PM: "PM-02",
    HI: "HI-02",
    WD: "WD-02",
    AD: "AD-02",
    BS: "BS-02",
    ER: "ER-02",
  }),
  "03": Object.freeze({
    HS: "HS-03",
    EG: "EG-03",
    BN: "BN-03",
    PH: "PH-03",
    PT: "PT-03",
    PC: "PC-03",
    PA: "PA-03",
    XH: "XH-03",
    XC: "XC-03",
    TG: "TG-03",
    RG: "RG-03",
    KG: "KG-03",
    WG: "WG-03",
    HU: "HU-03",
    FQ: "FQ-03",
    PM: "PM-03",
    HI: "HI-03",
    WD: "WD-03",
    AD: "AD-03",
    BS: "BS-03",
    ER: "ER-03",
  }),
  "04": Object.freeze({
    HS: "HS-04",
    EG: "EG-04",
    BN: "BN-04",
    PH: "PH-04",
    PT: "PT-04",
    PC: "PC-04",
    PA: "PA-04",
    XH: "XH-04",
    XC: "XC-04",
    TG: "TG-04",
    RG: "RG-04",
    KG: "KG-04",
    WG: "WG-04",
    HU: "HU-04",
    FQ: "FQ-04",
    PM: "PM-04",
    HI: "HI-04",
    WD: "WD-04",
    AD: "AD-04",
    BS: "BS-04",
    ER: "ER-04",
  }),
  "05": Object.freeze({
    HS: "HS-05",
    EG: "EG-05",
    BN: "BN-05",
    PH: "PH-05",
    PT: "PT-05",
    PC: "PC-05",
    PA: "PA-05",
    XH: "XH-05",
    XC: "XC-05",
    TG: "TG-05",
    RG: "RG-05",
    KG: "KG-05",
    WG: "WG-05",
    HU: "HU-05",
    FQ: "FQ-05",
    PM: "PM-05",
    HI: "HI-05",
    WD: "WD-05",
    AD: "AD-05",
    BS: "BS-05",
    ER: "ER-05",
  }),
  "06": Object.freeze({
    HS: "HS-06",
    EG: "EG-06",
    BN: "BN-06",
    PH: "PH-06",
    PT: "PT-06",
    PC: "PC-06",
    PA: "PA-06",
    XH: "XH-06",
    XC: "XC-06",
    TG: "TG-06",
    RG: "RG-06",
    KG: "KG-06",
    WG: "WG-06",
    HU: "HU-06",
    FQ: "FQ-06",
    PM: "PM-06",
    HI: "HI-06",
    WD: "WD-06",
    AD: "AD-06",
    BS: "BS-06",
    ER: "ER-06",
  }),
  "07": Object.freeze({
    HS: "HS-07",
    EG: "EG-07",
    BN: "BN-07",
    PH: "PH-07",
    PT: "PT-07",
    PC: "PC-07",
    PA: "PA-07",
    XH: "XH-07",
    XC: "XC-07",
    TG: "TG-07",
    RG: "RG-07",
    KG: "KG-07",
    WG: "WG-07",
    HU: "HU-07",
    FQ: "FQ-07",
    PM: "PM-07",
    HI: "HI-07",
    WD: "WD-07",
    AD: "AD-07",
    BS: "BS-07",
    ER: "ER-07",
  }),
  "08": Object.freeze({
    HS: "HS-08",
    EG: "EG-08",
    BN: "BN-08",
    PH: "PH-08",
    PT: "PT-08",
    PC: "PC-08",
    PA: "PA-08",
    XH: "XH-08",
    XC: "XC-08",
    TG: "TG-08",
    RG: "RG-08",
    KG: "KG-08",
    WG: "WG-08",
    HU: "HU-08",
    FQ: "FQ-08",
    PM: "PM-08",
    HI: "HI-08",
    WD: "WD-08",
    AD: "AD-08",
    BS: "BS-08",
    ER: "ER-08",
  }),
  "09": Object.freeze({
    HS: "HS-09",
    EG: "EG-09",
    BN: "BN-09",
    PH: "PH-09",
    PT: "PT-09",
    PC: "PC-09",
    PA: "PA-09",
    XH: "XH-09",
    XC: "XC-09",
    TG: "TG-09",
    RG: "RG-09",
    KG: "KG-09",
    WG: "WG-09",
    HU: "HU-09",
    FQ: "FQ-09",
    PM: "PM-09",
    HI: "HI-09",
    WD: "WD-09",
    AD: "AD-09",
    BS: "BS-09",
    ER: "ER-09",
  }),
  "10": Object.freeze({
    HS: "HS-10",
    EG: "EG-10",
    BN: "BN-10",
    PH: "PH-10",
    PT: "PT-10",
    PC: "PC-10",
    PA: "PA-10",
    XH: "XH-10",
    XC: "XC-10",
    TG: "TG-10",
    RG: "RG-10",
    KG: "KG-10",
    WG: "WG-10",
    HU: "HU-10",
    FQ: "FQ-10",
    PM: "PM-10",
    HI: "HI-10",
    WD: "WD-10",
    AD: "AD-10",
    BS: "BS-10",
    ER: "ER-10",
  }),
  "11": Object.freeze({
    HS: "HS-11",
    EG: "EG-11",
    BN: "BN-11",
    PH: "PH-11",
    PT: "PT-11",
    PC: "PC-11",
    PA: "PA-11",
    XH: "XH-11",
    XC: "XC-11",
    TG: "TG-11",
    RG: "RG-11",
    KG: "KG-11",
    WG: "WG-11",
    HU: "HU-11",
    FQ: "FQ-11",
    PM: "PM-11",
    HI: "HI-11",
    WD: "WD-11",
    AD: "AD-11",
    BS: "BS-11",
    ER: "ER-11",
  }),
  "12": Object.freeze({
    HS: "HS-12",
    EG: "EG-12",
    BN: "BN-12",
    PH: "PH-12",
    PT: "PT-12",
    PC: "PC-12",
    PA: "PA-12",
    XH: "XH-12",
    XC: "XC-12",
    TG: "TG-12",
    RG: "RG-12",
    KG: "KG-12",
    WG: "WG-12",
    HU: "HU-12",
    FQ: "FQ-12",
    PM: "PM-12",
    HI: "HI-12",
    WD: "WD-12",
    AD: "AD-12",
    BS: "BS-12",
    ER: "ER-12",
  }),
});

export const GLOBAL_THEME_SLOTS: readonly GlobalThemeSlot[] = Object.freeze(
  GLOBAL_THEME_CATALOG.map((definition) => {
    const variants = SLOT_MATRIX[definition.id];
    const complete = GLOBAL_THEME_GROUPS.every((group) => Boolean(variants[group]));
    const cells = Object.fromEntries(GLOBAL_THEME_GROUPS.map((group) => [
      group,
      variants[group] ? "APPROVED" : "MISSING_TO_CREATE",
    ])) as Record<GlobalThemeGroup, ThemeCellStatus>;
    return Object.freeze({
      id: definition.id,
      name: definition.name,
      status: complete ? "COMPLETE" as const : "INCOMPLETE" as const,
      variants,
      cells: Object.freeze(cells),
    });
  }),
);

export const RETIRED_GLOBAL_THEME_IDS = Object.freeze([] as const);
export const GLOBAL_THEME_SELECTABLE_IDS = Object.freeze(GLOBAL_THEME_CATALOG.map((theme) => theme.id));
export const COMPLETE_GLOBAL_THEME_IDS = Object.freeze(GLOBAL_THEME_SLOTS.filter((theme) => theme.status === "COMPLETE").map((theme) => theme.id));

export type CompleteGlobalTheme = { id: GlobalThemeId; name: string; variants: Readonly<Record<GlobalThemeGroup, string>>; };

const DEFAULT_THEME_ID: GlobalThemeId = "01";
const DEFAULT_THEME_VARIANTS = SLOT_MATRIX[DEFAULT_THEME_ID] as Readonly<Record<GlobalThemeGroup, string>>;

export const COMPLETE_GLOBAL_THEMES: readonly CompleteGlobalTheme[] = Object.freeze(
  GLOBAL_THEME_SLOTS.filter((slot) => slot.status === "COMPLETE").map((slot) => Object.freeze({
    id: slot.id,
    name: slot.name,
    variants: slot.variants as Readonly<Record<GlobalThemeGroup, string>>,
  })),
);

export function normalizeGlobalThemeId(value: unknown): GlobalThemeId {
  const raw = typeof value === "string" ? value.padStart(2, "0") : "";
  return (GLOBAL_THEME_SELECTABLE_IDS.includes(raw as GlobalThemeId) ? raw : DEFAULT_THEME_ID) as GlobalThemeId;
}

export function getGlobalThemeDefinition(id: string) { return GLOBAL_THEME_CATALOG.find((theme) => theme.id === id) || null; }
export function getGlobalThemeSlot(id: string): GlobalThemeSlot | null { return GLOBAL_THEME_SLOTS.find((theme) => theme.id === id) || null; }
export function getCompleteGlobalTheme(id: string): CompleteGlobalTheme | null { return COMPLETE_GLOBAL_THEMES.find((theme) => theme.id === id) || null; }

/** All accepted Global Theme slots are complete. Theme 01 remains a defensive runtime fallback only for corrupt/unknown state. */
export function getGlobalThemeRuntimeVariants(id: string): Readonly<Record<GlobalThemeGroup, string>> {
  const slot = getGlobalThemeSlot(normalizeGlobalThemeId(id)) || getGlobalThemeSlot(DEFAULT_THEME_ID)!;
  // Historical slot matrix is authoring provenance, not a new numbered choice.
  // Convert a physical style only when that design still exists in the active catalog.
  return Object.freeze(Object.fromEntries(GLOBAL_THEME_GROUPS.map((group) => {
    const style = slot.variants[group];
    const selection = Object.entries(INTERFACE_VARIANT_STYLE_BINDINGS[group])
      .find(([, rendered]) => rendered === style)?.[0];
    return [group, selection || INTERFACE_VARIANT_REGISTRY[group][0]];
  })) as Record<GlobalThemeGroup, string>);
}

export function findCompleteGlobalThemeIndex(settings: InterfaceVariantSettings): number {
  return COMPLETE_GLOBAL_THEMES.findIndex((theme) => GLOBAL_THEME_GROUPS.every((group) => settings[group] === theme.variants[group]));
}
export function inferCompleteGlobalThemeId(settings: InterfaceVariantSettings): GlobalThemeId {
  const index = findCompleteGlobalThemeIndex(settings);
  return COMPLETE_GLOBAL_THEMES[index]?.id || DEFAULT_THEME_ID;
}

export function applyGlobalThemeSlot(settings: InterfaceVariantSettings, themeId: string, overrides?: ThemeOverrideMap): InterfaceVariantSettings {
  return { ...settings, ...getGlobalThemeRuntimeVariants(themeId), ...(overrides || {}) };
}

export function applyCompleteGlobalTheme(settings: InterfaceVariantSettings, theme: CompleteGlobalTheme, overrides?: ThemeOverrideMap): InterfaceVariantSettings {
  return applyGlobalThemeSlot(settings, theme.id, overrides);
}

export function cycleGlobalThemeRecord(currentId: string, direction: 1 | -1): GlobalThemeSlot {
  const current = normalizeGlobalThemeId(currentId);
  const index = Math.max(0, GLOBAL_THEME_SELECTABLE_IDS.indexOf(current));
  const next = (index + direction + GLOBAL_THEME_SELECTABLE_IDS.length) % GLOBAL_THEME_SELECTABLE_IDS.length;
  return getGlobalThemeSlot(GLOBAL_THEME_SELECTABLE_IDS[next] || DEFAULT_THEME_ID)!;
}

export function cycleCompleteGlobalThemeRecord(currentId: string, direction: 1 | -1): CompleteGlobalTheme {
  const currentIndex = COMPLETE_GLOBAL_THEME_IDS.indexOf(normalizeGlobalThemeId(currentId));
  const start = currentIndex >= 0 ? currentIndex : 0;
  const next = (start + direction + COMPLETE_GLOBAL_THEME_IDS.length) % COMPLETE_GLOBAL_THEME_IDS.length;
  return getCompleteGlobalTheme(COMPLETE_GLOBAL_THEME_IDS[next] || DEFAULT_THEME_ID)!;
}

export function cycleCompleteGlobalTheme(settings: InterfaceVariantSettings, direction: 1 | -1): InterfaceVariantSettings {
  const current = inferCompleteGlobalThemeId(settings);
  return applyGlobalThemeSlot(settings, cycleCompleteGlobalThemeRecord(current, direction).id);
}

export function buildThemeOverride(themeId: string, effective: InterfaceVariantSettings): ThemeOverrideMap {
  const base = getGlobalThemeRuntimeVariants(themeId);
  const out: ThemeOverrideMap = {};
  for (const group of GLOBAL_THEME_GROUPS) if (effective[group] !== base[group]) out[group] = effective[group];
  return out;
}
