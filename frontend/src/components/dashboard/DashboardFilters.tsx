import React from "react";

import type { DashboardPanelMode } from "../../lib/dashboard/componentContract";

export type DashboardFilterMode = DashboardPanelMode;

export const dashboardAdminFilterKinds = [
  "status",
  "route",
  "operation_type",
  "user_segment",
  "date_range",
  "source",
  "severity",
] as const;

export const dashboardSimulationFilterKinds = [
  "panel_state",
  "period",
  "leaderboard_scope",
  "task_status",
  "referral_scope",
  "exchange_scope",
] as const;

export type DashboardAdminFilterKind =
  (typeof dashboardAdminFilterKinds)[number];

export type DashboardSimulationFilterKind =
  (typeof dashboardSimulationFilterKinds)[number];

export type DashboardFilterKind =
  | DashboardAdminFilterKind
  | DashboardSimulationFilterKind
  | "generic";

export type DashboardFilterQuerySync = "disabled" | "safe_display_only";

export type DashboardFilterOption = {
  key: string;
  label: React.ReactNode;
  description?: React.ReactNode;
  disabled?: boolean;
};

export type DashboardFilterGroupDefinition = {
  key?: string;
  label: React.ReactNode;
  value: string;
  options: DashboardFilterOption[];
  onChange: (value: string) => void;
  kind?: DashboardFilterKind;
  queryKey?: string;
  querySync?: DashboardFilterQuerySync;
};

export type DashboardFilterBarProps = React.PropsWithChildren<{
  mode: DashboardFilterMode;
  groups: DashboardFilterGroupDefinition[];
  resetLabel?: React.ReactNode;
  onReset?: () => void;
  className?: string;
}>;

export type DashboardVariableBarProps = DashboardFilterBarProps;

export type DashboardFilterChipProps = {
  mode?: DashboardFilterMode;
  label: React.ReactNode;
  selected?: boolean;
  disabled?: boolean;
  description?: React.ReactNode;
  onClick?: () => void;
};

export const dashboardFilterForbiddenQueryFragments = [
  "secret",
  "token",
  "payload",
  "initdata",
  "password",
  "private",
  "seed",
  "mnemonic",
  "tg_id",
] as const;

export function isSafeDashboardFilterQueryKey(queryKey: string): boolean {
  const normalized = queryKey.replace(/[^a-zA-Z0-9_]/g, "").toLowerCase();
  if (!normalized) return false;
  return !dashboardFilterForbiddenQueryFragments.some((fragment) =>
    normalized.includes(fragment),
  );
}

function modeClass(mode: DashboardFilterMode | undefined): string {
  if (mode === "simulation") return "efhc-dashboard-filters--simulation";
  return "efhc-dashboard-filters--admin";
}

function labelToString(label: React.ReactNode, fallback: string): string {
  if (typeof label === "string") return label;
  if (typeof label === "number") return String(label);
  return fallback;
}

export function DashboardFilterChip(props: DashboardFilterChipProps) {
  const className = [
    "efhc-dashboard-filter-chip",
    modeClass(props.mode),
  ]
    .filter(Boolean)
    .join(" ");

  if (!props.onClick) {
    return (
      <span
        className={className}
        data-dashboard-filter-chip="1466"
        data-dashboard-filter-selected={props.selected ? "true" : "false"}
        title={labelToString(props.description, "dashboard filter")}
      >
        {props.label}
      </span>
    );
  }

  return (
    <button
      aria-pressed={props.selected}
      className={className}
      data-dashboard-filter-chip="1466"
      data-dashboard-filter-selected={props.selected ? "true" : "false"}
      disabled={props.disabled}
      onClick={props.onClick}
      title={labelToString(props.description, "dashboard filter")}
      type="button"
    >
      {props.label}
    </button>
  );
}

export function DashboardFilterResetButton(props: {
  label: React.ReactNode;
  mode?: DashboardFilterMode;
  onReset: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      className={`efhc-dashboard-filter-reset ${modeClass(props.mode)}`}
      data-dashboard-filter-reset="1466"
      disabled={props.disabled}
      onClick={props.onReset}
      type="button"
    >
      {props.label}
    </button>
  );
}

export function DashboardFilterGroup(props: {
  group: DashboardFilterGroupDefinition;
  mode?: DashboardFilterMode;
}) {
  const group = props.group;
  const safeQuery = group.queryKey
    ? isSafeDashboardFilterQueryKey(group.queryKey)
    : true;
  const groupKey = group.key ?? labelToString(group.label, "filter-group");
  const querySync = group.querySync ?? "disabled";

  return (
    <div
      aria-label={labelToString(group.label, groupKey)}
      className="efhc-dashboard-filter-group"
      data-dashboard-filter-group="1466"
      data-dashboard-filter-kind={group.kind ?? "generic"}
      data-filter-query-safe={safeQuery ? "true" : "false"}
      data-filter-query-sync={querySync}
      role="group"
    >
      <span className="efhc-dashboard-filter-group__label">
        {group.label}
      </span>
      <div className="efhc-dashboard-filter-group__options">
        {group.options.map((option) => (
          <DashboardFilterChip
            description={option.description}
            disabled={option.disabled || !safeQuery}
            key={option.key}
            label={option.label}
            mode={props.mode}
            onClick={() => group.onChange(option.key)}
            selected={group.value === option.key}
          />
        ))}
      </div>
    </div>
  );
}

export function DashboardFilterBar(props: DashboardFilterBarProps) {
  const className = [
    "efhc-dashboard-filter-bar",
    modeClass(props.mode),
    props.className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div
      className={className}
      data-dashboard-filter-bar="1466"
      data-dashboard-filter-mode={props.mode}
      data-dashboard-filter-readonly="true"
    >
      {props.groups.map((group, index) => (
        <DashboardFilterGroup
          group={group}
          key={group.key ?? `${labelToString(group.label, "group")}-${index}`}
          mode={props.mode}
        />
      ))}
      {props.children}
      {props.onReset ? (
        <DashboardFilterResetButton
          label={props.resetLabel ?? "Reset"}
          mode={props.mode}
          onReset={props.onReset}
        />
      ) : null}
    </div>
  );
}

export function DashboardVariableBar(props: DashboardVariableBarProps) {
  return (
    <DashboardFilterBar
      {...props}
      className={[
        "efhc-dashboard-variable-bar",
        props.className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {props.children}
    </DashboardFilterBar>
  );
}

