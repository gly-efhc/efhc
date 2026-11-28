import { resolveInterfaceVariantStyle } from "./interfaceVariantRegistry";
export type HeaderThemeComposition = {
  shell: string;
  balance: string;
  statuses: string;
};

const DEFAULT_HEADER_THEME_COMPOSITION: HeaderThemeComposition =
  Object.freeze({ shell: "HS-03", balance: "HB-03", statuses: "SC-03" });

// Header is one indivisible user-facing theme object. HB and SC remain internal
// implementation sources only; there is no user-facing Balance selector.
// Global Header slots 01..13 are sequential Global Theme variants. Historical
// HB/SC sources remain internal implementation details, not user-facing themes.
const HEADER_THEME_COMPOSITION: Readonly<
  Record<string, HeaderThemeComposition>
> = Object.freeze({
  "HS-03": Object.freeze({ shell: "HS-03", balance: "HB-03", statuses: "SC-03" }),
  "HS-06": Object.freeze({ shell: "HS-06", balance: "HB-05", statuses: "SC-02" }),
  "HS-07": Object.freeze({ shell: "HS-07", balance: "HB-12", statuses: "SC-02" }),
  "HS-10": Object.freeze({ shell: "HS-10", balance: "HB-08", statuses: "SC-02" }),
  "HS-11": Object.freeze({ shell: "HS-11", balance: "HB-09", statuses: "SC-04" }),
  // v091: historical semicircular Split Focus moves from HS-14 to canonical Global Theme 12.
  // Theme 13: explicit black/gold Global Header slot; color identity is completed by the root Theme 13 owner layer.
  "HS-13": Object.freeze({ shell: "HS-13", balance: "HB-01", statuses: "SC-02" }),
});

export function resolveHeaderThemeComposition(variant: string): HeaderThemeComposition {
  return HEADER_THEME_COMPOSITION[resolveInterfaceVariantStyle("HS", variant)] || DEFAULT_HEADER_THEME_COMPOSITION;
}
