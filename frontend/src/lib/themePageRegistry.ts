export type ThemePageDescriptor = {
  marker: string;
  groups: readonly string[];
  kind: "user" | "admin" | "technical";
};

const USER_THEME_PAGES: Readonly<Record<string, ThemePageDescriptor>> = Object.freeze({
  "/": { marker: "THM-00", groups: ["EG"], kind: "user" },
  "/app": { marker: "THM-00A", groups: ["EG"], kind: "user" },
  "/panels": { marker: "THM-01", groups: ["PH", "PA"], kind: "user" },
  "/panels/portfolio": { marker: "THM-01A", groups: ["PT", "PC"], kind: "user" },
  "/exchange": { marker: "THM-02", groups: ["XH", "XC"], kind: "user" },
  "/tasks": { marker: "THM-03", groups: ["TG"], kind: "user" },
  "/referrals": { marker: "THM-04", groups: ["RG"], kind: "user" },
  "/referrals/my": { marker: "THM-04A", groups: ["RG"], kind: "user" },
  "/referrals/active": { marker: "THM-05", groups: ["RG"], kind: "user" },
  "/referrals/inactive": { marker: "THM-06", groups: ["RG"], kind: "user" },
  "/ranks": { marker: "THM-07", groups: ["KG"], kind: "user" },
  "/web-profile": { marker: "THM-08", groups: ["WG", "PM", "HI"], kind: "user" },
  "/hub": { marker: "THM-09", groups: ["HU"], kind: "user" },
  "/faq": { marker: "THM-10", groups: ["FQ"], kind: "user" },
  "/withdraw": { marker: "THM-11", groups: ["WD"], kind: "user" },
  "/ads": { marker: "THM-12", groups: ["AD"], kind: "user" },
  "/browser-shop": { marker: "THM-13", groups: ["BS", "HS"], kind: "user" },
  "/404": { marker: "THM-14", groups: ["ER"], kind: "user" },
  "/500": { marker: "THM-15", groups: ["ER"], kind: "user" },
});

/**
 * FRONTEND_v127 owner rule. Every user-facing route participates in the
 * selected Global Theme. Admin routes are excluded by kind/app mode.
 */
export const GLOBAL_THEME_PAGE_PATHS = Object.freeze([
  "/",
  "/app",
  "/panels",
  "/panels/portfolio",
  "/exchange",
  "/tasks",
  "/referrals",
  "/referrals/my",
  "/referrals/active",
  "/referrals/inactive",
  "/ranks",
  "/hub",
  "/web-profile",
  "/faq",
  "/withdraw",
  "/ads",
  "/browser-shop",
  "/404",
  "/500",
  "/_error",
] as const);

// No user page family is excluded from Global Theme coverage anymore.
// Admin remains outside the user theme contract.
export const INDIVIDUAL_ONLY_PAGE_GROUPS = Object.freeze([] as const);

export function getThemePageDescriptor(pathname: string): ThemePageDescriptor {
  if (pathname.startsWith("/admin")) {
    return { marker: "ADM", groups: ["AM", "HS"], kind: "admin" };
  }
  return USER_THEME_PAGES[pathname]
    || { marker: "THM-UNMAPPED", groups: ["HS"], kind: "user" };
}
