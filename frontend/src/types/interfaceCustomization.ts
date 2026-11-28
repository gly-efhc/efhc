export const INTERFACE_VARIANT_GROUPS = [
  "SC",
  "HB",
  "HS",
  "EG",
  "BN",
  "EI",
  "PB",
  "RP",
  "PH",
  "PT",
  "PC",
  "PA",
  "XH",
  "XS",
  "XC",
  "XA",
  "TG",
  "RG",
  "KG",
  "WG",
  "HU",
  "FQ",
  "PM",
  "HI",
  "WD",
  "AD",
  "BS",
  "ER",
  "AM",
] as const;

export type InterfaceVariantGroup =
  (typeof INTERFACE_VARIANT_GROUPS)[number];

export type InterfaceVariantSettings = Record<
  InterfaceVariantGroup,
  string
>;

export type InterfaceCustomizationMode = "idle" | "editing";
export type InterfaceAppMode = "user" | "admin";
export type VariantDotsPlacement = "above" | "below";
