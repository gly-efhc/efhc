import React from "react";

import type {
  DashboardDataKind,
  DashboardPanelTone,
} from "../../lib/dashboard/componentContract";

export type DashboardMiniChartTone = DashboardPanelTone;

export type DashboardMiniChartKind =
  | "sparkline"
  | "area"
  | "bar"
  | "activity";

export type DashboardMiniChartPoint = {
  id: string;
  label: React.ReactNode;
  value: number;
  tone?: DashboardMiniChartTone;
};

export type DashboardMiniChartBaseProps = {
  points: DashboardMiniChartPoint[];
  label?: React.ReactNode;
  unit?: React.ReactNode;
  source?: React.ReactNode;
  dataKind?: DashboardDataKind;
  synthetic?: boolean;
  tone?: DashboardMiniChartTone;
  emptyLabel?: React.ReactNode;
  ariaLabel?: string;
};

export type DashboardMiniChartSvgProps = DashboardMiniChartBaseProps & {
  width?: number;
  height?: number;
};

const DEFAULT_WIDTH = 120;
const DEFAULT_HEIGHT = 38;

const toneToClass: Record<DashboardMiniChartTone, string> = {
  neutral: "efhc-mini-chart-tone-neutral",
  info: "efhc-mini-chart-tone-info",
  success: "efhc-mini-chart-tone-success",
  warning: "efhc-mini-chart-tone-warning",
  danger: "efhc-mini-chart-tone-danger",
};

function finiteValue(value: number): number {
  return Number.isFinite(value) ? value : 0;
}

export function normalizeMiniChartPoints(
  points: DashboardMiniChartPoint[],
): DashboardMiniChartPoint[] {
  return points.map((point) => ({
    ...point,
    value: finiteValue(point.value),
  }));
}

function chartMetaAttrs(
  kind: DashboardMiniChartKind,
  dataKind?: DashboardDataKind,
  synthetic?: boolean,
) {
  return {
    "data-dashboard-mini-chart": "1464",
    "data-mini-chart-kind": kind,
    "data-mini-chart-data-kind": dataKind ?? "derived",
    "data-mini-chart-synthetic": synthetic ? "true" : "false",
  };
}

function pointScale(
  points: DashboardMiniChartPoint[],
  height: number,
) {
  const values = points.map((point) => point.value);
  const min = Math.min(...values, 0);
  const max = Math.max(...values, 1);
  const range = max - min || 1;
  return (value: number) =>
    height - ((value - min) / range) * (height - 4) - 2;
}

export function buildMiniChartPolyline(
  points: DashboardMiniChartPoint[],
  width = DEFAULT_WIDTH,
  height = DEFAULT_HEIGHT,
): string {
  if (points.length === 0) return "";
  if (points.length === 1) {
    const y = pointScale(points, height)(points[0].value);
    return `0,${y.toFixed(2)} ${width},${y.toFixed(2)}`;
  }
  const yFor = pointScale(points, height);
  const step = width / Math.max(points.length - 1, 1);
  return points
    .map((point, index) => {
      const x = index * step;
      const y = yFor(point.value);
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
}

function emptyChart(label: React.ReactNode) {
  return (
    <div className="efhc-mini-chart-empty" data-mini-chart-empty="true">
      {label}
    </div>
  );
}

function miniChartShell(
  props: React.PropsWithChildren<
    DashboardMiniChartBaseProps & { kind: DashboardMiniChartKind }
  >,
) {
  const tone = props.tone ?? "info";
  const className = [
    "efhc-mini-chart",
    toneToClass[tone],
    `efhc-mini-chart--${props.kind}`,
  ].join(" ");
  return (
    <div
      className={className}
      {...chartMetaAttrs(props.kind, props.dataKind, props.synthetic)}
      aria-label={props.ariaLabel}
    >
      {props.label || props.unit ? (
        <div className="efhc-mini-chart__header">
          {props.label ? <span>{props.label}</span> : <span />}
          {props.unit ? <small>{props.unit}</small> : null}
        </div>
      ) : null}
      {props.children}
      {props.synthetic && props.emptyLabel ? (
        <small className="efhc-mini-chart__synthetic">
          {props.emptyLabel}
        </small>
      ) : null}
    </div>
  );
}

export function DashboardMiniSparkline(
  props: DashboardMiniChartSvgProps,
) {
  const points = normalizeMiniChartPoints(props.points);
  const width = props.width ?? DEFAULT_WIDTH;
  const height = props.height ?? DEFAULT_HEIGHT;
  if (points.length === 0) {
    return miniChartShell({
      ...props,
      kind: "sparkline",
      children: emptyChart(props.emptyLabel ?? "—"),
    });
  }
  const polyline = buildMiniChartPolyline(points, width, height);
  return miniChartShell({
    ...props,
    kind: "sparkline",
    children: (
      <svg
        className="efhc-mini-chart__svg"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-hidden={props.ariaLabel ? undefined : true}
      >
        <polyline points={polyline} />
      </svg>
    ),
  });
}

export function DashboardMiniAreaChart(
  props: DashboardMiniChartSvgProps,
) {
  const points = normalizeMiniChartPoints(props.points);
  const width = props.width ?? DEFAULT_WIDTH;
  const height = props.height ?? DEFAULT_HEIGHT;
  if (points.length === 0) {
    return miniChartShell({
      ...props,
      kind: "area",
      children: emptyChart(props.emptyLabel ?? "—"),
    });
  }
  const polyline = buildMiniChartPolyline(points, width, height);
  const areaPath = `M ${polyline} L ${width},${height} L 0,${height} Z`;
  return miniChartShell({
    ...props,
    kind: "area",
    children: (
      <svg
        className="efhc-mini-chart__svg"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-hidden={props.ariaLabel ? undefined : true}
      >
        <path className="efhc-mini-chart__area" d={areaPath} />
        <polyline points={polyline} />
      </svg>
    ),
  });
}

export function DashboardMiniBarChart(
  props: DashboardMiniChartSvgProps,
) {
  const points = normalizeMiniChartPoints(props.points);
  if (points.length === 0) {
    return miniChartShell({
      ...props,
      kind: "bar",
      children: emptyChart(props.emptyLabel ?? "—"),
    });
  }
  const max = Math.max(...points.map((point) => point.value), 1);
  return miniChartShell({
    ...props,
    kind: "bar",
    children: (
      <div className="efhc-mini-chart-bars">
        {points.map((point) => {
          const percent = Math.max(2, (point.value / max) * 100);
          return (
            <span
              key={point.id}
              title={`${point.label}: ${point.value}`}
              style={{ height: `${percent}%` }}
            />
          );
        })}
      </div>
    ),
  });
}

export function DashboardActivityStrip(
  props: DashboardMiniChartBaseProps,
) {
  const points = normalizeMiniChartPoints(props.points);
  if (points.length === 0) {
    return miniChartShell({
      ...props,
      kind: "activity",
      children: emptyChart(props.emptyLabel ?? "—"),
    });
  }
  const max = Math.max(...points.map((point) => point.value), 1);
  return miniChartShell({
    ...props,
    kind: "activity",
    children: (
      <div className="efhc-mini-chart-activity">
        {points.map((point) => {
          const intensity = Math.max(0, Math.min(point.value / max, 1));
          return (
            <span
              data-intensity={intensity.toFixed(2)}
              key={point.id}
              title={`${point.label}: ${point.value}`}
              style={{ opacity: 0.25 + intensity * 0.75 }}
            />
          );
        })}
      </div>
    ),
  });
}

