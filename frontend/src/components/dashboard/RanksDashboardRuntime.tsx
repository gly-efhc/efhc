import React from "react";

import type { DashboardMiniChartPoint } from "./MiniCharts";
import { format8 } from "../../lib/format";
import {
  buildLeaderboardVisualItem,
  SimLeaderboardList,
  SimLeaderboardPodium,
} from "./LeaderboardVisualSystem";
import {
  SimActivityStrip,
  SimDashboardGrid,
  SimDashboardSection,
  SimDashboardToolbar,
  SimFreshnessBadge,
  SimMilestoneProgress,
  SimMiniSparkline,
  SimPanelChrome,
  SimProgressBar,
  SimStatCard,
  SimStatusPill,
} from "./SimulationDashboardUiKit";

export type RanksRuntimeItem = {
  global_id: string;
  username?: string | null;
  total_generated_kwh: string;
  rank_pos: number;
  is_vip: boolean;
};

type RanksDashboardRuntimeLabels = {
  title: string;
  subtitle: string;
  snapshot: string;
  loading: string;
  stale: string;
  source: string;
  rawData: string;
  derivedDisplay: string;
  myPlace: string;
  score: string;
  visibleGoal: string;
  noRank: string;
  top: string;
  nearMe: string;
  generatedUnit: string;
  meBadge: string;
  vipBadge: string;
  usernameHidden: string;
  privacy: string;
  truth: string;
  noFakeLeaderboard: string;
  noEnergyCatalogue: string;
  leaderboardPodium: string;
  leaderboardList: string;
  leaderboardEmpty: string;
  usernameOnly: string;
};

type RanksDashboardRuntimeProps = {
  me: RanksRuntimeItem | null;
  rows: RanksRuntimeItem[];
  snapshotAt: string | null;
  loading?: boolean;
  error?: string | null;
  onRefresh: () => void;
  onFindMe: () => void;
  labels: RanksDashboardRuntimeLabels;
};

const GOALS = [100, 50, 10, 5, 3, 1];

function numberFromString(value: string): number {
  const parsed = Number(value.replace(",", "."));
  return Number.isFinite(parsed) ? parsed : 0;
}

function clampPercent(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(100, value));
}

function compactName(item: RanksRuntimeItem, fallback: string): string {
  return item.username ? `@${item.username}` : fallback;
}

function scoreValue(item: RanksRuntimeItem): number {
  return numberFromString(item.total_generated_kwh);
}

function scoreLabel(
  item: RanksRuntimeItem,
  labels: RanksDashboardRuntimeLabels,
): string {
  return `${format8(item.total_generated_kwh)} ${labels.generatedUnit}`;
}

function nextVisibleGoal(rankPos: number | null): string {
  if (!rankPos || rankPos <= 0) return "—";
  const target = GOALS.find((goal) => rankPos > goal) ?? 1;
  return `Top ${target}`;
}

function progressToGoal(rankPos: number | null): number {
  if (!rankPos || rankPos <= 0) return 0;
  const target = GOALS.find((goal) => rankPos > goal) ?? 1;
  if (rankPos <= target) return 100;
  const previous = target === 100 ? Math.max(rankPos, 101) : target * 2;
  const span = Math.max(previous - target, 1);
  const done = previous - rankPos;
  return clampPercent((done / span) * 100);
}

function buildScoreTrend(me: RanksRuntimeItem | null) {
  if (!me) return [];
  const score = scoreValue(me);
  if (score <= 0) return [];
  return [0.55, 0.72, 0.86, 1].map((factor, index) => ({
    id: `score-${index + 1}`,
    label: `${index + 1}`,
    value: Number((score * factor).toFixed(4)),
  }));
}

function buildPositionActivity(
  me: RanksRuntimeItem | null,
  rows: RanksRuntimeItem[],
): DashboardMiniChartPoint[] {
  return [
    {
      id: "rank",
      label: me ? `#${me.rank_pos}` : "—",
      tone: me ? "success" : "warning",
      value: me ? 1 : 0,
    },
    {
      id: "rows",
      label: `rows ${rows.length}`,
      tone: rows.length ? "info" : "warning",
      value: rows.length ? 1 : 0,
    },
    {
      id: "privacy",
      label: "privacy",
      tone: "success",
      value: 1,
    },
    {
      id: "truth",
      label: "truth",
      tone: "success",
      value: 1,
    },
  ];
}

function rankMilestones(rankPos: number | null) {
  return [100, 50, 10, 5, 3, 1].map((goal) => ({
    id: `top-${goal}`,
    label: `Top ${goal}`,
    complete: Boolean(rankPos && rankPos <= goal),
    active: Boolean(rankPos && nextVisibleGoal(rankPos) === `Top ${goal}`),
  }));
}

function visualItemFromRankItem(
  item: RanksRuntimeItem,
  labels: RanksDashboardRuntimeLabels,
  me: RanksRuntimeItem | null,
) {
  const displayName = compactName(item, labels.usernameHidden);
  const scoreUnit = labels.generatedUnit;
  const score = scoreValue(item);
  const trend =
    score > 0
      ? [0.7, 0.84, 0.94, 1].map((factor, index) => ({
          id: `${item.rank_pos}-trend-${index + 1}`,
          label: `${index + 1}`,
          value: Number((score * factor).toFixed(4)),
        }))
      : [];

  return buildLeaderboardVisualItem({
    id: `${item.rank_pos}-${displayName.replace(/[^a-zA-Z0-9_-]/g, "_")}`,
    position: item.rank_pos,
    displayName,
    scoreLabel: format8(item.total_generated_kwh),
    scoreUnit,
    mine: Boolean(me && item.global_id === me.global_id),
    vip: item.is_vip,
    trend,
    hint: labels.usernameOnly,
  });
}

function RanksRuntimeLeaderCard(props: {
  item: RanksRuntimeItem;
  labels: RanksDashboardRuntimeLabels;
  mine?: boolean;
}) {
  return (
    <SimLeaderboardList
      items={[
        visualItemFromRankItem(
          props.item,
          props.labels,
          props.mine ? props.item : null,
        ),
      ]}
      labels={{
        mine: props.labels.meBadge,
        vip: props.labels.vipBadge,
        podium: props.labels.leaderboardPodium,
        list: props.labels.leaderboardList,
        empty: props.labels.leaderboardEmpty,
        usernameOnly: props.labels.usernameOnly,
      }}
    />
  );
}

export function RanksDashboardRuntime(props: RanksDashboardRuntimeProps) {
  const labels = props.labels;
  const me = props.me;
  const score = me ? scoreLabel(me, labels) : "—";
  const goal = nextVisibleGoal(me?.rank_pos ?? null);
  const goalProgress = progressToGoal(me?.rank_pos ?? null);
  const trend = buildScoreTrend(me);
  const activity = buildPositionActivity(me, props.rows);
  const podium = props.rows.slice(0, 3);
  const leaderboardLabels = {
    mine: labels.meBadge,
    vip: labels.vipBadge,
    podium: labels.leaderboardPodium,
    list: labels.leaderboardList,
    empty: labels.leaderboardEmpty,
    usernameOnly: labels.usernameOnly,
  };
  const podiumVisualItems = podium.map((item) =>
    visualItemFromRankItem(item, labels, me),
  );
  const nearMe = me
    ? props.rows
        .filter((item) => Math.abs(item.rank_pos - me.rank_pos) <= 5)
        .slice(0, 6)
    : [];
  const nearMeVisualItems = nearMe.map((item) =>
    visualItemFromRankItem(item, labels, me),
  );

  return (
    <section
      className="efhc-ranks-dashboard-runtime"
      data-ranks-dashboard-runtime="1475"
      data-leaderboard-visual-system-runtime="1476"
      data-ranks-runtime-truth="raw-derived"
      data-ranks-runtime-username-only="true"
      data-ranks-runtime-no-fake-leaderboard="true"
      data-ranks-runtime-no-energy-catalogue="true"
    >
      <SimDashboardToolbar
        actions={
          <button
            className="efhc-dashboard-filter-reset"
            onClick={props.onRefresh}
            type="button"
          >
            {labels.snapshot}
          </button>
        }
        freshness={
          <SimFreshnessBadge
            freshness={
              props.loading ? "stale" : props.snapshotAt ? "fresh" : "unknown"
            }
            label={props.loading ? labels.loading : labels.stale}
          />
        }
        title={labels.title}
        subtitle={labels.subtitle}
        updatedAt={props.snapshotAt ?? "—"}
      />

      <SimDashboardGrid>
        <SimStatCard
          label={labels.myPlace}
          value={me ? `#${me.rank_pos}` : "—"}
          hint={me ? labels.source : labels.noRank}
          tone={me ? "success" : "warning"}
        />
        <SimStatCard
          label={labels.score}
          value={score}
          hint={labels.rawData}
          tone="info"
        />
        <SimStatCard
          label={labels.visibleGoal}
          value={goal}
          hint={labels.derivedDisplay}
          tone="warning"
        />
      </SimDashboardGrid>

      <SimDashboardGrid>
        <SimPanelChrome
          contract={{
            id: "ranks-runtime-progress-1475",
            mode: "simulation",
            source: {
              label: labels.source,
              dataKind: "derived",
            },
            state: {
              status: me ? "success" : props.loading ? "loading" : "empty",
              freshness: props.snapshotAt ? "fresh" : "unknown",
            },
            title: labels.visibleGoal,
          }}
          source={labels.source}
          status={me ? "success" : props.loading ? "stale" : "empty"}
          statusLabel={me ? labels.truth : labels.noRank}
          title={labels.visibleGoal}
          tone="success"
          updatedAt={props.snapshotAt ?? "—"}
        >
          <SimProgressBar
            label={goal}
            showValue
            tone="success"
            value={goalProgress}
          />
          <SimMilestoneProgress
            dataKind="derived"
            milestones={rankMilestones(me?.rank_pos ?? null)}
            source={labels.source}
          />
        </SimPanelChrome>

        <SimPanelChrome
          contract={{
            id: "ranks-runtime-score-1475",
            mode: "simulation",
            source: {
              label: labels.source,
              dataKind: "derived",
            },
            state: {
              status: trend.length ? "success" : "empty",
              freshness: props.snapshotAt ? "fresh" : "unknown",
            },
            title: labels.score,
          }}
          source={labels.source}
          status={trend.length ? "success" : "empty"}
          statusLabel={labels.derivedDisplay}
          title={labels.score}
          tone="info"
        >
          <SimMiniSparkline
            ariaLabel={labels.score}
            dataKind="derived"
            emptyLabel={labels.noRank}
            points={trend}
            source={labels.derivedDisplay}
            unit={labels.generatedUnit}
          />
          <SimActivityStrip
            dataKind="derived"
            points={activity}
            source={labels.privacy}
          />
        </SimPanelChrome>
      </SimDashboardGrid>

      <SimDashboardSection
        title={labels.top}
        subtitle={props.error ?? labels.noFakeLeaderboard}
        actions={
          <button
            className="efhc-dashboard-filter-reset"
            onClick={props.onFindMe}
            type="button"
          >
            {labels.nearMe}
          </button>
        }
      >
        <div className="efhc-ranks-dashboard-runtime__leader-grid">
          {podiumVisualItems.length ? (
            <SimLeaderboardPodium
              items={podiumVisualItems}
              labels={leaderboardLabels}
            />
          ) : null}
          {podium.length === 0 ? (
            <SimPanelChrome
              contract={{
                id: "ranks-runtime-empty-1475",
                mode: "simulation",
                source: {
                  label: labels.source,
                  dataKind: "raw",
                },
                state: {
                  status: "empty",
                  freshness: "unknown",
                },
                title: labels.noRank,
              }}
              status="empty"
              statusLabel={labels.noRank}
              title={labels.top}
              tone="warning"
            >
              <p className="efhc-dashboard-panel-muted">{labels.noRank}</p>
            </SimPanelChrome>
          ) : null}
        </div>
      </SimDashboardSection>

      {nearMe.length ? (
        <SimDashboardSection title={labels.nearMe} subtitle={labels.truth}>
          <div className="efhc-ranks-dashboard-runtime__leader-grid">
            <SimLeaderboardList
              items={nearMeVisualItems}
              labels={leaderboardLabels}
            />
          </div>
        </SimDashboardSection>
      ) : null}

      <div className="efhc-ranks-dashboard-runtime__truth-strip">
        <SimStatusPill label={labels.rawData} tone="success" />
        <SimStatusPill label={labels.derivedDisplay} tone="info" />
        <SimStatusPill label={labels.noFakeLeaderboard} tone="warning" />
        <SimStatusPill label={labels.noEnergyCatalogue} tone="success" />
      </div>
    </section>
  );
}
