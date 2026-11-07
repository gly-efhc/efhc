import React from "react";

import {
  DashboardFilterBar,
  DashboardFilterGroup,
} from "./DashboardFilters";
import {
  DashboardFreshnessBadge,
  DashboardTimeRangePicker,
  DashboardToolbar,
} from "./DashboardToolbar";
import { PanelChrome } from "./PanelChrome";
import {
  DashboardActivityStrip,
  DashboardMiniAreaChart,
  DashboardMiniBarChart,
  DashboardMiniSparkline,
} from "./MiniCharts";
import {
  DashboardCircularProgress,
  DashboardCountdownProgress,
  DashboardMilestoneProgress,
  DashboardProgressBar,
  DashboardSegmentedProgress,
} from "./ProgressSystem";

import type {
  DashboardComponentContract,
  DashboardPanelStatus,
  DashboardPanelTone,
} from "../../lib/dashboard/componentContract";

export type SimTone = DashboardPanelTone;

type SimShellProps = React.PropsWithChildren<{
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  eyebrow?: React.ReactNode;
  actions?: React.ReactNode;
  contract?: DashboardComponentContract;
}>;

type SimSectionProps = React.PropsWithChildren<{
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  actions?: React.ReactNode;
}>;

type SimCardProps = React.PropsWithChildren<{
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  tone?: SimTone;
  contract?: DashboardComponentContract;
  footer?: React.ReactNode;
}>;


type SimDashboardToolbarProps = React.PropsWithChildren<{
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  period?: React.ReactNode;
  freshness?: React.ReactNode;
  updatedAt?: React.ReactNode;
  actions?: React.ReactNode;
}>;

type SimPeriodSwitchProps = React.ComponentProps<
  typeof DashboardTimeRangePicker
>;

type SimFreshnessBadgeProps = React.ComponentProps<
  typeof DashboardFreshnessBadge
>;

type SimFilterOption = {
  key: string;
  label: React.ReactNode;
  description?: React.ReactNode;
  disabled?: boolean;
};

type SimFilterKind =
  | "period"
  | "panel_state"
  | "leaderboard_scope"
  | "task_status"
  | "referral_scope"
  | "exchange_scope";

type SimFilterGroup = {
  key?: string;
  kind?: SimFilterKind;
  label: React.ReactNode;
  value: string;
  options: SimFilterOption[];
  onChange: (value: string) => void;
  queryKey?: string;
  querySync?: "disabled" | "safe_display_only";
};

type SimFilterBarProps = React.PropsWithChildren<{
  groups: SimFilterGroup[];
  resetLabel?: React.ReactNode;
  onReset?: () => void;
  className?: string;
}>;

type SimSingleFilterProps = {
  label?: React.ReactNode;
  value: string;
  options: SimFilterOption[];
  onChange: (value: string) => void;
  queryKey?: string;
  querySync?: "disabled" | "safe_display_only";
};


type SimPanelChromeProps = React.PropsWithChildren<{
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  status?: DashboardPanelStatus;
  statusLabel?: React.ReactNode;
  tone?: SimTone;
  updatedAt?: React.ReactNode;
  source?: React.ReactNode;
  actions?: React.ReactNode;
  footer?: React.ReactNode;
  contract?: DashboardComponentContract;
}>;

type SimStatCardProps = {
  label: React.ReactNode;
  value: React.ReactNode;
  hint?: React.ReactNode;
  tone?: SimTone;
};

type SimHeroEnergyCardProps = {
  title: React.ReactNode;
  value: React.ReactNode;
  unit?: React.ReactNode;
  subtitle?: React.ReactNode;
  progressLabel?: React.ReactNode;
  progressValue?: number;
  actions?: React.ReactNode;
};

type SimProgressBarProps = {
  label?: React.ReactNode;
  value: number;
  max?: number;
  tone?: SimTone;
  showValue?: boolean;
};

type SimSegmentedProgressProps = React.ComponentProps<
  typeof DashboardSegmentedProgress
>;

type SimCircularProgressProps = React.ComponentProps<
  typeof DashboardCircularProgress
>;

type SimCountdownProgressProps = React.ComponentProps<
  typeof DashboardCountdownProgress
>;

type SimMilestoneProgressProps = React.ComponentProps<
  typeof DashboardMilestoneProgress
>;


type SimMiniSparklineProps = React.ComponentProps<
  typeof DashboardMiniSparkline
>;

type SimMiniAreaChartProps = React.ComponentProps<
  typeof DashboardMiniAreaChart
>;

type SimMiniBarChartProps = React.ComponentProps<
  typeof DashboardMiniBarChart
>;

type SimActivityStripProps = React.ComponentProps<
  typeof DashboardActivityStrip
>;

type SimStatusPillProps = {
  label: React.ReactNode;
  tone?: SimTone;
};

const toneToClass: Record<SimTone, string> = {
  neutral: "efhc-sim-dashboard-tone-neutral",
  info: "efhc-sim-dashboard-tone-info",
  success: "efhc-sim-dashboard-tone-success",
  warning: "efhc-sim-dashboard-tone-warning",
  danger: "efhc-sim-dashboard-tone-danger",
};

export function SimDashboardShell(props: SimShellProps) {
  return (
    <section
      className="efhc-sim-dashboard-shell efhc-dashboard-surface"
      data-sim-dashboard-shell="1460"
      data-dashboard-contract={props.contract?.id ?? "simulation-shell"}
    >
      <header className="efhc-sim-dashboard-shell__header">
        <div>
          <p className="efhc-sim-dashboard-eyebrow">
            {props.eyebrow ?? "EFHC"}
          </p>
          <h1>{props.title}</h1>
          {props.subtitle ? <p>{props.subtitle}</p> : null}
        </div>
        {props.actions ? (
          <div className="efhc-sim-dashboard-shell__actions">
            {props.actions}
          </div>
        ) : null}
      </header>
      <div className="efhc-sim-dashboard-shell__body">
        {props.children}
      </div>
    </section>
  );
}

export function SimDashboardToolbar(props: SimDashboardToolbarProps) {
  return (
    <DashboardToolbar
      actions={props.actions}
      className="efhc-sim-dashboard-toolbar"
      freshness={props.freshness}
      mode="simulation"
      subtitle={props.subtitle}
      timeRange={props.period}
      title={props.title}
      updatedAt={props.updatedAt}
    >
      {props.children}
    </DashboardToolbar>
  );
}

export function SimPeriodSwitch(props: SimPeriodSwitchProps) {
  return <DashboardTimeRangePicker {...props} mode="simulation" />;
}

export function SimFreshnessBadge(props: SimFreshnessBadgeProps) {
  return <DashboardFreshnessBadge {...props} mode="simulation" />;
}

export function SimFilterBar(props: SimFilterBarProps) {
  return (
    <DashboardFilterBar
      className={`efhc-sim-dashboard-filter-bar ${props.className ?? ""}`}
      groups={props.groups}
      mode="simulation"
      onReset={props.onReset}
      resetLabel={props.resetLabel}
    >
      {props.children}
    </DashboardFilterBar>
  );
}

function buildSimFilterGroup(
  key: string,
  kind: SimFilterKind,
  fallbackLabel: React.ReactNode,
  props: SimSingleFilterProps,
) {
  return {
    key,
    kind,
    label: props.label ?? fallbackLabel,
    onChange: props.onChange,
    options: props.options,
    queryKey: props.queryKey,
    querySync: props.querySync ?? "disabled",
    value: props.value,
  };
}

export function SimPeriodFilter(props: SimSingleFilterProps) {
  return (
    <DashboardFilterGroup
      group={buildSimFilterGroup("sim-period", "period", "Period", props)}
      mode="simulation"
    />
  );
}

export function SimPanelStateFilter(props: SimSingleFilterProps) {
  return (
    <DashboardFilterGroup
      group={buildSimFilterGroup(
        "sim-panel-state",
        "panel_state",
        "Panel state",
        props,
      )}
      mode="simulation"
    />
  );
}

export function SimLeaderboardScopeFilter(props: SimSingleFilterProps) {
  return (
    <DashboardFilterGroup
      group={buildSimFilterGroup(
        "sim-leaderboard-scope",
        "leaderboard_scope",
        "Leaderboard scope",
        props,
      )}
      mode="simulation"
    />
  );
}

export function SimTaskStatusFilter(props: SimSingleFilterProps) {
  return (
    <DashboardFilterGroup
      group={buildSimFilterGroup(
        "sim-task-status",
        "task_status",
        "Task status",
        props,
      )}
      mode="simulation"
    />
  );
}

export function SimReferralScopeFilter(props: SimSingleFilterProps) {
  return (
    <DashboardFilterGroup
      group={buildSimFilterGroup(
        "sim-referral-scope",
        "referral_scope",
        "Referral scope",
        props,
      )}
      mode="simulation"
    />
  );
}


export function SimExchangeScopeFilter(props: SimSingleFilterProps) {
  return (
    <DashboardFilterGroup
      group={buildSimFilterGroup(
        "sim-exchange-scope",
        "exchange_scope",
        "Exchange scope",
        props,
      )}
      mode="simulation"
    />
  );
}

export function SimDashboardSection(props: SimSectionProps) {
  return (
    <section
      className="efhc-sim-dashboard-section"
      data-sim-dashboard-section="1460"
    >
      <div className="efhc-sim-dashboard-section__header">
        <div>
          <h2>{props.title}</h2>
          {props.subtitle ? <p>{props.subtitle}</p> : null}
        </div>
        {props.actions ? <div>{props.actions}</div> : null}
      </div>
      {props.children}
    </section>
  );
}

export function SimDashboardGrid(props: React.PropsWithChildren) {
  return (
    <div
      className="efhc-sim-dashboard-grid efhc-dashboard-grid"
      data-sim-dashboard-grid="1460"
    >
      {props.children}
    </div>
  );
}

export function SimPanelChrome(props: SimPanelChromeProps) {
  const tone = props.tone ?? "neutral";
  return (
    <PanelChrome
      actions={props.actions}
      className={`efhc-sim-panel-chrome ${toneToClass[tone]}`}
      contract={props.contract}
      dataMarker="sim-panel-chrome"
      footer={props.footer}
      mode="simulation"
      source={props.source}
      status={props.status}
      statusLabel={props.statusLabel}
      subtitle={props.subtitle}
      title={props.title}
      tone={tone}
      updatedAt={props.updatedAt}
    >
      {props.children}
    </PanelChrome>
  );
}

export function SimSummaryCard(props: SimCardProps) {
  const tone = props.tone ?? "neutral";
  return (
    <article
      className={`efhc-sim-dashboard-card ${toneToClass[tone]}`}
      data-sim-summary-card="1460"
      data-dashboard-contract={props.contract?.id ?? "sim-summary"}
    >
      <div className="efhc-sim-dashboard-card__head">
        <div>
          <h3>{props.title}</h3>
          {props.subtitle ? <p>{props.subtitle}</p> : null}
        </div>
      </div>
      <div className="efhc-sim-dashboard-card__body">
        {props.children}
      </div>
      {props.footer ? (
        <footer className="efhc-sim-dashboard-card__footer">
          {props.footer}
        </footer>
      ) : null}
    </article>
  );
}

export function SimStatCard(props: SimStatCardProps) {
  const tone = props.tone ?? "neutral";
  return (
    <article
      className={`efhc-sim-dashboard-stat ${toneToClass[tone]}`}
      data-sim-stat-card="1460"
    >
      <span>{props.label}</span>
      <strong>{props.value}</strong>
      {props.hint ? <small>{props.hint}</small> : null}
    </article>
  );
}

export function SimHeroEnergyCard(props: SimHeroEnergyCardProps) {
  return (
    <article
      className="efhc-sim-dashboard-hero"
      data-sim-hero-energy-card="1460"
    >
      <div className="efhc-sim-dashboard-hero__content">
        <p className="efhc-sim-dashboard-eyebrow">Energy</p>
        <h2>{props.title}</h2>
        <div className="efhc-sim-dashboard-hero__value">
          <strong>{props.value}</strong>
          {props.unit ? <span>{props.unit}</span> : null}
        </div>
        {props.subtitle ? <p>{props.subtitle}</p> : null}
        {props.progressValue !== undefined ? (
          <SimProgressBar
            label={props.progressLabel}
            value={props.progressValue}
            showValue
            tone="success"
          />
        ) : null}
      </div>
      {props.actions ? (
        <div className="efhc-sim-dashboard-hero__actions">
          {props.actions}
        </div>
      ) : null}
    </article>
  );
}

export function SimProgressBar(props: SimProgressBarProps) {
  const tone = props.tone ?? "info";
  return (
    <DashboardProgressBar
      dataKind="derived"
      label={props.label}
      max={props.max}
      showValue={props.showValue}
      tone={tone}
      value={props.value}
    />
  );
}

export function SimSegmentedProgress(props: SimSegmentedProgressProps) {
  return <DashboardSegmentedProgress {...props} />;
}

export function SimCircularProgress(props: SimCircularProgressProps) {
  return <DashboardCircularProgress {...props} />;
}

export function SimCountdownProgress(props: SimCountdownProgressProps) {
  return <DashboardCountdownProgress {...props} />;
}

export function SimMilestoneProgress(props: SimMilestoneProgressProps) {
  return <DashboardMilestoneProgress {...props} />;
}

export function SimMiniSparkline(props: SimMiniSparklineProps) {
  return <DashboardMiniSparkline dataKind="derived" {...props} />;
}

export function SimMiniAreaChart(props: SimMiniAreaChartProps) {
  return <DashboardMiniAreaChart dataKind="derived" {...props} />;
}

export function SimMiniBarChart(props: SimMiniBarChartProps) {
  return <DashboardMiniBarChart dataKind="derived" {...props} />;
}

export function SimActivityStrip(props: SimActivityStripProps) {
  return <DashboardActivityStrip dataKind="derived" {...props} />;
}

export function SimStatusPill(props: SimStatusPillProps) {
  const tone = props.tone ?? "neutral";
  return (
    <span
      className={`efhc-sim-dashboard-pill ${toneToClass[tone]}`}
      data-sim-status-pill="1460"
    >
      {props.label}
    </span>
  );
}


type SimLeaderboardRowItem = {
  id: string;
  rank?: React.ReactNode;
  label: React.ReactNode;
  value?: React.ReactNode;
  tone?: SimTone;
};

type SimTierItem = {
  id: string;
  label: React.ReactNode;
  active?: boolean;
  complete?: boolean;
};

export function SimPanelCard(props: SimCardProps) {
  return <SimSummaryCard {...props}>{props.children}</SimSummaryCard>;
}

export function SimPanelPortfolioSummary(props: SimCardProps) {
  return <SimSummaryCard {...props}>{props.children}</SimSummaryCard>;
}

export function SimRankCard(props: SimCardProps) {
  return <SimSummaryCard {...props}>{props.children}</SimSummaryCard>;
}

export function SimLeaderboardRow(props: SimLeaderboardRowItem) {
  const tone = props.tone ?? "neutral";
  return (
    <div
      className={`efhc-sim-leaderboard-row ${toneToClass[tone]}`}
      data-sim-leaderboard-row="1497"
    >
      {props.rank ? <strong>{props.rank}</strong> : null}
      <span>{props.label}</span>
      {props.value ? <b>{props.value}</b> : null}
    </div>
  );
}

export function SimRankTierLadder(props: { tiers: SimTierItem[] }) {
  return (
    <ol
      className="efhc-sim-rank-tier-ladder"
      data-sim-rank-tier-ladder="1497"
    >
      {props.tiers.map((tier) => (
        <li
          data-active={tier.active ? "true" : "false"}
          data-complete={tier.complete ? "true" : "false"}
          key={tier.id}
        >
          {tier.label}
        </li>
      ))}
    </ol>
  );
}

export function SimCountdownBadge(props: {
  label: React.ReactNode;
  tone?: SimTone;
}) {
  return <SimStatusPill label={props.label} tone={props.tone ?? "info"} />;
}

export function SimLiveIndicator(props: {
  label: React.ReactNode;
  active?: boolean;
}) {
  return (
    <span
      className="efhc-sim-live-indicator"
      data-active={props.active ? "true" : "false"}
      data-sim-live-indicator="1497"
      role="status"
    >
      {props.label}
    </span>
  );
}

export function SimValueDelta(props: {
  value: React.ReactNode;
  label?: React.ReactNode;
  tone?: SimTone;
}) {
  const tone = props.tone ?? "neutral";
  return (
    <span
      className={`efhc-sim-value-delta ${toneToClass[tone]}`}
      data-sim-value-delta="1497"
    >
      {props.label ? <small>{props.label}</small> : null}
      <strong>{props.value}</strong>
    </span>
  );
}

export function SimBalanceTicker(props: {
  value: React.ReactNode;
  unit?: React.ReactNode;
}) {
  return (
    <span className="efhc-sim-balance-ticker" data-sim-balance-ticker="1497">
      <strong>{props.value}</strong>
      {props.unit ? <small>{props.unit}</small> : null}
    </span>
  );
}

export function SimLoadingCard(props: { label?: React.ReactNode }) {
  return (
    <SimSummaryCard title={props.label ?? "…"}>
      <div className="efhc-sim-skeleton" data-sim-loading-card="1497" />
    </SimSummaryCard>
  );
}

export function SimEmptyCard(props: {
  title: React.ReactNode;
  text?: React.ReactNode;
}) {
  return (
    <SimSummaryCard title={props.title}>
      {props.text ? <p>{props.text}</p> : null}
    </SimSummaryCard>
  );
}

export function SimErrorCard(props: {
  title: React.ReactNode;
  text?: React.ReactNode;
}) {
  return (
    <SimSummaryCard title={props.title} tone="danger">
      {props.text ? <p>{props.text}</p> : null}
    </SimSummaryCard>
  );
}

export function SimSkeleton(props: { label?: React.ReactNode }) {
  return (
    <div className="efhc-sim-skeleton" data-sim-skeleton="1497">
      {props.label ?? "…"}
    </div>
  );
}








