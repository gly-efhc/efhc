export const dashboardPanelStatuses = [
  "loading",
  "empty",
  "error",
  "stale",
  "success",
] as const;

export const dashboardPanelTones = [
  "neutral",
  "info",
  "success",
  "warning",
  "danger",
] as const;

export const dashboardDataKinds = [
  "raw",
  "derived",
  "synthetic_preview",
  "real_timeseries",
] as const;

export const dashboardFreshnessStates = [
  "fresh",
  "stale",
  "unknown",
] as const;

export type DashboardPanelStatus =
  (typeof dashboardPanelStatuses)[number];

export type DashboardPanelTone =
  (typeof dashboardPanelTones)[number];

export type DashboardDataKind =
  (typeof dashboardDataKinds)[number];

export type DashboardFreshness =
  (typeof dashboardFreshnessStates)[number];

export type DashboardPanelMode = "admin" | "simulation";

export type DashboardPanelSize = "compact" | "normal" | "hero";

export type DashboardPanelSource = {
  label: string;
  route?: string;
  dataKind: DashboardDataKind;
  synthetic?: boolean;
};

export type DashboardPanelActionKind =
  | "nav"
  | "mutation-safe"
  | "copy"
  | "external";

export type DashboardPanelAction = {
  label: string;
  /**
   * Navigation link for drill-down routes.
   * If set, render the action as a link.
   */
  href?: string;
  /**
   * Callback for mutation-safe parent actions.
   * Guard, confirm and idempotency stay in the page.
   */
  onClick?: () => void;
  disabled?: boolean;
  danger?: boolean;
  /** Intent marker for review and future renderers. */
  actionKind?: DashboardPanelActionKind;
};

export type DashboardPanelState = {
  status: DashboardPanelStatus;
  message?: string;
  updatedAt?: string;
  freshness?: DashboardFreshness;
};

export type DashboardComponentContract = {
  id: string;
  mode: DashboardPanelMode;
  title: string;
  subtitle?: string;
  description?: string;
  size?: DashboardPanelSize;
  tone?: DashboardPanelTone;
  source: DashboardPanelSource;
  state: DashboardPanelState;
  /**
   * Panel actions rendered by AdminPanelChrome or SimPanelChrome.
   * Nav actions use href only. Mutation-safe actions use onClick only.
   * Guard, confirm and idempotency must remain in the parent page.
   */
  actions?: DashboardPanelAction[];
  ariaLabel?: string;
};

export const dashboardRequiredStates = dashboardPanelStatuses;

