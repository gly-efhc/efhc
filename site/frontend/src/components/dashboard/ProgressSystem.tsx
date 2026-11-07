import React from "react";

import type {
  DashboardDataKind,
  DashboardPanelTone,
} from "../../lib/dashboard/componentContract";

export type DashboardProgressTone = DashboardPanelTone;

export type DashboardProgressKind =
  | "linear"
  | "segmented"
  | "circular"
  | "countdown"
  | "milestone";

export type DashboardProgressSegment = {
  id: string;
  label: React.ReactNode;
  value: number;
  max?: number;
  tone?: DashboardProgressTone;
};

export type DashboardMilestone = {
  id: string;
  label: React.ReactNode;
  complete?: boolean;
  active?: boolean;
};

export type DashboardProgressBaseProps = {
  label?: React.ReactNode;
  value: number;
  max?: number;
  tone?: DashboardProgressTone;
  showValue?: boolean;
  source?: React.ReactNode;
  dataKind?: DashboardDataKind;
  synthetic?: boolean;
  ariaLabel?: string;
};

export type DashboardProgressBarProps = DashboardProgressBaseProps & {
  kind?: "linear";
};

export type DashboardSegmentedProgressProps = {
  label?: React.ReactNode;
  segments: DashboardProgressSegment[];
  source?: React.ReactNode;
  dataKind?: DashboardDataKind;
  synthetic?: boolean;
};

export type DashboardCircularProgressProps = DashboardProgressBaseProps & {
  valueLabel?: React.ReactNode;
};

export type DashboardDurationLabels = {
  days: string;
  hours: string;
  minutes: string;
  seconds: string;
};

export type DashboardCountdownProgressProps = {
  label?: React.ReactNode;
  remainingSeconds: number;
  totalSeconds: number;
  completeLabel?: React.ReactNode;
  elapsedLabel?: React.ReactNode;
  durationLabels?: DashboardDurationLabels;
  tone?: DashboardProgressTone;
  source?: React.ReactNode;
  dataKind?: DashboardDataKind;
  synthetic?: boolean;
};

export type DashboardMilestoneProgressProps = {
  label?: React.ReactNode;
  milestones: DashboardMilestone[];
  source?: React.ReactNode;
  dataKind?: DashboardDataKind;
  synthetic?: boolean;
};

const toneToClass: Record<DashboardProgressTone, string> = {
  neutral: "efhc-dashboard-progress-tone-neutral",
  info: "efhc-dashboard-progress-tone-info",
  success: "efhc-dashboard-progress-tone-success",
  warning: "efhc-dashboard-progress-tone-warning",
  danger: "efhc-dashboard-progress-tone-danger",
};

const SECONDS_PER_DAY = 86400;
const SECONDS_PER_HOUR = 3600;
const SECONDS_PER_MINUTE = 60;

export function normalizeDashboardProgress(value: number, max = 100) {
  if (!Number.isFinite(value) || !Number.isFinite(max) || max <= 0) {
    return { value: 0, max: 100, percent: 0 };
  }
  const safeValue = Math.max(0, Math.min(value, max));
  const percent = Math.min(100, Math.max(0, (safeValue / max) * 100));
  return { value: safeValue, max, percent };
}

const DEFAULT_DURATION_LABELS: DashboardDurationLabels = {
  days: "d",
  hours: "h",
  minutes: "m",
  seconds: "s",
};

export function formatDashboardDuration(
  totalSeconds: number,
  labels: DashboardDurationLabels = DEFAULT_DURATION_LABELS,
): string {
  const safeSeconds = Math.max(0, Math.floor(totalSeconds));
  const days = Math.floor(safeSeconds / SECONDS_PER_DAY);
  const hours = Math.floor(
    (safeSeconds % SECONDS_PER_DAY) / SECONDS_PER_HOUR,
  );
  const minutes = Math.floor(
    (safeSeconds % SECONDS_PER_HOUR) / SECONDS_PER_MINUTE,
  );
  const seconds = safeSeconds % SECONDS_PER_MINUTE;
  return [
    `${days}${labels.days}`,
    `${hours}${labels.hours}`,
    `${minutes}${labels.minutes}`,
    `${seconds}${labels.seconds}`,
  ].join(" ");
}

function progressLabelToString(label: React.ReactNode, fallback: string): string {
  if (typeof label === "string") return label;
  if (typeof label === "number") return String(label);
  if (Array.isArray(label)) {
    return label
      .map((item) => progressLabelToString(item, ""))
      .filter(Boolean)
      .join(" ") || fallback;
  }
  return fallback;
}

function metaAttrs(
  kind: DashboardProgressKind,
  dataKind?: DashboardDataKind,
  synthetic?: boolean,
) {
  return {
    "data-dashboard-progress-system": "1463",
    "data-progress-kind": kind,
    "data-progress-data-kind": dataKind ?? "derived",
    "data-progress-synthetic": synthetic ? "true" : "false",
  };
}

export function DashboardProgressBar(props: DashboardProgressBarProps) {
  const tone = props.tone ?? "info";
  const normalized = normalizeDashboardProgress(props.value, props.max);
  return (
    <div
      aria-label={props.ariaLabel ?? progressLabelToString(props.label, "Dashboard progress")}
      aria-valuemax={100}
      aria-valuemin={0}
      aria-valuenow={Math.round(normalized.percent)}
      className={`efhc-dashboard-progress ${toneToClass[tone]}`}
      data-dashboard-accessibility-overflow-qa="1494"
      role="progressbar"
      {...metaAttrs("linear", props.dataKind, props.synthetic)}
    >
      {props.label || props.showValue ? (
        <div className="efhc-dashboard-progress__label">
          {props.label ? <span>{props.label}</span> : <span />}
          {props.showValue ? <b>{Math.round(normalized.percent)}%</b> : null}
        </div>
      ) : null}
      <div className="efhc-dashboard-progress__track">
        <span style={{ width: `${normalized.percent}%` }} />
      </div>
    </div>
  );
}

export function DashboardSegmentedProgress(
  props: DashboardSegmentedProgressProps,
) {
  return (
    <div
      className="efhc-dashboard-progress-segmented"
      {...metaAttrs("segmented", props.dataKind, props.synthetic)}
    >
      {props.label ? <div>{props.label}</div> : null}
      <div className="efhc-dashboard-progress-segmented__grid">
        {props.segments.map((segment) => {
          const tone = segment.tone ?? "info";
          return (
            <div
              className={`efhc-dashboard-progress-segment ${toneToClass[tone]}`}
              key={segment.id}
            >
              <span>{segment.label}</span>
              <DashboardProgressBar
                dataKind={props.dataKind}
                max={segment.max ?? 100}
                showValue
                synthetic={props.synthetic}
                tone={tone}
                value={segment.value}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function DashboardCircularProgress(
  props: DashboardCircularProgressProps,
) {
  const tone = props.tone ?? "info";
  const normalized = normalizeDashboardProgress(props.value, props.max);
  const style = {
    "--efhc-progress-value": `${normalized.percent}%`,
  } as React.CSSProperties;
  return (
    <div
      className={`efhc-dashboard-progress-circular ${toneToClass[tone]}`}
      style={style}
      {...metaAttrs("circular", props.dataKind, props.synthetic)}
      aria-label={props.ariaLabel}
    >
      <div className="efhc-dashboard-progress-circular__ring">
        <strong>
          {props.valueLabel ?? `${Math.round(normalized.percent)}%`}
        </strong>
      </div>
      {props.label ? <span>{props.label}</span> : null}
    </div>
  );
}

export function DashboardCountdownProgress(
  props: DashboardCountdownProgressProps,
) {
  const tone = props.tone ?? "success";
  const remaining = Math.max(0, props.remainingSeconds);
  const elapsed = Math.max(0, props.totalSeconds - remaining);
  const normalized = normalizeDashboardProgress(elapsed, props.totalSeconds);
  const complete = remaining <= 0;
  return (
    <div
      className={`efhc-dashboard-progress-countdown ${toneToClass[tone]}`}
      {...metaAttrs("countdown", props.dataKind, props.synthetic)}
    >
      <DashboardProgressBar
        dataKind={props.dataKind}
        label={props.label}
        max={props.totalSeconds}
        showValue
        synthetic={props.synthetic}
        tone={tone}
        value={elapsed}
      />
      <strong>
        {complete
          ? props.completeLabel ?? "100%"
          : formatDashboardDuration(remaining, props.durationLabels)}
      </strong>
      <small>
        {props.elapsedLabel
          ? `${Math.round(normalized.percent)}% ${props.elapsedLabel}`
          : `${Math.round(normalized.percent)}%`}
      </small>
    </div>
  );
}

export function DashboardMilestoneProgress(
  props: DashboardMilestoneProgressProps,
) {
  const completeCount = props.milestones.filter((item) => item.complete).length;
  return (
    <div
      className="efhc-dashboard-progress-milestone"
      {...metaAttrs("milestone", props.dataKind, props.synthetic)}
    >
      {props.label ? <div>{props.label}</div> : null}
      <DashboardProgressBar
        dataKind={props.dataKind}
        max={props.milestones.length || 1}
        showValue
        synthetic={props.synthetic}
        tone="success"
        value={completeCount}
      />
      <ol className="efhc-dashboard-progress-milestone__list">
        {props.milestones.map((milestone) => (
          <li
            data-active={milestone.active ? "true" : "false"}
            data-complete={milestone.complete ? "true" : "false"}
            key={milestone.id}
          >
            {milestone.label}
          </li>
        ))}
      </ol>
    </div>
  );
}

