import React, { useMemo } from "react";

import type { DashboardMiniChartPoint } from "./MiniCharts";
import { format8, sumScaledDown } from "../../lib/format";
import {
  SimActivityStrip,
  SimCountdownProgress,
  SimDashboardGrid,
  SimDashboardSection,
  SimDashboardToolbar,
  SimFreshnessBadge,
  SimMiniBarChart,
  SimMiniSparkline,
  SimPanelChrome,
  SimPanelStateFilter,
  SimProgressBar,
  SimSegmentedProgress,
  SimStatCard,
  SimStatusPill,
} from "./SimulationDashboardUiKit";
import type { DbId } from "../../types/db-id";

type PanelsPortfolioRuntimeState = "active" | "archive";

export type PanelsPortfolioRuntimePanel = {
  id: DbId;
  public_id: string;
  activated_at?: string | null;
  created_at?: string | null;
  expires_at?: string | null;
  archived_at?: string | null;
  remaining_seconds?: number | null;
  base_gen_per_sec: string;
  generated_kwh: string;
  is_active: boolean;
};

export type PanelsPortfolioRuntimeLabels = {
  title: string;
  subtitle: string;
  stateLabel: string;
  active: string;
  archive: string;
  loadedPanels: string;
  activePanels: string;
  archiveLoaded: string;
  generatedTotal: string;
  activeGeneration: string;
  loadedGenerated: string;
  loadedRate: string;
  lifecycle: string;
  portfolioSummary: string;
  portfolioSummarySubtitle: string;
  generatedByLoadedPanels: string;
  statusStrip: string;
  panelCards: string;
  panelCardsSubtitle: string;
  generated: string;
  remaining: string;
  activatedAt: string;
  expiresAt: string;
  statusActive: string;
  statusArchive: string;
  noLoadedPanels: string;
  sourceRaw: string;
  sourceDerived: string;
  freshnessLive: string;
  snapshotOnly: string;
  noWriteActions: string;
  expiringSoon: string;
  newlyActive: string;
  activeCycle: string;
  archivedComplete: string;
  microState: string;
  panelCardA11y: string;
  durationDays: string;
  durationHours: string;
  durationMinutes: string;
  durationSeconds: string;
  durationElapsed: string;
  durationComplete: string;
};

type PanelsPortfolioRuntimeProps = {
  tab: PanelsPortfolioRuntimeState;
  items: PanelsPortfolioRuntimePanel[];
  activeCount: number | null;
  totalGeneratedByPanels: string | null;
  activeGeneration: string;
  effectiveRate: string | null;
  serverNowIso: string | null;
  loading: boolean;
  error: string | null;
  onTabChange: (tab: PanelsPortfolioRuntimeState) => void;
  labels: PanelsPortfolioRuntimeLabels;
};

const PANEL_LIFETIME_SECONDS = 180 * 86400;
const EXPIRING_SOON_SECONDS = 14 * 86400;
const NEWLY_ACTIVE_PROGRESS = 10;

type PanelMicroState =
  | "expiring_soon"
  | "newly_active"
  | "active_cycle"
  | "archived_complete";

function toNumber(value: string | number | null | undefined): number {
  if (value === null || value === undefined) return 0;
  const numeric = typeof value === "number" ? value : Number(value);
  return Number.isFinite(numeric) ? numeric : 0;
}

function clampPercent(value: number): number {
  if (!Number.isFinite(value)) return 0;
  if (value < 0) return 0;
  if (value > 100) return 100;
  return Math.round(value);
}

function panelLabel(panel: PanelsPortfolioRuntimePanel): string {
  return /^PNL-(?!00000000$)[0-9]{8}$/.test(panel.public_id) ? panel.public_id : "Ошибка целостности PNL";
}

function buildPanelPoints(
  panels: PanelsPortfolioRuntimePanel[],
): DashboardMiniChartPoint[] {
  return panels.slice(0, 8).map((panel, index) => ({
    id: String(panel.id),
    label: panelLabel(panel),
    value: toNumber(panel.generated_kwh),
    tone: panel.is_active ? "success" : "neutral",
    x: index,
  }));
}

function buildStatusPoints(
  panels: PanelsPortfolioRuntimePanel[],
): DashboardMiniChartPoint[] {
  if (panels.length === 0) {
    return [{ id: "empty", label: "empty", value: 0, tone: "neutral" }];
  }
  return panels.slice(0, 12).map((panel) => ({
    id: String(panel.id),
    label: panelLabel(panel),
    value: panel.is_active ? 1 : 0,
    tone: panel.is_active ? "success" : "neutral",
  }));
}

function lifecycleProgress(panel: PanelsPortfolioRuntimePanel): number {
  if (!panel.is_active) return 100;
  const remaining = panel.remaining_seconds;
  if (remaining === null || remaining === undefined) return 0;
  const elapsed = PANEL_LIFETIME_SECONDS - Math.max(remaining, 0);
  return clampPercent((elapsed / PANEL_LIFETIME_SECONDS) * 100);
}

function panelMicroState(panel: PanelsPortfolioRuntimePanel): PanelMicroState {
  if (!panel.is_active) return "archived_complete";
  const progress = lifecycleProgress(panel);
  const remaining = panel.remaining_seconds ?? PANEL_LIFETIME_SECONDS;
  if (remaining <= EXPIRING_SOON_SECONDS) return "expiring_soon";
  if (progress <= NEWLY_ACTIVE_PROGRESS) return "newly_active";
  return "active_cycle";
}

function panelMicroStateLabel(
  state: PanelMicroState,
  labels: PanelsPortfolioRuntimeLabels,
): string {
  if (state === "expiring_soon") return labels.expiringSoon;
  if (state === "newly_active") return labels.newlyActive;
  if (state === "archived_complete") return labels.archivedComplete;
  return labels.activeCycle;
}

function panelCardClassName(state: PanelMicroState): string {
  return [
    "efhc-panels-dashboard-runtime__panel-card",
    `efhc-panels-dashboard-runtime__panel-card--${state}`,
  ].join(" ");
}

function pad2(value: number): string {
  return value < 10 ? `0${value}` : String(value);
}

function formatUtcMinute(iso: string | null | undefined): string {
  if (!iso) return "—";
  const ms = Date.parse(iso);
  if (Number.isNaN(ms)) return "—";
  const date = new Date(ms);
  return [
    `${pad2(date.getUTCDate())}.${pad2(date.getUTCMonth() + 1)}` +
      `.${date.getUTCFullYear()}`,
    `${pad2(date.getUTCHours())}:${pad2(date.getUTCMinutes())} UTC`,
  ].join(" ");
}

function formatKwhDisplay(value: string): string {
  return `${value} kWh`;
}

function loadedGeneratedTotal(panels: PanelsPortfolioRuntimePanel[]): string {
  const sum = panels.reduce(
    (acc, panel) => sumScaledDown(acc, panel.generated_kwh, 8),
    "0.00000000",
  );
  return `${format8(sum)} kWh`;
}

export function PanelsPortfolioRuntime(props: PanelsPortfolioRuntimeProps) {
  const loadedActive = useMemo(
    () => props.items.filter((panel) => panel.is_active).length,
    [props.items],
  );
  const loadedArchive = useMemo(
    () => props.items.filter((panel) => !panel.is_active).length,
    [props.items],
  );
  const generatedPoints = useMemo(
    () => buildPanelPoints(props.items),
    [props.items],
  );
  const statusPoints = useMemo(
    () => buildStatusPoints(props.items),
    [props.items],
  );
  const averageLifecycle = useMemo(() => {
    if (props.items.length === 0) return 0;
    const sum = props.items.reduce(
      (acc, panel) => acc + lifecycleProgress(panel),
      0,
    );
    return clampPercent(sum / props.items.length);
  }, [props.items]);

  const segments = useMemo(
    () => [
      {
        id: "active-loaded",
        label: props.labels.active,
        value: clampPercent(
          props.items.length === 0
            ? 0
            : (loadedActive / props.items.length) * 100,
        ),
        tone: "success" as const,
      },
      {
        id: "archive-loaded",
        label: props.labels.archive,
        value: clampPercent(
          props.items.length === 0
            ? 0
            : (loadedArchive / props.items.length) * 100,
        ),
        tone: "neutral" as const,
      },
      {
        id: "lifecycle-loaded",
        label: props.labels.lifecycle,
        value: averageLifecycle,
        tone: "info" as const,
      },
    ],
    [
      averageLifecycle,
      loadedActive,
      loadedArchive,
      props.items.length,
      props.labels.active,
      props.labels.archive,
      props.labels.lifecycle,
    ],
  );

  const stateOptions = [
    {
      key: "active",
      label: props.labels.active,
      description: props.labels.sourceRaw,
    },
    {
      key: "archive",
      label: props.labels.archive,
      description: props.labels.sourceRaw,
    },
  ];

  return (
    <section
      className="efhc-panels-dashboard-runtime"
      data-panels-portfolio-runtime-port="1472"
      data-panel-cards-deep-polish="1473"
      data-panel-card-accessibility="true"
      data-panels-portfolio-data-kind="raw-derived"
      data-panels-portfolio-source="panels-summary-and-panel-list"
      data-panels-portfolio-write-flow="false"
      data-panel-lifetime-days="180"
      data-grafana-reference-only="true"
      data-sandbox-reference-only="true"
    >
      <SimDashboardToolbar
        actions={
          <SimStatusPill label={props.labels.noWriteActions} tone="success" />
        }
        freshness={
          <SimFreshnessBadge
            freshness={props.error ? "stale" : "fresh"}
            label={props.labels.freshnessLive}
            updatedAt={props.serverNowIso ?? props.labels.snapshotOnly}
          />
        }
        period={
          <SimPanelStateFilter
            label={props.labels.stateLabel}
            onChange={(next) => {
              if (next === "active" || next === "archive") {
                props.onTabChange(next);
              }
            }}
            options={stateOptions}
            value={props.tab}
          />
        }
        subtitle={props.labels.subtitle}
        title={props.labels.title}
        updatedAt={props.serverNowIso ?? props.labels.snapshotOnly}
      />

      <div className="efhc-panels-dashboard-runtime__kpi-strip">
        <SimStatCard
          hint={props.labels.sourceRaw}
          label={props.labels.activePanels}
          tone="success"
          value={props.activeCount ?? "—"}
        />
        <SimStatCard
          hint={props.labels.sourceDerived}
          label={props.labels.loadedPanels}
          tone="info"
          value={props.items.length}
        />
        <SimStatCard
          hint={props.labels.sourceDerived}
          label={props.labels.archiveLoaded}
          tone="neutral"
          value={loadedArchive}
        />
        <SimStatCard
          hint={props.labels.sourceRaw}
          label={props.labels.activeGeneration}
          tone="success"
          value={props.activeGeneration}
        />
      </div>

      <SimPanelChrome
        footer={props.labels.snapshotOnly}
        source="source / derived current summary"
        status={props.error ? "error" : props.loading ? "loading" : "success"}
        statusLabel={props.error ? "error" : props.loading ? "loading" : "live"}
        subtitle={props.labels.portfolioSummarySubtitle}
        title={props.labels.portfolioSummary}
        tone={props.error ? "danger" : "info"}
        updatedAt={props.serverNowIso ?? props.labels.snapshotOnly}
      >
        <div className="efhc-panels-dashboard-runtime__summary-grid">
          <div>
            <strong>{props.totalGeneratedByPanels ?? "—"}</strong>
            <span>{props.labels.generatedTotal}</span>
          </div>
          <div>
            <strong>{loadedGeneratedTotal(props.items)}</strong>
            <span>{props.labels.loadedGenerated}</span>
          </div>
          <div>
            <strong>{props.effectiveRate ?? "—"}</strong>
            <span>{props.labels.loadedRate}</span>
          </div>
        </div>
        <SimSegmentedProgress
          dataKind="derived"
          label={props.labels.lifecycle}
          segments={segments}
          source={props.labels.sourceDerived}
        />
      </SimPanelChrome>

      <SimDashboardGrid>
        <SimPanelChrome
          footer={props.labels.sourceDerived}
          source={props.labels.sourceRaw}
          status={props.items.length ? "success" : "empty"}
          statusLabel="snapshot"
          subtitle={props.labels.sourceDerived}
          title={props.labels.generatedByLoadedPanels}
          tone="success"
        >
          <SimMiniBarChart
            ariaLabel={props.labels.generatedByLoadedPanels}
            label={props.labels.generated}
            points={generatedPoints}
            source={props.labels.sourceDerived}
            tone="success"
            unit="kWh"
          />
        </SimPanelChrome>

        <SimPanelChrome
          footer={props.labels.sourceDerived}
          source={props.labels.sourceRaw}
          status={props.items.length ? "success" : "empty"}
          statusLabel="snapshot"
          subtitle={props.labels.snapshotOnly}
          title={props.labels.statusStrip}
          tone="info"
        >
          <SimActivityStrip
            ariaLabel={props.labels.statusStrip}
            label={props.labels.stateLabel}
            points={statusPoints}
            source={props.labels.sourceDerived}
          />
        </SimPanelChrome>
      </SimDashboardGrid>

      <SimDashboardSection
        subtitle={props.labels.panelCardsSubtitle}
        title={props.labels.panelCards}
        actions={<SimStatusPill label={`${props.items.length}`} />}
      >
        {props.items.length === 0 ? (
          <div className="efhc-panels-dashboard-runtime__empty">
            {props.loading ? "…" : props.labels.noLoadedPanels}
          </div>
        ) : (
          <div className="efhc-panels-dashboard-runtime__panel-grid">
            {props.items.slice(0, 6).map((panel) => {
              const progress = lifecycleProgress(panel);
              const statusLabel = panel.is_active
                ? props.labels.statusActive
                : props.labels.statusArchive;
              const microState = panelMicroState(panel);
              const microLabel = panelMicroStateLabel(microState, props.labels);
              const activatedIso = panel.activated_at ?? panel.created_at;
              const expiresIso = panel.expires_at ?? panel.archived_at;
              return (
                <article
                  aria-label={`${props.labels.panelCardA11y}: ${panelLabel(panel)}`}
                  className={panelCardClassName(microState)}
                  data-panel-card-runtime="1472"
                  data-panel-card-polish="1473"
                  data-panel-micro-state={microState}
                  data-panel-status={panel.is_active ? "active" : "archive"}
                  data-panel-write-action="false"
                  key={panel.id}
                >
                  <div className="efhc-panels-dashboard-runtime__panel-head">
                    <div>
                      <strong>{panelLabel(panel)}</strong>
                      <span>{statusLabel}</span>
                    </div>
                    <div className="efhc-panels-dashboard-runtime__panel-badges">
                      <SimStatusPill
                        label={statusLabel}
                        tone={panel.is_active ? "success" : "neutral"}
                      />
                      <small>{microLabel}</small>
                    </div>
                  </div>
                  <div className="efhc-panels-dashboard-runtime__panel-metrics">
                    <div>
                      <span>{props.labels.generated}</span>
                      <strong>{formatKwhDisplay(panel.generated_kwh)}</strong>
                    </div>
                  </div>
                  {panel.is_active ? (
                    <SimCountdownProgress
                      dataKind="raw"
                      label={props.labels.remaining}
                      remainingSeconds={Math.max(
                        panel.remaining_seconds ?? 0,
                        0,
                      )}
                      source={props.labels.sourceRaw}
                      totalSeconds={PANEL_LIFETIME_SECONDS}
                      completeLabel={props.labels.durationComplete}
                      elapsedLabel={props.labels.durationElapsed}
                      durationLabels={{
                        days: props.labels.durationDays,
                        hours: props.labels.durationHours,
                        minutes: props.labels.durationMinutes,
                        seconds: props.labels.durationSeconds,
                      }}
                    />
                  ) : null}
                  <SimProgressBar
                    label={props.labels.lifecycle}
                    showValue
                    tone={panel.is_active ? "success" : "neutral"}
                    value={progress}
                  />
                  <SimMiniSparkline
                    ariaLabel={panelLabel(panel)}
                    label={props.labels.generated}
                    points={[
                      { id: "zero", label: "0", value: 0 },
                      {
                        id: String(panel.id),
                        label: panelLabel(panel),
                        value: toNumber(panel.generated_kwh),
                      },
                    ]}
                    source={props.labels.sourceDerived}
                    tone={panel.is_active ? "success" : "neutral"}
                    unit="kWh"
                  />
                  <div className="efhc-panels-dashboard-runtime__panel-dates">
                    <span>
                      {props.labels.activatedAt}:{" "}
                      {formatUtcMinute(activatedIso)}
                    </span>
                    <span>
                      {props.labels.expiresAt}: {formatUtcMinute(expiresIso)}
                    </span>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </SimDashboardSection>
    </section>
  );
}

export const panelsPortfolioRuntimeVersion =
  "EFHC_PANELS_PORTFOLIO_RUNTIME_PORT_V1";

export const panelCardsDeepPolishVersion = "EFHC_PANEL_CARDS_DEEP_POLISH_V1";
