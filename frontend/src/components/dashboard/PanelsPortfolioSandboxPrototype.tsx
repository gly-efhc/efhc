import Link from "next/link";
import React, { useMemo, useState } from "react";

import type { DashboardMiniChartPoint } from "./MiniCharts";
import {
  SimActivityStrip,
  SimCountdownProgress,
  SimDashboardGrid,
  SimDashboardSection,
  SimDashboardShell,
  SimDashboardToolbar,
  SimFreshnessBadge,
  SimMiniAreaChart,
  SimMiniBarChart,
  SimMiniSparkline,
  SimPanelChrome,
  SimPanelStateFilter,
  SimPeriodFilter,
  SimProgressBar,
  SimSegmentedProgress,
  SimStatCard,
  SimStatusPill,
} from "./SimulationDashboardUiKit";

type PanelsPortfolioPeriod = "30d" | "180d";
type PanelsPortfolioState = "all" | "active" | "archive";

type PanelsPortfolioPreviewPanel = {
  id: string;
  title: string;
  status: "active" | "archive";
  generatedKwh: number;
  remainingSeconds: number;
  lifetimeProgress: number;
  activatedAt: string;
  expiresAt: string;
  result: string;
  trend: DashboardMiniChartPoint[];
};

type PanelsPortfolioPreview = {
  totalPanels: string;
  activePanels: string;
  archivedPanels: string;
  nearestExpiry: string;
  totalGenerated: number;
  lifetimeProgress: number;
  portfolioTrend: DashboardMiniChartPoint[];
  distribution: DashboardMiniChartPoint[];
  activity: DashboardMiniChartPoint[];
  panels: PanelsPortfolioPreviewPanel[];
};

type PanelsPortfolioSandboxPrototypeProps = {
  initialPeriod?: PanelsPortfolioPeriod;
  initialState?: PanelsPortfolioState;
};

const PANEL_LIFETIME_SECONDS = 180 * 86400;

const periodOptions = [
  {
    key: "30d",
    label: "30д",
    description: "Preview динамики портфеля за месяц",
  },
  {
    key: "180d",
    label: "180д",
    description: "Preview жизненного цикла панели",
  },
];

const stateOptions = [
  {
    key: "all",
    label: "Все",
    description: "Active + Archive preview",
  },
  {
    key: "active",
    label: "Активные",
    description: "Панели, которые ещё генерируют kWh",
  },
  {
    key: "archive",
    label: "Архив",
    description: "Завершённые панели без write-actions",
  },
];

const panelsPreviewByPeriod: Record<
  PanelsPortfolioPeriod,
  PanelsPortfolioPreview
> = {
  "30d": {
    totalPanels: "9",
    activePanels: "6",
    archivedPanels: "3",
    nearestExpiry: "27д 04ч",
    totalGenerated: 1842.45,
    lifetimeProgress: 64,
    portfolioTrend: [
      { id: "d1", label: "День 1", value: 520 },
      { id: "d7", label: "День 7", value: 790 },
      { id: "d14", label: "День 14", value: 1120 },
      { id: "d21", label: "День 21", value: 1490 },
      { id: "d30", label: "День 30", value: 1842 },
    ],
    distribution: [
      { id: "active", label: "Активные", value: 6, tone: "success" },
      { id: "archive", label: "Архив", value: 3, tone: "info" },
      { id: "soon", label: "Скоро истекают", value: 2, tone: "warning" },
    ],
    activity: [
      { id: "portfolio", label: "Портфель", value: 1, tone: "success" },
      { id: "countdown", label: "Countdown", value: 1, tone: "info" },
      { id: "archive", label: "Архив", value: 1, tone: "neutral" },
      { id: "expiry", label: "Expiry", value: 1, tone: "warning" },
      { id: "truth", label: "Truth", value: 1, tone: "success" },
    ],
    panels: [
      {
        id: "PANEL-A1",
        title: "Solar Panel A1",
        status: "active",
        generatedKwh: 384.25,
        remainingSeconds: 27 * 86400 + 4 * 3600,
        lifetimeProgress: 85,
        activatedAt: "10.12.2025 UTC",
        expiresAt: "06.07.2026 UTC",
        result: "Генерирует",
        trend: [
          { id: "a1", label: "1", value: 120 },
          { id: "a2", label: "2", value: 180 },
          { id: "a3", label: "3", value: 240 },
          { id: "a4", label: "4", value: 384 },
        ],
      },
      {
        id: "PANEL-B7",
        title: "Solar Panel B7",
        status: "active",
        generatedKwh: 291.7,
        remainingSeconds: 88 * 86400 + 11 * 3600,
        lifetimeProgress: 51,
        activatedAt: "21.03.2026 UTC",
        expiresAt: "17.09.2026 UTC",
        result: "Средний цикл",
        trend: [
          { id: "b1", label: "1", value: 70 },
          { id: "b2", label: "2", value: 140 },
          { id: "b3", label: "3", value: 210 },
          { id: "b4", label: "4", value: 291 },
        ],
      },
      {
        id: "PANEL-C4",
        title: "Solar Panel C4",
        status: "archive",
        generatedKwh: 420.5,
        remainingSeconds: 0,
        lifetimeProgress: 100,
        activatedAt: "02.07.2025 UTC",
        expiresAt: "29.12.2025 UTC",
        result: "Завершена",
        trend: [
          { id: "c1", label: "1", value: 110 },
          { id: "c2", label: "2", value: 250 },
          { id: "c3", label: "3", value: 360 },
          { id: "c4", label: "4", value: 420 },
        ],
      },
    ],
  },
  "180d": {
    totalPanels: "12",
    activePanels: "8",
    archivedPanels: "4",
    nearestExpiry: "13д 18ч",
    totalGenerated: 4926.8,
    lifetimeProgress: 72,
    portfolioTrend: [
      { id: "m1", label: "0д", value: 0 },
      { id: "m2", label: "45д", value: 980 },
      { id: "m3", label: "90д", value: 2250 },
      { id: "m4", label: "135д", value: 3600 },
      { id: "m5", label: "180д", value: 4926 },
    ],
    distribution: [
      { id: "active", label: "Активные", value: 8, tone: "success" },
      { id: "archive", label: "Архив", value: 4, tone: "info" },
      { id: "soon", label: "Скоро истекают", value: 3, tone: "warning" },
    ],
    activity: [
      { id: "portfolio", label: "Портфель", value: 1, tone: "success" },
      { id: "countdown", label: "Countdown", value: 1, tone: "info" },
      { id: "archive", label: "Архив", value: 1, tone: "neutral" },
      { id: "expiry", label: "Expiry", value: 1, tone: "warning" },
      { id: "truth", label: "Truth", value: 1, tone: "success" },
    ],
    panels: [
      {
        id: "PANEL-L9",
        title: "Solar Panel L9",
        status: "active",
        generatedKwh: 812,
        remainingSeconds: 13 * 86400 + 18 * 3600,
        lifetimeProgress: 92,
        activatedAt: "22.12.2025 UTC",
        expiresAt: "20.06.2026 UTC",
        result: "Скоро в архив",
        trend: [
          { id: "l1", label: "1", value: 180 },
          { id: "l2", label: "2", value: 360 },
          { id: "l3", label: "3", value: 600 },
          { id: "l4", label: "4", value: 812 },
        ],
      },
      {
        id: "PANEL-M3",
        title: "Solar Panel M3",
        status: "active",
        generatedKwh: 633.3,
        remainingSeconds: 74 * 86400 + 6 * 3600,
        lifetimeProgress: 59,
        activatedAt: "24.02.2026 UTC",
        expiresAt: "23.08.2026 UTC",
        result: "Рабочий цикл",
        trend: [
          { id: "m1", label: "1", value: 120 },
          { id: "m2", label: "2", value: 280 },
          { id: "m3", label: "3", value: 470 },
          { id: "m4", label: "4", value: 633 },
        ],
      },
      {
        id: "PANEL-Z2",
        title: "Solar Panel Z2",
        status: "archive",
        generatedKwh: 1004.9,
        remainingSeconds: 0,
        lifetimeProgress: 100,
        activatedAt: "01.06.2025 UTC",
        expiresAt: "28.11.2025 UTC",
        result: "Завершена",
        trend: [
          { id: "z1", label: "1", value: 250 },
          { id: "z2", label: "2", value: 520 },
          { id: "z3", label: "3", value: 810 },
          { id: "z4", label: "4", value: 1004 },
        ],
      },
    ],
  },
};

function isPanelsPortfolioPeriod(
  value: string,
): value is PanelsPortfolioPeriod {
  return value === "30d" || value === "180d";
}

function isPanelsPortfolioState(value: string): value is PanelsPortfolioState {
  return value === "all" || value === "active" || value === "archive";
}

function stateLabel(state: PanelsPortfolioPreviewPanel["status"]): string {
  return state === "active" ? "Активна" : "Архив";
}

function periodSeconds(period: PanelsPortfolioPeriod): number {
  return period === "30d" ? 30 * 86400 : PANEL_LIFETIME_SECONDS;
}

function formatKwh(value: number): string {
  return `${value.toFixed(8)} kWh`;
}

function formatDerivedGenerationRate(
  generatedKwh: number,
  seconds: number,
): string {
  const safeSeconds = Math.max(seconds, 1);
  return `+${(generatedKwh / safeSeconds).toFixed(7)} kWh/с`;
}

function panelElapsedSeconds(panel: PanelsPortfolioPreviewPanel): number {
  if (panel.status === "archive") return PANEL_LIFETIME_SECONDS;
  return Math.max(PANEL_LIFETIME_SECONDS - panel.remainingSeconds, 1);
}

function panelDerivedRate(panel: PanelsPortfolioPreviewPanel): string {
  if (panel.status === "archive") return "архив";
  return formatDerivedGenerationRate(
    panel.generatedKwh,
    panelElapsedSeconds(panel),
  );
}

export function PanelsPortfolioSandboxPrototype(
  props: PanelsPortfolioSandboxPrototypeProps,
) {
  const [period, setPeriod] = useState<PanelsPortfolioPeriod>(
    props.initialPeriod ?? "180d",
  );
  const [state, setState] = useState<PanelsPortfolioState>(
    props.initialState ?? "all",
  );
  const preview = panelsPreviewByPeriod[period];
  const filteredPanels = useMemo(() => {
    if (state === "all") return preview.panels;
    return preview.panels.filter((panel) => panel.status === state);
  }, [preview.panels, state]);

  const segments = useMemo(
    () => [
      {
        id: "portfolio-lifetime",
        label: "Lifecycle",
        value: preview.lifetimeProgress,
        tone: "success" as const,
      },
      {
        id: "active-share",
        label: "Active",
        value: Math.round(
          (Number(preview.activePanels) /
            Math.max(Number(preview.totalPanels), 1)) *
            100,
        ),
        tone: "info" as const,
      },
      {
        id: "archive-share",
        label: "Archive",
        value: Math.round(
          (Number(preview.archivedPanels) /
            Math.max(Number(preview.totalPanels), 1)) *
            100,
        ),
        tone: "warning" as const,
      },
    ],
    [
      preview.activePanels,
      preview.archivedPanels,
      preview.lifetimeProgress,
      preview.totalPanels,
    ],
  );

  const changePeriod = (next: string) => {
    if (isPanelsPortfolioPeriod(next)) setPeriod(next);
  };

  const changeState = (next: string) => {
    if (isPanelsPortfolioState(next)) setState(next);
  };

  return (
    <SimDashboardShell
      eyebrow="EFHC Simulation"
      title="Panels Portfolio screen draft"
      subtitle="internal stand-only preview: визуальный портфель панелей без current mode-подключения"
      contract={{
        id: "panels-portfolio-sandbox-prototype-1471",
        title: "Panels Portfolio internal stand screen draft",
        source: {
          label: "synthetic_preview / internal stand-only",
          dataKind: "synthetic_preview",
          synthetic: true,
        },
        state: {
          status: "success",
          message: "internal stand visual screen draft",
          freshness: "unknown",
        },
        mode: "simulation",
      }}
    >
      <div
        className="efhc-panels-dashboard-sandbox"
        data-panels-portfolio-sandbox-prototype="1471"
        data-panels-portfolio-formula-polish="1473"
        data-panels-portfolio-data-kind="synthetic_preview"
        data-panels-portfolio-preview-only="true"
        data-panels-portfolio-runtime-route-changed="false"
        data-panels-portfolio-write-flow="false"
        data-panel-lifetime-days="180"
        data-grafana-reference-only="true"
        data-sandbox-reference-only="true"
      >
        <SimDashboardToolbar
          title="Портфель панелей"
          subtitle="Панели как живой энергетический портфель: active, archive, countdown, generated kWh"
          period={
            <SimPeriodFilter
              label="Период"
              onChange={changePeriod}
              options={periodOptions}
              value={period}
            />
          }
          freshness={
            <SimFreshnessBadge
              freshness="unknown"
              label="Preview"
              updatedAt="internal stand generated"
            />
          }
          actions={<SimStatusPill label="truth-safe preview" tone="info" />}
        >
          <SimPanelStateFilter
            label="Состояние"
            onChange={changeState}
            options={stateOptions}
            value={state}
          />
        </SimDashboardToolbar>

        <div className="efhc-panels-dashboard-sandbox__actions">
          <Link href="/panels">Открыть current mode Panels</Link>
          <Link href="/web-profile?section=history">История аккаунта</Link>
        </div>

        <div className="efhc-panels-dashboard-sandbox__kpi-strip">
          <SimStatCard
            hint="generated preview"
            label="Всего панелей"
            tone="info"
            value={preview.totalPanels}
          />
          <SimStatCard
            hint="active preview"
            label="Активные"
            tone="success"
            value={preview.activePanels}
          />
          <SimStatCard
            hint="archive preview"
            label="Архив"
            tone="neutral"
            value={preview.archivedPanels}
          />
          <SimStatCard
            hint="nearest expiry"
            label="Ближайшее завершение"
            tone="warning"
            value={preview.nearestExpiry}
          />
        </div>

        <SimPanelChrome
          footer="Источник: synthetic_preview. current mode /panels не изменён. 180-day lifecycle сохраняется."
          source="internal stand generated"
          status="success"
          statusLabel="Preview only"
          subtitle="Portfolio summary, lifecycle progress, distribution and activity strip"
          title="Сводка портфеля"
          tone="info"
          updatedAt="sandbox"
        >
          <div className="efhc-panels-dashboard-sandbox__summary-grid">
            <div>
              <strong>{formatKwh(preview.totalGenerated)}</strong>
              <span>Всего сгенерировано панелями</span>
            </div>
            <div>
              <strong>
                {formatDerivedGenerationRate(
                  preview.totalGenerated,
                  periodSeconds(period),
                )}
              </strong>
              <span>Скорость генерации preview</span>
            </div>
          </div>
          <SimSegmentedProgress
            dataKind="synthetic_preview"
            label="Портфельный прогресс"
            segments={segments}
            source="derived from generated preview"
            synthetic
          />
        </SimPanelChrome>

        <SimDashboardGrid>
          <SimPanelChrome
            footer="Future current mode port must use real panel records only."
            source="internal stand generated"
            status="success"
            statusLabel="Trend preview"
            subtitle="Мини-график показывает форму будущего портфеля, не real analytics"
            title="Рост портфеля"
            tone="success"
          >
            <SimMiniAreaChart
              ariaLabel="generated panels portfolio trend preview"
              label="Generated kWh"
              points={preview.portfolioTrend}
              source="synthetic_preview"
              synthetic
              tone="success"
              unit="kWh"
            />
          </SimPanelChrome>

          <SimPanelChrome
            footer="Active/archive split is preview-only in this component."
            source="internal stand generated"
            status="success"
            statusLabel="Distribution"
            subtitle="Active, archive and expiring-soon proportions"
            title="Состав портфеля"
            tone="info"
          >
            <SimMiniBarChart
              ariaLabel="generated panels distribution preview"
              label="Panels"
              points={preview.distribution}
              source="synthetic_preview"
              synthetic
              tone="info"
              unit="count"
            />
          </SimPanelChrome>

          <SimPanelChrome
            footer="Activity strip is a visual state idea, not a service event stream."
            source="internal stand generated"
            status="success"
            statusLabel="State strip"
            subtitle="Показывает будущий язык state timeline без real events claim"
            title="Состояние портфеля"
            tone="warning"
          >
            <SimActivityStrip
              ariaLabel="generated panels activity strip preview"
              label="Portfolio states"
              points={preview.activity}
              source="synthetic_preview"
              synthetic
            />
          </SimPanelChrome>
        </SimDashboardGrid>

        <SimDashboardSection
          subtitle="Карточки показывают статус, countdown, даты, результат и мини-тренд"
          title="Карточки панелей"
          actions={<SimStatusPill label={`${filteredPanels.length} shown`} />}
        >
          <div className="efhc-panels-dashboard-sandbox__panel-grid">
            {filteredPanels.map((panel) => (
              <article
                className="efhc-panels-dashboard-sandbox__panel-card"
                data-panel-card-sandbox="1471"
                data-panel-status={panel.status}
                data-panel-write-action="false"
                key={panel.id}
              >
                <div className="efhc-panels-dashboard-sandbox__panel-head">
                  <div>
                    <strong>{panel.id}</strong>
                    <span>{panel.title}</span>
                  </div>
                  <SimStatusPill
                    label={stateLabel(panel.status)}
                    tone={panel.status === "active" ? "success" : "neutral"}
                  />
                </div>

                <div className="efhc-panels-dashboard-sandbox__panel-metrics">
                  <div>
                    <span>Сгенерировано</span>
                    <strong>{formatKwh(panel.generatedKwh)}</strong>
                  </div>
                  <div>
                    <span>Скорость</span>
                    <strong>{panelDerivedRate(panel)}</strong>
                  </div>
                </div>

                {panel.status === "active" ? (
                  <SimCountdownProgress
                    dataKind="synthetic_preview"
                    label="Осталось до архива"
                    remainingSeconds={panel.remainingSeconds}
                    source="synthetic_preview / 180-day lifecycle"
                    synthetic
                    totalSeconds={PANEL_LIFETIME_SECONDS}
                  />
                ) : (
                  <SimProgressBar
                    label="Lifecycle complete"
                    showValue
                    tone="neutral"
                    value={100}
                  />
                )}

                <SimProgressBar
                  label="Жизненный цикл"
                  showValue
                  tone={panel.status === "active" ? "success" : "neutral"}
                  value={panel.lifetimeProgress}
                />

                <SimMiniSparkline
                  ariaLabel={`${panel.id} synthetic generation trend`}
                  label="Mini trend"
                  points={panel.trend}
                  source="synthetic_preview"
                  synthetic
                  tone={panel.status === "active" ? "success" : "neutral"}
                  unit="kWh"
                />

                <div className="efhc-panels-dashboard-sandbox__panel-dates">
                  <span>Старт: {panel.activatedAt}</span>
                  <span>Финиш: {panel.expiresAt}</span>
                  <strong>{panel.result}</strong>
                </div>
              </article>
            ))}
          </div>
        </SimDashboardSection>

        <SimPanelChrome
          footer="Activation, debit order bonus→main and idempotency stay only in existing current mode guarded flows."
          source="EFHC canon"
          status="success"
          statusLabel="No write actions"
          subtitle="Прототип не активирует панели и не списывает 100 EFHC"
          title="Truth / safety boundary"
          tone="success"
        >
          <div className="efhc-panels-dashboard-sandbox__rules">
            <span>1 EFHC = 1 kWh</span>
            <span>Panel lifecycle = 180 days</span>
            <span>synthetic_preview only</span>
            <span>current mode `/panels` unchanged</span>
            <span>no activation / no debit / no POST</span>
          </div>
        </SimPanelChrome>
      </div>
    </SimDashboardShell>
  );
}


