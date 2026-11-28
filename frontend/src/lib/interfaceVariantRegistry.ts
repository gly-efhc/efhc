import type {
  InterfaceVariantGroup,
  InterfaceVariantSettings,
} from "../types/interfaceCustomization";
import { COLOR_THEME_CATALOG, COLOR_THEME_PROGRESS_STARTER } from "./colorThemeRegistry";

function numbered(prefix: string, count: number): readonly string[] {
  return Object.freeze(
    Array.from(
      { length: count },
      (_, index) => `${prefix}-${String(index + 1).padStart(2, "0")}`,
    ),
  );
}

// One model catalog, independent persisted PB/RP selections.
export const PROGRESS_MODEL_LIBRARY: readonly string[] = Object.freeze([
    ...COLOR_THEME_CATALOG.map(({ id }) => COLOR_THEME_PROGRESS_STARTER[id]),
    "PB-02", "PB-04", "PB-05", "PB-07", "PB-15", "PB-17", "PB-19", "PB-21", "PB-06", "PB-08", "PB-09", "PB-10", "PB-18", "PB-20",
  ]);

export const INTERFACE_VARIANT_REGISTRY: Readonly<
  Record<InterfaceVariantGroup, readonly string[]>
> = Object.freeze({
  SC: numbered("SC", 4),
  HB: numbered("HB", 11),
  HS: numbered("HS", 6),
  EG: numbered("EG", 1),
  BN: numbered("BN", 5),
  EI: Object.freeze(["EI-07"]),
  PB: PROGRESS_MODEL_LIBRARY,
  RP: Object.freeze(PROGRESS_MODEL_LIBRARY.map(id => id.replace("PB-", "RP-"))),
  PH: numbered("PH", 6),
  PT: numbered("PT", 5),
  PC: numbered("PC", 9),
  PA: numbered("PA", 6),
  XH: numbered("XH", 6),
  XS: numbered("XS", 1),
  XC: numbered("XC", 1),
  XA: numbered("XA", 1),
  TG: numbered("TG", 4),
  RG: numbered("RG", 13),
  KG: numbered("KG", 10),
  WG: numbered("WG", 1),
  HU: numbered("HU", 1),
  FQ: numbered("FQ", 6),
  PM: numbered("PM", 13),
  HI: numbered("HI", 3),
  WD: numbered("WD", 5),
  AD: numbered("AD", 13),
  BS: numbered("BS", 13),
  ER: numbered("ER", 13),
  AM: numbered("AM", 12),
});

// Presentation order only: keep stored selections and physical CSS bindings intact.
// OWNER: the ten accepted CT starters occupy the first ten PB/RP positions.
function progressSelectionOrder(group: "PB" | "RP"): readonly string[] {
  const starters = COLOR_THEME_CATALOG.map(({ id }) =>
    COLOR_THEME_PROGRESS_STARTER[id].replace("PB-", `${group}-`),
  );
  const starterIds = new Set(starters);
  return Object.freeze([
    ...starters,
    ...INTERFACE_VARIANT_REGISTRY[group].filter((id) => !starterIds.has(id)),
  ]);
}

const PROGRESS_SELECTION_ORDER = Object.freeze({
  PB: progressSelectionOrder("PB"),
  RP: progressSelectionOrder("RP"),
});

export function getInterfaceVariantSelectionOrder(group: InterfaceVariantGroup): readonly string[] {
  return group === "PB" || group === "RP"
    ? PROGRESS_SELECTION_ORDER[group]
    : INTERFACE_VARIANT_REGISTRY[group];
}

function physicalSlotCapacity(variants: readonly string[]): number {
  const highestAuthoredSlot = variants.reduce((highest, variant) => {
    const match = variant.match(/-(\d{2})$/);
    return Math.max(highest, match ? Number(match[1]) : 0);
  }, 0);
  // Preserve the historical 20-slot capacity for existing families while allowing
  // local families such as PB/RP to scale beyond 20 without aliasing or clipping.
  return Math.max(20, highestAuthoredSlot);
}

function toPhysicalSlots(variants: readonly string[]): readonly (string | null)[] {
  const capacity = physicalSlotCapacity(variants);
  const byNumber = new Map<number, string>();
  for (const variant of variants) {
    const match = variant.match(/-(\d{2})$/);
    const slot = match ? Number(match[1]) : 0;
    if (slot >= 1 && slot <= capacity) byNumber.set(slot, variant);
  }
  return Object.freeze(
    Array.from({ length: capacity }, (_, index) => byNumber.get(index + 1) || null),
  );
}

/**
 * Canonical consecutive numbered positions. Historical style IDs live only in
 * INTERFACE_VARIANT_STYLE_BINDINGS. Physical selection slots have no gaps.
 */
export function getInterfaceVariantAuthoredSlotCount(
  group: InterfaceVariantGroup,
): number {
  // Energy's OWNER-approved reduced list has contiguous display positions,
  // while persisted selections retain their original physical model identities.
  if (group === "PB" || group === "RP") return INTERFACE_VARIANT_REGISTRY[group].length;
  return INTERFACE_VARIANT_REGISTRY[group].reduce((highest, variant) => {
    const match = variant.match(/-(\d{2})$/);
    return Math.max(highest, match ? Number(match[1]) : 0);
  }, 0);
}

export const INTERFACE_VARIANT_SLOT_REGISTRY: Readonly<
  Record<InterfaceVariantGroup, readonly (string | null)[]>
> = Object.freeze(
  Object.fromEntries(
    Object.entries(INTERFACE_VARIANT_REGISTRY).map(([group, variants]) => [
      group,
      group === "PB" || group === "RP"
        ? PROGRESS_SELECTION_ORDER[group]
        : toPhysicalSlots(variants),
    ]),
  ) as Record<InterfaceVariantGroup, readonly (string | null)[]>,
);

export const DEFAULT_INTERFACE_VARIANTS: InterfaceVariantSettings = {
  SC: "SC-01",
  HB: "HB-01",
  HS: "HS-01",
  EG: "EG-01",
  BN: "BN-01",
  EI: "EI-07",
  PB: "PB-01",
  RP: "RP-01",
  PH: "PH-01",
  PT: "PT-01",
  PC: "PC-01",
  PA: "PA-01",
  XH: "XH-01",
  XS: "XS-01",
  XC: "XC-01",
  XA: "XA-01",
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
  AM: "AM-01",
};

// OWNER 0546: numeric selection IDs are canonical 01..N in all 29 groups.
// CSS retains authored style IDs as an internal rendering implementation.
// This table is NOT a stored-ID migration: pre-0546 selections are reset on load.
export const INTERFACE_VARIANT_STYLE_BINDINGS: Readonly<Record<InterfaceVariantGroup, Readonly<Record<string, string>>>> =
  Object.freeze({"SC":{},"HB":{"HB-07":"HB-08","HB-08":"HB-09","HB-09":"HB-11","HB-10":"HB-12","HB-11":"HB-13"},"HS":{"HS-01":"HS-03","HS-02":"HS-06","HS-03":"HS-07","HS-04":"HS-10","HS-05":"HS-11","HS-06":"HS-13"},"EG":{},"BN":{"BN-01":"BN-02","BN-02":"BN-01","BN-04":"BN-10","BN-05":"BN-13"},"EI":{},"PB":{"PB-08":"PB-09","PB-09":"PB-10","PB-10":"PB-11","PB-11":"PB-12","PB-12":"PB-13","PB-13":"PB-14","PB-14":"PB-15","PB-15":"PB-16","PB-16":"PB-18","PB-17":"PB-19","PB-18":"PB-20","PB-19":"PB-21","PB-20":"PB-22","PB-21":"PB-23","PB-22":"PB-24","PB-23":"PB-25","PB-24":"PB-26","PB-25":"PB-27","PB-26":"PB-28","PB-27":"PB-29","PB-28":"PB-30","PB-29":"PB-31","PB-30":"PB-32","PB-31":"PB-33","PB-32":"PB-34","PB-33":"PB-35"},"RP":{"RP-01":"PB-01","RP-02":"PB-02","RP-03":"PB-03","RP-04":"PB-04","RP-05":"PB-05","RP-06":"PB-06","RP-07":"PB-07","RP-08":"PB-09","RP-09":"PB-10","RP-10":"PB-11","RP-11":"PB-12","RP-12":"PB-13","RP-13":"PB-14","RP-14":"PB-15","RP-15":"PB-16","RP-16":"PB-18","RP-17":"PB-19","RP-18":"PB-20","RP-19":"PB-21","RP-20":"PB-22","RP-21":"PB-23","RP-22":"PB-24","RP-23":"PB-25","RP-24":"PB-26","RP-25":"PB-27","RP-26":"PB-28","RP-27":"PB-29","RP-28":"PB-30","RP-29":"PB-31","RP-30":"PB-32","RP-31":"PB-33","RP-32":"PB-34","RP-33":"PB-35"},"PH":{"PH-05":"PH-10","PH-06":"PH-12"},"PT":{"PT-04":"PT-10","PT-05":"PT-11"},"PC":{"PC-07":"PC-08","PC-08":"PC-09","PC-09":"PC-10"},"PA":{"PA-03":"PA-04","PA-04":"PA-10","PA-05":"PA-11","PA-06":"PA-12"},"XH":{"XH-03":"XH-04","XH-04":"XH-07","XH-05":"XH-10","XH-06":"XH-12"},"XS":{},"XC":{},"XA":{},"TG":{"TG-04":"TG-09"},"RG":{},"KG":{},"WG":{},"HU":{},"FQ":{"FQ-06":"FQ-13"},"PM":{},"HI":{"HI-02":"HI-03","HI-03":"HI-04"},"WD":{"WD-03":"WD-06","WD-04":"WD-10","WD-05":"WD-13"},"AD":{},"BS":{},"ER":{},"AM":{}} as Record<InterfaceVariantGroup, Record<string, string>>);

export function resolveInterfaceVariantStyle(group: InterfaceVariantGroup, selection: string): string {
  const canonical = normalizeInterfaceVariant(group, selection);
  return INTERFACE_VARIANT_STYLE_BINDINGS[group][canonical] || canonical;
}

export function normalizeInterfaceVariant(
  group: InterfaceVariantGroup,
  value: unknown,
): string {
  const raw = typeof value === "string" ? value : "";
  const allowed = INTERFACE_VARIANT_REGISTRY[group];
  // New numeric catalog: invalid or old selections reset to the group's first slot.
  // No retired-ID aliases or inferred remapping is permitted.
  return allowed.includes(raw) ? raw : DEFAULT_INTERFACE_VARIANTS[group];
}

export function normalizeInterfaceVariants(
  value: unknown,
): InterfaceVariantSettings {
  const input = value && typeof value === "object"
    ? value as Partial<Record<InterfaceVariantGroup, unknown>>
    : {};
  return {
    SC: normalizeInterfaceVariant("SC", input.SC),
    HB: normalizeInterfaceVariant("HB", input.HB),
    HS: normalizeInterfaceVariant("HS", input.HS),
    EG: normalizeInterfaceVariant("EG", input.EG),
    BN: normalizeInterfaceVariant("BN", input.BN),
    EI: normalizeInterfaceVariant("EI", input.EI),
    PB: normalizeInterfaceVariant("PB", input.PB),
    RP: normalizeInterfaceVariant("RP", input.RP),
    PH: normalizeInterfaceVariant("PH", input.PH),
    PT: normalizeInterfaceVariant("PT", input.PT),
    PC: normalizeInterfaceVariant("PC", input.PC),
    PA: normalizeInterfaceVariant("PA", input.PA),
    XH: normalizeInterfaceVariant("XH", input.XH),
    XS: normalizeInterfaceVariant("XS", input.XS),
    XC: normalizeInterfaceVariant("XC", input.XC),
    XA: normalizeInterfaceVariant("XA", input.XA),
    TG: normalizeInterfaceVariant("TG", input.TG),
    RG: normalizeInterfaceVariant("RG", input.RG),
    KG: normalizeInterfaceVariant("KG", input.KG),
    WG: normalizeInterfaceVariant("WG", input.WG),
    HU: normalizeInterfaceVariant("HU", input.HU),
    FQ: normalizeInterfaceVariant("FQ", input.FQ),
    PM: normalizeInterfaceVariant("PM", input.PM),
    HI: normalizeInterfaceVariant("HI", input.HI),
    WD: normalizeInterfaceVariant("WD", input.WD),
    AD: normalizeInterfaceVariant("AD", input.AD),
    BS: normalizeInterfaceVariant("BS", input.BS),
    ER: normalizeInterfaceVariant("ER", input.ER),
    AM: normalizeInterfaceVariant("AM", input.AM),
  };
}

export function cycleInterfaceVariant(
  settings: InterfaceVariantSettings,
  group: InterfaceVariantGroup,
  direction: 1 | -1,
): InterfaceVariantSettings {
  const variants = getInterfaceVariantSelectionOrder(group);
  const current = normalizeInterfaceVariant(group, settings[group]);
  const currentIndex = Math.max(0, variants.indexOf(current));
  const nextIndex = (
    currentIndex + direction + variants.length
  ) % variants.length;
  return {
    ...settings,
    [group]: variants[nextIndex] || DEFAULT_INTERFACE_VARIANTS[group],
  };
}

export function getRouteInterfaceGroups(
  pathname: string,
): readonly InterfaceVariantGroup[] {
  if (pathname === "/" || pathname === "/app") {
    return ["HS", "EG", "PB", "BN"];
  }
  if (pathname === "/panels") {
    return ["HS", "PH", "PA", "BN"];
  }
  if (pathname === "/panels/portfolio") {
    return ["HS", "PT", "PC", "BN"];
  }
  if (pathname === "/exchange") {
    return ["HS", "XH", "XC", "BN"];
  }
  if (pathname === "/tasks") return ["HS", "TG", "BN"];
  if (pathname.startsWith("/referrals")) return ["HS", "RG", "RP", "BN"];
  if (pathname === "/ranks") return ["HS", "KG", "BN"];
  if (pathname === "/web-profile") {
    return ["HS", "WG", "PM", "HI", "BN"];
  }
  if (pathname === "/hub") return ["HS", "HU", "BN"];
  if (pathname === "/faq") return ["HS", "FQ", "BN"];
  if (pathname === "/withdraw") return ["HS", "WD", "BN"];
  if (pathname === "/ads") return ["HS", "AD", "BN"];
  if (pathname.startsWith("/admin")) return ["HS", "AM"];
  if (pathname === "/browser-shop") return ["HS", "BS"];
  if (["/404", "/500", "/_error"].includes(pathname)) {
    return ["HS", "ER", "BN"];
  }
  return ["HS", "BN"];
}

// Display renumbering only. Never mutate the authored v727 rank styles.
export const RANK_STYLE_ID_BY_SELECTION: Readonly<Record<string,string>> = Object.freeze({"KG-01":"KG-01","KG-02":"KG-02","KG-03":"KG-04","KG-04":"KG-06","KG-05":"KG-07","KG-06":"KG-08","KG-07":"KG-09","KG-08":"KG-10","KG-09":"KG-11","KG-10":"KG-12"});
export function rankStyleId(selected: string): string {
  return RANK_STYLE_ID_BY_SELECTION[selected] || "KG-01";
}
