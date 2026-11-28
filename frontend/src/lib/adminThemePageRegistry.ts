export const ADMIN_THEME_PAGE_MARKERS = Object.freeze({
  "/admin": "ADM-00",
  "/admin/users": "ADM-01",
  "/admin/user-history": "ADM-01",
  "/admin/bank": "ADM-02",
  "/admin/withdrawals": "ADM-03",
  "/admin/bonuses": "ADM-04",
  "/admin/shop": "ADM-05",
  "/admin/tasks": "ADM-06",
  "/admin/reports": "ADM-07",
  "/admin/referrals": "ADM-08",
  "/admin/panels": "ADM-09",
  "/admin/hub": "ADM-10",
  "/admin/efhc-deposits": "ADM-12",
  "/admin/ads": "ADM-13",
  "/admin/sale-packages": "ADM-14",
  "/admin/diagnostics": "ADM-15",
  "/admin/system": "ADM-15",
  "/admin/vip-nft": "ADM-11",
  "/admin/api-workbench": "ADM-16",
  "/admin/logs": "ADM-07",
  "/admin/emergency": "ADM-19",
} as const);

export type AdminThemePageRoute = keyof typeof ADMIN_THEME_PAGE_MARKERS;
export type AdminThemePageMarker = (typeof ADMIN_THEME_PAGE_MARKERS)[AdminThemePageRoute];

export function getAdminThemePageMarker(pathname: string): AdminThemePageMarker {
  return (
    ADMIN_THEME_PAGE_MARKERS[pathname as AdminThemePageRoute]
    || ADMIN_THEME_PAGE_MARKERS["/admin"]
  );
}
