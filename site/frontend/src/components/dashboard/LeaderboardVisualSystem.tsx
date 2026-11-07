import React from "react";

import type { DashboardMiniChartPoint } from "./MiniCharts";
import { SimMiniSparkline, SimStatusPill } from "./SimulationDashboardUiKit";


export type LeaderboardVisualTone = "gold" | "silver" | "bronze" | "normal";

export type LeaderboardVisualItem = {
  id: string;
  position: number;
  displayName: string;
  scoreLabel: string;
  scoreUnit: string;
  mine?: boolean;
  vip?: boolean;
  trend?: DashboardMiniChartPoint[];
  hint?: string;
};

type LeaderboardVisualLabels = {
  mine: string;
  vip: string;
  podium: string;
  list: string;
  empty: string;
  usernameOnly: string;
};

function rankTone(position: number): LeaderboardVisualTone {
  if (position === 1) return "gold";
  if (position === 2) return "silver";
  if (position === 3) return "bronze";
  return "normal";
}

function rankMedal(position: number): string {
  if (position === 1) return "🥇";
  if (position === 2) return "🥈";
  if (position === 3) return "🥉";
  return `#${position}`;
}

export function SimLeaderboardCard(props: {
  item: LeaderboardVisualItem;
  labels: LeaderboardVisualLabels;
  variant?: "podium" | "row";
}) {
  const item = props.item;
  const tone = rankTone(item.position);
  const variant = props.variant ?? "row";
  return (
    <article
      aria-label={`${item.displayName} #${item.position}`}
      className={`efhc-leaderboard-visual-system__card efhc-leaderboard-visual-system__card--${tone} efhc-leaderboard-visual-system__card--${variant} ${
        item.mine ? "efhc-leaderboard-visual-system__card--me" : ""
      }`}
      data-leaderboard-visual-system="1476"
      data-leaderboard-card-variant={variant}
      data-leaderboard-username-only="true"
      data-ranks-runtime-card="1475"
      data-ranks-runtime-username-only="true"
    >
      <div className="efhc-leaderboard-visual-system__rank">
        {rankMedal(item.position)}
      </div>
      <div className="efhc-leaderboard-visual-system__body">
        <div className="efhc-leaderboard-visual-system__name">
          {item.displayName}
        </div>
        <div className="efhc-leaderboard-visual-system__score">
          {item.scoreLabel} {item.scoreUnit}
        </div>
        {item.hint ? (
          <div className="efhc-leaderboard-visual-system__hint">
            {item.hint}
          </div>
        ) : null}
        {item.trend?.length ? (
          <SimMiniSparkline
            ariaLabel={`${item.displayName} trend`}
            dataKind="derived"
            emptyLabel={props.labels.empty}
            points={item.trend}
            source="leaderboard visual derived display"
            unit={item.scoreUnit}
          />
        ) : null}
      </div>
      <div className="efhc-leaderboard-visual-system__badges">
        {item.mine ? (
          <SimStatusPill label={props.labels.mine} tone="success" />
        ) : null}
        {item.vip ? (
          <SimStatusPill label={props.labels.vip} tone="warning" />
        ) : null}
      </div>
    </article>
  );
}

export function SimLeaderboardPodium(props: {
  items: LeaderboardVisualItem[];
  labels: LeaderboardVisualLabels;
}) {
  return (
    <div
      className="efhc-leaderboard-visual-system efhc-leaderboard-visual-system__podium"
      data-leaderboard-podium="1476"
      data-leaderboard-no-raw-tg-id="true"
    >
      {props.items.map((item) => (
        <SimLeaderboardCard
          key={item.id}
          item={item}
          labels={props.labels}
          variant="podium"
        />
      ))}
    </div>
  );
}

export function SimLeaderboardList(props: {
  items: LeaderboardVisualItem[];
  labels: LeaderboardVisualLabels;
}) {
  if (!props.items.length) {
    return (
      <div
        className="efhc-leaderboard-visual-system__empty"
        data-leaderboard-empty="1476"
      >
        {props.labels.empty}
      </div>
    );
  }

  return (
    <div
      className="efhc-leaderboard-visual-system efhc-leaderboard-visual-system__list"
      data-leaderboard-list="1476"
      data-leaderboard-no-raw-tg-id="true"
    >
      {props.items.map((item) => (
        <SimLeaderboardCard key={item.id} item={item} labels={props.labels} />
      ))}
    </div>
  );
}

export function buildLeaderboardVisualItem(input: {
  id: string;
  position: number;
  displayName: string;
  scoreLabel: string;
  scoreUnit: string;
  mine?: boolean;
  vip?: boolean;
  trend?: DashboardMiniChartPoint[];
  hint?: string;
}): LeaderboardVisualItem {
  return {
    id: input.id,
    position: input.position,
    displayName: input.displayName,
    scoreLabel: input.scoreLabel,
    scoreUnit: input.scoreUnit,
    mine: input.mine,
    vip: input.vip,
    trend: input.trend,
    hint: input.hint,
  };
}
