import React from "react";

import type {
  DashboardFreshness,
  DashboardPanelMode,
} from "../../lib/dashboard/componentContract";

export type DashboardToolbarMode = DashboardPanelMode;

export type DashboardToolbarOption = {
  key: string;
  label: React.ReactNode;
  description?: React.ReactNode;
};

export type DashboardToolbarProps = React.PropsWithChildren<{
  mode: DashboardToolbarMode;
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  breadcrumb?: React.ReactNode;
  timeRange?: React.ReactNode;
  refresh?: React.ReactNode;
  filters?: React.ReactNode;
  freshness?: React.ReactNode;
  updatedAt?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}>;

export type DashboardRangeControlProps = {
  label: React.ReactNode;
  value: string;
  options: DashboardToolbarOption[];
  onChange: (value: string) => void;
  mode?: DashboardToolbarMode;
};

export type DashboardRefreshPickerProps = {
  label: React.ReactNode;
  refreshLabel: React.ReactNode;
  value?: string;
  options?: DashboardToolbarOption[];
  onRefresh: () => void;
  onIntervalChange?: (value: string) => void;
  disabled?: boolean;
  mode?: DashboardToolbarMode;
};

export type DashboardFreshnessBadgeProps = {
  freshness: DashboardFreshness;
  label: React.ReactNode;
  updatedAt?: React.ReactNode;
  mode?: DashboardToolbarMode;
};

function modeClass(mode: DashboardToolbarMode | undefined): string {
  if (mode === "simulation") return "efhc-dashboard-toolbar--simulation";
  return "efhc-dashboard-toolbar--admin";
}

export function DashboardToolbar(props: DashboardToolbarProps) {
  const className = [
    "efhc-dashboard-toolbar",
    modeClass(props.mode),
    props.className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <header
      className={className}
      data-dashboard-toolbar="1465"
      data-dashboard-toolbar-mode={props.mode}
    >
      <div className="efhc-dashboard-toolbar__identity">
        {props.breadcrumb ? (
          <div className="efhc-dashboard-toolbar__breadcrumb">
            {props.breadcrumb}
          </div>
        ) : null}
        <div>
          <strong>{props.title}</strong>
          {props.subtitle ? <p>{props.subtitle}</p> : null}
        </div>
      </div>
      <div className="efhc-dashboard-toolbar__controls">
        {props.timeRange}
        {props.refresh}
        {props.filters}
        {props.freshness}
        {props.updatedAt ? (
          <span className="efhc-dashboard-toolbar__updated">
            {props.updatedAt}
          </span>
        ) : null}
        {props.actions}
      </div>
      {props.children ? (
        <div className="efhc-dashboard-toolbar__extra">
          {props.children}
        </div>
      ) : null}
    </header>
  );
}

export function DashboardTimeRangePicker(
  props: DashboardRangeControlProps,
) {
  return (
    <div
      className="efhc-dashboard-toolbar-picker"
      data-dashboard-time-range-picker="1465"
      data-dashboard-toolbar-mode={props.mode ?? "admin"}
    >
      <span>{props.label}</span>
      <div className="efhc-dashboard-toolbar-picker__options">
        {props.options.map((option) => (
          <button
            aria-pressed={props.value === option.key}
            key={option.key}
            onClick={() => props.onChange(option.key)}
            title={String(option.description ?? option.label)}
            type="button"
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}

export function DashboardRefreshPicker(
  props: DashboardRefreshPickerProps,
) {
  return (
    <div
      className="efhc-dashboard-toolbar-picker"
      data-dashboard-refresh-picker="1465"
      data-dashboard-toolbar-mode={props.mode ?? "admin"}
    >
      <button
        className="efhc-dashboard-toolbar-refresh"
        disabled={props.disabled}
        onClick={props.onRefresh}
        type="button"
      >
        {props.refreshLabel}
      </button>
      {props.options && props.options.length > 0 ? (
        <label>
          <span>{props.label}</span>
          <select
            value={props.value}
            onChange={(event) => {
              props.onIntervalChange?.(event.target.value);
            }}
          >
            {props.options.map((option) => (
              <option key={option.key} value={option.key}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
      ) : null}
    </div>
  );
}

export function DashboardFreshnessBadge(
  props: DashboardFreshnessBadgeProps,
) {
  return (
    <span
      className="efhc-dashboard-freshness-badge"
      data-dashboard-freshness-badge="1465"
      data-freshness={props.freshness}
      data-dashboard-toolbar-mode={props.mode ?? "admin"}
    >
      {props.label}
      {props.updatedAt ? <small>{props.updatedAt}</small> : null}
    </span>
  );
}

