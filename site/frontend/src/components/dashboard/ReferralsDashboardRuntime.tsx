import React, { useMemo, useState } from "react";

import {
  SimActivityStrip,
  SimDashboardGrid,
  SimDashboardSection,
  SimDashboardToolbar,
  SimFilterBar,
  SimFreshnessBadge,
  SimMiniBarChart,
  SimPanelChrome,
  SimProgressBar,
  SimReferralScopeFilter,
  SimSegmentedProgress,
  SimStatCard,
  SimStatusPill,
} from "./SimulationDashboardUiKit";

type ReferralScope = "all" | "active" | "inactive";

export type ReferralsDashboardRuntimeStats = {
  bonusBalance: string;
  bonusTotal: string;
  totalReferrals: number;
  activeReferrals: number;
  inactiveReferrals: number;
  level: number;
  nextLevel: number | null;
  refsToNext: number;
  progress: number;
  referralLinkReady: boolean;
};

export type ReferralsDashboardRuntimeLabels = {
  title: string;
  subtitle: string;
  fresh: string;
  loading: string;
  error: string;
  source: string;
  rawData: string;
  derivedDisplay: string;
  total: string;
  active: string;
  inactive: string;
  bonusBalance: string;
  bonusTotal: string;
  progressTitle: string;
  progressSubtitle: string;
  growthTitle: string;
  growthSubtitle: string;
  bonusTitle: string;
  bonusSubtitle: string;
  scopeLabel: string;
  scopeAll: string;
  scopeActive: string;
  scopeInactive: string;
  reset: string;
  emptyTitle: string;
  emptyDetail: string;
  privacy: string;
  truth: string;
  noHistory: string;
  bonusRule: string;
  linkReady: string;
  linkPending: string;
  refsToNext: string;
  maxLevel: string;
};

type ReferralsDashboardRuntimeProps = {
  stats: ReferralsDashboardRuntimeStats;
  labels: ReferralsDashboardRuntimeLabels;
  loading?: boolean;
  error?: boolean;
  updatedAt?: string | null;
};

function toNumber(value: string | number | null | undefined): number {
  if (value === null || value === undefined) return 0;
  const numeric = typeof value === "number" ? value : Number(value);
  return Number.isFinite(numeric) ? numeric : 0;
}

function clampRatio(value: number): number {
  if (!Number.isFinite(value)) return 0;
  if (value < 0) return 0;
  if (value > 1) return 1;
  return value;
}

function clampPct(value: number): number {
  return Math.round(clampRatio(value) * 100);
}

function formatAmount(value: string): string {
  const numeric = toNumber(value);
  return numeric
    .toFixed(8)
    .replace(/\.0+$/, "")
    .replace(/(\.\d*?)0+$/, "$1");
}

function scopeHint(
  scope: ReferralScope,
  stats: ReferralsDashboardRuntimeStats,
  labels: ReferralsDashboardRuntimeLabels,
): string {
  if (scope === "active") {
    return `${labels.active}: ${stats.activeReferrals}`;
  }
  if (scope === "inactive") {
    return `${labels.inactive}: ${stats.inactiveReferrals}`;
  }
  return `${labels.total}: ${stats.totalReferrals}`;
}

export function ReferralsDashboardRuntime(
  props: ReferralsDashboardRuntimeProps,
) {
  const [scope, setScope] = useState<ReferralScope>("all");
  const totals = useMemo(() => {
    const total = Math.max(0, props.stats.totalReferrals);
    const active = Math.max(0, props.stats.activeReferrals);
    const inactive = Math.max(0, props.stats.inactiveReferrals);
    const activeRatio = total > 0 ? active / total : 0;
    const progress = clampRatio(props.stats.progress);
    return {
      active,
      activePct: clampPct(activeRatio),
      inactive,
      progressPct: clampPct(progress),
      total,
    };
  }, [props.stats]);

  const statusLabel = props.error
    ? props.labels.error
    : props.loading
      ? props.labels.loading
      : props.labels.fresh;
  const freshness = props.error || props.loading ? "unknown" : "fresh";
  const panelStatus = props.error
    ? "error"
    : props.loading
      ? "loading"
      : "success";
  const linkLabel = props.stats.referralLinkReady
    ? props.labels.linkReady
    : props.labels.linkPending;

  return (
    <section
      className="efhc-referrals-dashboard-runtime"
      data-dashboard-contract="referrals-dashboard-runtime"
      data-referrals-dashboard-runtime="1478"
      data-referrals-dashboard-no-raw-tg-id="true"
      data-referrals-dashboard-no-fake-history="true"
      data-referrals-dashboard-no-write-bypass="true"
      data-referrals-dashboard-truth="raw-derived"
    >
      <SimDashboardToolbar
        freshness={
          <SimFreshnessBadge freshness={freshness} label={statusLabel} />
        }
        subtitle={props.labels.subtitle}
        title={props.labels.title}
        updatedAt={props.updatedAt ?? props.labels.source}
      />

      <SimFilterBar
        groups={[]}
        onReset={() => setScope("all")}
        resetLabel={props.labels.reset}
      >
        <SimReferralScopeFilter
          label={props.labels.scopeLabel}
          onChange={(value) => setScope(value as ReferralScope)}
          options={[
            { key: "all", label: props.labels.scopeAll },
            { key: "active", label: props.labels.scopeActive },
            { key: "inactive", label: props.labels.scopeInactive },
          ]}
          value={scope}
        />
      </SimFilterBar>

      <SimDashboardGrid>
        <SimStatCard
          hint={props.labels.rawData}
          label={props.labels.total}
          tone="info"
          value={totals.total}
        />
        <SimStatCard
          hint={props.labels.derivedDisplay}
          label={props.labels.active}
          tone="success"
          value={totals.active}
        />
        <SimStatCard
          hint={props.labels.derivedDisplay}
          label={props.labels.inactive}
          tone="warning"
          value={totals.inactive}
        />
        <SimStatCard
          hint={props.labels.rawData}
          label={props.labels.bonusBalance}
          tone="neutral"
          value={`${formatAmount(props.stats.bonusBalance)} EFHCb`}
        />
      </SimDashboardGrid>

      <SimDashboardGrid>
        <SimPanelChrome
          source={props.labels.source}
          status={panelStatus}
          statusLabel={statusLabel}
          subtitle={props.labels.progressSubtitle}
          title={props.labels.progressTitle}
          tone="success"
        >
          <div className="efhc-referrals-dashboard-runtime__scope">
            <SimStatusPill label={scopeHint(scope, props.stats, props.labels)} />
            <SimStatusPill label={linkLabel} tone="info" />
          </div>
          <SimProgressBar
            label={
              props.stats.nextLevel === null
                ? props.labels.maxLevel
                : `${props.labels.refsToNext}: ${props.stats.refsToNext}`
            }
            showValue
            tone="success"
            value={totals.progressPct}
          />
          <SimSegmentedProgress
            dataKind="derived"
            label={props.labels.growthTitle}
            segments={[
              {
                id: "active",
                label: props.labels.active,
                max: totals.total || 1,
                tone: "success",
                value: totals.active,
              },
              {
                id: "inactive",
                label: props.labels.inactive,
                max: totals.total || 1,
                tone: "warning",
                value: totals.inactive,
              },
            ]}
            source={props.labels.derivedDisplay}
            synthetic={false}
          />
        </SimPanelChrome>

        <SimPanelChrome
          source={props.labels.source}
          status={panelStatus}
          statusLabel={statusLabel}
          subtitle={props.labels.bonusSubtitle}
          title={props.labels.bonusTitle}
          tone="info"
        >
          <div className="efhc-referrals-dashboard-runtime__bonus">
            <strong>{formatAmount(props.stats.bonusTotal)} EFHCb</strong>
            <span>{props.labels.bonusTotal}</span>
          </div>
          <SimMiniBarChart
            ariaLabel={props.labels.growthTitle}
            dataKind="derived"
            emptyLabel={props.labels.emptyDetail}
            points={[
              {
                id: "active",
                label: props.labels.active,
                tone: "success",
                value: totals.active,
              },
              {
                id: "inactive",
                label: props.labels.inactive,
                tone: "warning",
                value: totals.inactive,
              },
            ]}
            source={props.labels.derivedDisplay}
            synthetic={false}
            tone="success"
            unit="refs"
          />
        </SimPanelChrome>
      </SimDashboardGrid>

      <SimDashboardSection
        subtitle={props.labels.growthSubtitle}
        title={props.labels.growthTitle}
      >
        <div className="efhc-referrals-dashboard-runtime__cards">
          <article data-referrals-dashboard-card="active-ratio">
            <span>{props.labels.active}</span>
            <strong>{totals.activePct}%</strong>
            <small>{props.labels.derivedDisplay}</small>
          </article>
          <article data-referrals-dashboard-card="bonus-rule">
            <span>{props.labels.bonusRule}</span>
            <strong>+0.1 EFHCb</strong>
            <small>{props.labels.truth}</small>
          </article>
          <article data-referrals-dashboard-card="privacy">
            <span>{props.labels.privacy}</span>
            <strong>{props.labels.noHistory}</strong>
            <small>{props.labels.source}</small>
          </article>
        </div>
      </SimDashboardSection>

      <SimActivityStrip
        dataKind="derived"
        emptyLabel={props.labels.emptyDetail}
        label={props.labels.truth}
        points={[
          { id: "raw", label: props.labels.rawData, value: totals.total },
          {
            id: "active",
            label: props.labels.active,
            value: totals.active,
          },
          {
            id: "inactive",
            label: props.labels.inactive,
            value: totals.inactive,
          },
          { id: "history", label: props.labels.noHistory, value: 0 },
        ]}
        source={props.labels.source}
        synthetic={false}
        tone="info"
      />
    </section>
  );
}

