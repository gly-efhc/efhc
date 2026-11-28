import Link from "next/link";
import React from "react";

import {
  FrontendCard,
  FrontendStatusBlock,
} from "../shell/FrontendShell";
import {
  cmp8,
  format8,
} from "../../lib/format";
import type { SyncSnapshot } from "../../services/snapshot.service";

type Labels = {
  mainBalance: string;
  bonusBalance: string;
  totalBalance: string;
  baseRate: string;
  effectiveRate: string;
  activePanels: string;
  energyStatus: string;
  active: string;
  inactive: string;
  nextAction: string;
  activatePanel: string;
  activatePanelNote: string;
  exchange: string;
  exchangeNote: string;
  panels: string;
  panelsNote: string;
  open: string;
  browserPreview: string;
  refreshing: string;
};

export function EnergyMvpSummary(props: {
  snap: SyncSnapshot;
  hideBalances: boolean;
  browserPreview: boolean;
  refreshing: boolean;
  labels: Labels;
}) {
  const profile = props.snap.profile;
  const activePanels = props.snap.panels.active_count;
  const availableKwh = profile.available_kwh;
  const nextAction = activePanels <= 0
    ? {
        href: "/panels",
        title: props.labels.activatePanel,
        icon: "☀",
      }
    : cmp8(availableKwh, "0") > 0
      ? {
          href: "/exchange",
          title: props.labels.exchange,
          icon: "↔",
        }
      : {
          href: "/panels",
          title: props.labels.panels,
          icon: "▦",
        };

  const hidden = "••••••••";
  const value = (raw: string) => props.hideBalances
    ? hidden
    : format8(raw);

  const metrics = [
    {
      key: "main-balance",
      label: props.labels.mainBalance,
      value: `${value(profile.main_balance)} EFHCm`,
    },
    {
      key: "bonus-balance",
      label: props.labels.bonusBalance,
      value: `${value(profile.bonus_balance)} EFHCb`,
    },
  ];

  return (
    <section
      className="efhc-energy-mvp-summary efhc-energy-mvp-summary--compact"
      data-energy-mvp-summary="compact-current"
      data-energy-summary-card-count="2"
      data-energy-summary-layout="compact-two-card"
      data-energy-snapshot-source={
        props.browserPreview ? "browser-preview" : "live"
      }
    >
      <div className="efhc-energy-summary-grid">
        {metrics.map((metric) => (
          <FrontendCard
            key={metric.key}
            className="efhc-energy-mini-card"
          >
            <span className="efhc-energy-mini-card_label">
              {metric.label}
            </span>
            <strong className="efhc-energy-mini-card_value tabular-nums">
              {metric.value}
            </strong>
          </FrontendCard>
        ))}
      </div>

      {props.browserPreview ? (
        <FrontendStatusBlock
          title={props.labels.browserPreview}
          tone="info"
        />
      ) : null}

      {props.refreshing ? (
        <div className="efhc-energy-refreshing" role="status">
          {props.labels.refreshing}
        </div>
      ) : null}

      <div className="efhc-energy-next-action">
        <Link
          href={nextAction.href}
          className="efhc-energy-action-card"
          data-energy-mobile-actions="aligned"
          data-first-screen-action-count="1"
        >
          <span className="efhc-energy-action-card_icon">
            {nextAction.icon}
          </span>
          <strong>{nextAction.title}</strong>
          <b>{props.labels.open}</b>
        </Link>
      </div>
    </section>
  );
}
