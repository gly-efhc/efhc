import React, { useMemo, useState } from "react";

import type { DashboardMiniChartPoint } from "./MiniCharts";
import {
  SimActivityStrip,
  SimDashboardGrid,
  SimDashboardSection,
  SimDashboardShell,
  SimDashboardToolbar,
  SimFreshnessBadge,
  SimLeaderboardScopeFilter,
  SimMilestoneProgress,
  SimMiniBarChart,
  SimMiniSparkline,
  SimPanelChrome,
  SimProgressBar,
  SimSegmentedProgress,
  SimStatCard,
  SimStatusPill,
} from "./SimulationDashboardUiKit";

type RanksSandboxScope = "kwh" | "referrals" | "near_me";

type RanksSandboxRow = {
  id: string;
  position: number;
  username: string;
  score: number;
  unit: "kWh" | "referrals";
  badge: string;
  isMe?: boolean;
  vip?: boolean;
  trend: DashboardMiniChartPoint[];
};

type RanksSandboxPreview = {
  title: string;
  subtitle: string;
  myPosition: number;
  myScore: number;
  myScoreUnit: "kWh" | "referrals";
  nextVisibleGoal: string;
  progressToGoal: number;
  rows: RanksSandboxRow[];
  trend: DashboardMiniChartPoint[];
  activity: DashboardMiniChartPoint[];
  ladder: Array<{
    id: string;
    label: string;
    complete?: boolean;
    active?: boolean;
  }>;
  segments: Array<{
    id: string;
    label: string;
    value: number;
    tone: "success" | "info" | "warning";
  }>;
};

type RanksDashboardSandboxPrototypeProps = {
  initialScope?: RanksSandboxScope;
};

const scopeOptions = [
  {
    key: "kwh",
    label: "kWh",
    description: "Preview лидерборда по сгенерированной энергии",
  },
  {
    key: "referrals",
    label: "Рефералы",
    description: "Preview лидерборда по активным рефералам",
  },
  {
    key: "near_me",
    label: "Рядом со мной",
    description: "Preview зоны вокруг пользователя без source identifiers",
  },
];

const kwhRows: RanksSandboxRow[] = [
  {
    id: "solar-maria",
    position: 1,
    username: "@solar_maria",
    score: 12842.4,
    unit: "kWh",
    badge: "Podium",
    vip: true,
    trend: [
      { id: "m1", label: "1", value: 9800 },
      { id: "m2", label: "2", value: 10300 },
      { id: "m3", label: "3", value: 11600 },
      { id: "m4", label: "4", value: 12842 },
    ],
  },
  {
    id: "green-den",
    position: 7,
    username: "@green_den",
    score: 6840.2,
    unit: "kWh",
    badge: "Моя зона",
    isMe: true,
    trend: [
      { id: "d1", label: "1", value: 5020 },
      { id: "d2", label: "2", value: 5440 },
      { id: "d3", label: "3", value: 6120 },
      { id: "d4", label: "4", value: 6840 },
    ],
  },
  {
    id: "energy-oleksii",
    position: 8,
    username: "@energy_oleksii",
    score: 6530.9,
    unit: "kWh",
    badge: "Сосед",
    trend: [
      { id: "o1", label: "1", value: 4890 },
      { id: "o2", label: "2", value: 5300 },
      { id: "o3", label: "3", value: 5990 },
      { id: "o4", label: "4", value: 6530 },
    ],
  },
  {
    id: "sun-id",
    position: 9,
    username: "@sun_id",
    score: 6294.1,
    unit: "kWh",
    badge: "Сосед",
    trend: [
      { id: "s1", label: "1", value: 4500 },
      { id: "s2", label: "2", value: 5120 },
      { id: "s3", label: "3", value: 5740 },
      { id: "s4", label: "4", value: 6294 },
    ],
  },
];

const referralRows: RanksSandboxRow[] = [
  {
    id: "ref-lina",
    position: 1,
    username: "@lina_solar",
    score: 48,
    unit: "referrals",
    badge: "Podium",
    vip: true,
    trend: [
      { id: "r1", label: "1", value: 20 },
      { id: "r2", label: "2", value: 28 },
      { id: "r3", label: "3", value: 37 },
      { id: "r4", label: "4", value: 48 },
    ],
  },
  {
    id: "ref-me",
    position: 12,
    username: "@green_den",
    score: 9,
    unit: "referrals",
    badge: "Моя зона",
    isMe: true,
    trend: [
      { id: "rm1", label: "1", value: 3 },
      { id: "rm2", label: "2", value: 5 },
      { id: "rm3", label: "3", value: 7 },
      { id: "rm4", label: "4", value: 9 },
    ],
  },
  {
    id: "ref-ivan",
    position: 13,
    username: "@ivan_energy",
    score: 8,
    unit: "referrals",
    badge: "Сосед",
    trend: [
      { id: "ri1", label: "1", value: 2 },
      { id: "ri2", label: "2", value: 4 },
      { id: "ri3", label: "3", value: 6 },
      { id: "ri4", label: "4", value: 8 },
    ],
  },
];

function buildPreview(scope: RanksSandboxScope): RanksSandboxPreview {
  if (scope === "referrals") {
    return {
      title: "Referral leaderboard preview",
      subtitle: "internal stand-only: активные рефералы без source identifiers",
      myPosition: 12,
      myScore: 9,
      myScoreUnit: "referrals",
      nextVisibleGoal: "Top 10",
      progressToGoal: 72,
      rows: referralRows,
      trend: [
        { id: "w1", label: "Нед. 1", value: 3 },
        { id: "w2", label: "Нед. 2", value: 5 },
        { id: "w3", label: "Нед. 3", value: 7 },
        { id: "w4", label: "Нед. 4", value: 9 },
      ],
      activity: [
        { id: "score", label: "Счёт", value: 1, tone: "success" },
        { id: "near", label: "Рядом", value: 1, tone: "info" },
        { id: "safe", label: "Privacy", value: 1, tone: "success" },
      ],
      ladder: [
        { id: "top100", label: "Top 100", complete: true },
        { id: "top50", label: "Top 50", complete: true },
        { id: "top10", label: "Top 10", active: true },
        { id: "top3", label: "Top 3" },
      ],
      segments: [
        { id: "score", label: "Счёт", value: 72, tone: "success" },
        { id: "focus", label: "Фокус", value: 64, tone: "info" },
        { id: "privacy", label: "Privacy", value: 100, tone: "warning" },
      ],
    };
  }

  const rows = scope === "near_me" ? kwhRows.slice(1) : kwhRows;
  return {
    title: scope === "near_me" ? "Near-me preview" : "kWh leaderboard preview",
    subtitle: "internal stand-only: leaderboard cards without Energy catalogue",
    myPosition: 7,
    myScore: 6840.2,
    myScoreUnit: "kWh",
    nextVisibleGoal: "Top 5",
    progressToGoal: scope === "near_me" ? 66 : 78,
    rows,
    trend: [
      { id: "w1", label: "Нед. 1", value: 5020 },
      { id: "w2", label: "Нед. 2", value: 5440 },
      { id: "w3", label: "Нед. 3", value: 6120 },
      { id: "w4", label: "Нед. 4", value: 6840 },
    ],
    activity: [
      { id: "score", label: "Счёт", value: 1, tone: "success" },
      { id: "near", label: "Рядом", value: 1, tone: "info" },
      { id: "safe", label: "Privacy", value: 1, tone: "success" },
      { id: "truth", label: "Truth", value: 1, tone: "warning" },
    ],
    ladder: [
      { id: "top100", label: "Top 100", complete: true },
      { id: "top50", label: "Top 50", complete: true },
      { id: "top10", label: "Top 10", complete: true },
      { id: "top5", label: "Top 5", active: true },
      { id: "top3", label: "Top 3" },
    ],
    segments: [
      { id: "score", label: "Счёт", value: 78, tone: "success" },
      { id: "focus", label: "Фокус", value: 66, tone: "info" },
      { id: "privacy", label: "Privacy", value: 100, tone: "warning" },
    ],
  };
}

function scoreLabel(row: RanksSandboxRow): string {
  return row.unit === "kWh"
    ? `${row.score.toLocaleString("ru-RU")} kWh`
    : `${row.score.toLocaleString("ru-RU")} реф.`;
}

function changeLabel(row: RanksSandboxRow): string {
  if (row.position <= 3) return "podium focus";
  if (row.isMe) return "my row highlighted";
  return "privacy-safe row";
}

function isRanksScope(value: string): value is RanksSandboxScope {
  return value === "kwh" || value === "referrals" || value === "near_me";
}

export function RanksDashboardSandboxPrototype(
  props: RanksDashboardSandboxPrototypeProps,
) {
  const [scope, setScope] = useState<RanksSandboxScope>(
    props.initialScope ?? "kwh",
  );
  const preview = useMemo(() => buildPreview(scope), [scope]);
  const changeScope = (next: string) => {
    if (isRanksScope(next)) setScope(next);
  };

  return (
    <SimDashboardShell
      eyebrow="EFHC Simulation"
      title="Ranks Dashboard screen draft"
      subtitle="internal stand-only leaderboard dashboard; no current mode truth claimed"
      contract={{
        id: "ranks-dashboard-sandbox-prototype-1474",
        mode: "simulation",
        title: "Ranks Dashboard internal stand screen draft",
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
      }}
    >
      <section
        className="efhc-ranks-dashboard-sandbox"
        data-ranks-dashboard-sandbox-prototype="1474"
        data-ranks-truth-model="synthetic_preview"
        data-ranks-no-raw-tg-id="true"
        data-ranks-no-energy-level-catalog="true"
      >
        <SimDashboardToolbar
          title={preview.title}
          subtitle={preview.subtitle}
          freshness={
            <SimFreshnessBadge
              freshness="unknown"
              label="generated preview"
            />
          }
          actions={
            <SimStatusPill
              label="No current mode page changed"
              tone="warning"
            />
          }
        >
          <SimLeaderboardScopeFilter
            label="Leaderboard scope"
            value={scope}
            options={scopeOptions}
            onChange={changeScope}
          />
        </SimDashboardToolbar>

        <SimDashboardGrid>
          <SimStatCard
            label="Моя позиция"
            value={`#${preview.myPosition}`}
            hint="Preview row highlight"
            tone="success"
          />
          <SimStatCard
            label="Мой счёт"
            value={`${preview.myScore.toLocaleString("ru-RU")} ${
              preview.myScoreUnit
            }`}
            hint="generated display only"
            tone="info"
          />
          <SimStatCard
            label="Ближайшая цель"
            value={preview.nextVisibleGoal}
            hint="Visible leaderboard milestone"
            tone="warning"
          />
        </SimDashboardGrid>

        <SimPanelChrome
          title="Rank hero"
          subtitle="Позиция, счёт и следующий видимый рубеж"
          status="success"
          statusLabel="preview"
          source="generated preview"
          tone="success"
        >
          <div className="efhc-ranks-dashboard-sandbox__hero">
            <div>
              <p>Current focus</p>
              <strong>#{preview.myPosition}</strong>
              <span>{preview.nextVisibleGoal}</span>
            </div>
            <SimProgressBar
              label="Прогресс до видимой цели"
              value={preview.progressToGoal}
              showValue
              tone="success"
            />
          </div>
        </SimPanelChrome>

        <SimDashboardSection
          title="Leaderboard cards"
          subtitle="Карточки показывают username, позицию и score без source identifiers"
        >
          <div className="efhc-ranks-dashboard-sandbox__leader-grid">
            {preview.rows.map((row) => (
              <article
                key={row.id}
                className={[
                  "efhc-ranks-dashboard-sandbox__leader-card",
                  row.isMe
                    ? "efhc-ranks-dashboard-sandbox__leader-card--me"
                    : "",
                ].join(" ")}
                data-ranks-leader-card="1474"
                data-ranks-leaderboard-synthetic="true"
                data-ranks-username-only="true"
              >
                <div className="efhc-ranks-dashboard-sandbox__leader-head">
                  <strong>#{row.position}</strong>
                  <div>
                    <b>{row.username}</b>
                    <span>{changeLabel(row)}</span>
                  </div>
                  <div className="efhc-ranks-dashboard-sandbox__badges">
                    <SimStatusPill
                      label={row.badge}
                      tone={row.isMe ? "success" : "info"}
                    />
                    {row.vip ? (
                      <SimStatusPill label="VIP" tone="warning" />
                    ) : null}
                  </div>
                </div>
                <div className="efhc-ranks-dashboard-sandbox__leader-body">
                  <strong>{scoreLabel(row)}</strong>
                  <SimMiniSparkline
                    label="score trend"
                    points={row.trend}
                    synthetic
                    tone={row.isMe ? "success" : "info"}
                  />
                </div>
              </article>
            ))}
          </div>
        </SimDashboardSection>

        <SimDashboardGrid>
          <SimPanelChrome
            title="Position ladder"
            subtitle="Видимые рубежи рейтинга без каталога Energy"
            status="success"
            statusLabel="safe"
            source="generated preview"
            tone="info"
          >
            <SimMilestoneProgress
              milestones={preview.ladder}
              source="display-only leaderboard milestones"
              dataKind="synthetic_preview"
              synthetic
            />
          </SimPanelChrome>

          <SimPanelChrome
            title="Score mix"
            subtitle="Мотивационная композиция без экономических boost"
            status="success"
            statusLabel="preview"
            source="generated preview"
            tone="neutral"
          >
            <SimSegmentedProgress
              segments={preview.segments}
              source="display-only score composition"
              dataKind="synthetic_preview"
              synthetic
            />
          </SimPanelChrome>
        </SimDashboardGrid>

        <SimDashboardGrid>
          <SimPanelChrome
            title="Trend preview"
            subtitle="Не real time-series; только internal stand shape"
            status="stale"
            statusLabel="preview"
            source="generated preview"
            tone="warning"
          >
            <SimMiniBarChart
              label="visible score movement"
              points={preview.trend}
              synthetic
              tone="success"
              unit={preview.myScoreUnit}
            />
          </SimPanelChrome>

          <SimPanelChrome
            title="Privacy / truth strip"
            subtitle="Preview показывает, какие safeguards нужны current mode"
            status="success"
            statusLabel="safe"
            source="internal stand reference"
            tone="success"
          >
            <SimActivityStrip
              label="safety states"
              points={preview.activity}
              synthetic
            />
          </SimPanelChrome>
        </SimDashboardGrid>
      </section>
    </SimDashboardShell>
  );
}

