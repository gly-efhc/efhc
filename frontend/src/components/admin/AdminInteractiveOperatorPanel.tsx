import React, { useEffect, useMemo, useState } from "react";

import {
  AdminActionTable,
  AdminChartCard,
  AdminFilterBar,
  AdminFlowMapCard,
  AdminKpiCard,
  AdminSectionHeader,
  AdminStatusBadge,
  type AdminUiTone,
} from "./AdminDashboardUiKit";

type OperatorMetric = {
  key: string;
  label: string;
  value: React.ReactNode;
  numericValue: number;
  hint?: React.ReactNode;
  tone?: AdminUiTone;
};

type OperatorFlowNode = {
  key: string;
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
  metricKey?: string;
};

type OperatorActionRow = {
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
};

type WindowKey = "7" | "14" | "30";

type OperatorPoint = {
  step: number;
  label: string;
  value: number;
};

function safeMetric(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, value);
}

function human(value: number): string {
  return value.toLocaleString("ru-RU", {
    maximumFractionDigits: 2,
  });
}

function buildOperatorSeries(
  value: number,
  days: number,
  pulse: number,
): OperatorPoint[] {
  const base = Math.max(safeMetric(value), 1);
  const liveFactor = 1 + ((pulse % 8) * 0.006);
  return Array.from({ length: days }, (_, index) => {
    const step = index + 1;
    const progress = step / days;
    const wave = 1 + Math.sin(step / 2.4) * 0.045;
    return {
      step,
      label: `Шаг ${step}`,
      value: base * Math.max(0.04, progress * wave * liveFactor),
    };
  });
}

function clampPercent(value: number, max: number): number {
  if (!Number.isFinite(value) || max <= 0) return 0;
  return Math.max(6, Math.min(94, Math.round((value / max) * 88)));
}

function pathFor(points: OperatorPoint[]): string {
  if (!points.length) return "";
  const max = Math.max(...points.map((point) => point.value), 1);
  return points.map((point, index) => {
    const x = points.length === 1
      ? 20
      : (index / (points.length - 1)) * 100;
    const y = 94 - clampPercent(point.value, max);
    return `${index === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
  }).join(" ");
}

export function AdminInteractiveOperatorPanel(props: {
  scope: "bank" | "users";
  title: React.ReactNode;
  subtitle: React.ReactNode;
  metrics: OperatorMetric[];
  flowNodes: OperatorFlowNode[];
  rows: OperatorActionRow[];
  defaultMetricKey?: string;
}) {
  const [metricKey, setMetricKey] = useState(
    props.defaultMetricKey || props.metrics[0]?.key || "overview",
  );
  const [windowKey, setWindowKey] = useState<WindowKey>("14");
  const [zoom, setZoom] = useState(100);
  const [live, setLive] = useState(true);
  const [pulse, setPulse] = useState(0);
  const [selectedStep, setSelectedStep] = useState<number | null>(null);

  useEffect(() => {
    if (!live) return undefined;
    const id = window.setInterval(() => {
      setPulse((value) => value + 1);
    }, 3000);
    return () => window.clearInterval(id);
  }, [live]);

  const metric = props.metrics.find((item) => item.key === metricKey)
    || props.metrics[0];
  const days = windowKey === "30" ? 30 : windowKey === "7" ? 7 : 14;
  const series = useMemo(
    () => buildOperatorSeries(metric?.numericValue || 0, days, pulse),
    [days, metric?.numericValue, pulse],
  );
  const visibleCount = Math.max(3, Math.ceil(series.length * zoom / 100));
  const visible = series.slice(-visibleCount);
  const selected = visible.find((point) => point.step === selectedStep)
    || visible[visible.length - 1]
    || null;
  const chartPath = pathFor(visible);
  const max = Math.max(...visible.map((point) => point.value), 1);

  return (
    <section
      className="efhc-admin-operator-panel"
      data-admin-operator-panel-scope={props.scope}
    >
      <AdminSectionHeader
        eyebrow="Sandbox interactive operator pattern"
        title={props.title}
        subtitle={props.subtitle}
        actions={(
          <button
            type="button"
            className="efhc-admin-live-dashboard_live"
            aria-pressed={live}
            onClick={() => setLive((value) => !value)}
          >
            {live ? "Live включён" : "Live пауза"}
          </button>
        )}
      />

      <AdminFilterBar
        groups={[
          {
            label: "Метрика",
            value: metricKey,
            options: props.metrics.map((item) => ({
              key: item.key,
              label: item.label,
            })),
            onChange: setMetricKey,
          },
          {
            label: "Окно",
            value: windowKey,
            options: (["7", "14", "30"] as WindowKey[]).map((item) => ({
              key: item,
              label: `${item} шагов`,
            })),
            onChange: (value) => setWindowKey(value as WindowKey),
          },
        ]}
      />

      <div className="efhc-admin-live-controls">
        <label className="efhc-admin-live-zoom">
          <span>Масштаб</span>
          <input
            min="35"
            max="100"
            step="5"
            type="range"
            value={zoom}
            onChange={(event) => setZoom(parseInt(event.target.value, 10))}
          />
          <strong>{zoom}%</strong>
        </label>
      </div>

      <div className="efhc-admin-operator-panel_grid">
        <AdminChartCard
          title={metric?.label || "Метрика"}
          subtitle={selected ? selected.label : "нет данных"}
          meta={<AdminStatusBadge label="SVG interactive" tone="primary" />}
        >
          <svg
            viewBox="0 0 100 100"
            preserveAspectRatio="none"
            role="img"
            aria-label="Интерактивный график операторского раздела"
          >
            <path
              className="efhc-admin-live-chart_area"
              d={`${chartPath} L100,100 L0,100 Z`}
            />
            <path className="efhc-admin-live-chart_line" d={chartPath} />
            {visible.map((point, index) => {
              const x = visible.length === 1
                ? 20
                : (index / (visible.length - 1)) * 100;
              const y = 94 - clampPercent(point.value, max);
              return (
                <circle
                  key={point.step}
                  className="efhc-admin-live-chart_point"
                  cx={x}
                  cy={y}
                  r={selected?.step === point.step ? 3.2 : 2.1}
                  role="button"
                  tabIndex={0}
                  onClick={() => setSelectedStep(point.step)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      setSelectedStep(point.step);
                    }
                  }}
                />
              );
            })}
          </svg>
        </AdminChartCard>

        <div className="efhc-admin-operator-panel_metrics">
          {props.metrics.slice(0, 4).map((item) => (
            <AdminKpiCard
              key={item.key}
              label={item.label}
              value={item.value}
              meta={item.key === metricKey ? "выбрано" : "операторский срез"}
              hint={item.hint}
              tone={item.tone}
            />
          ))}
        </div>
      </div>

      <AdminFlowMapCard
        title="Операторская карта раздела"
        nodes={props.flowNodes.map((node) => ({
          label: node.label,
          value: node.value,
          hint: node.hint,
          active: node.metricKey === metricKey,
          onClick: node.metricKey ? () => setMetricKey(node.metricKey || metricKey) : undefined,
        }))}
      />

      <AdminActionTable
        title="Контроль выбранного состояния"
        rows={[
          { label: "Активная метрика", value: metric?.label || "—" },
          { label: "Выбранный шаг", value: selected?.label || "—" },
          { label: "Значение на шаге", value: human(selected?.value || 0) },
          ...props.rows,
        ]}
      />
    </section>
  );
}
