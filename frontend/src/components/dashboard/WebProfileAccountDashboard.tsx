import React from "react";

import {
  SimActivityStrip,
  SimDashboardGrid,
  SimDashboardToolbar,
  SimFreshnessBadge,
  SimPanelChrome,
  SimProgressBar,
  SimStatCard,
  SimStatusPill,
} from "./SimulationDashboardUiKit";


export type WebProfileAccountDashboardLabels = {
  title: string;
  subtitle: string;
  fresh: string;
  source: string;
  rawData: string;
  derivedDisplay: string;
  totalBalance: string;
  mainBalance: string;
  bonusBalance: string;
  activePanels: string;
  accountStatusTitle: string;
  accountStatusSubtitle: string;
  walletTitle: string;
  walletSubtitle: string;
  historyTitle: string;
  historySubtitle: string;
  quickLinksTitle: string;
  quickLinksSubtitle: string;
  walletCount: string;
  walletConnected: string;
  walletNotConnected: string;
  primaryWallet: string;
  historyItems: string;
  withdrawRequests: string;
  latestWithdraw: string;
  profileLink: string;
  walletLink: string;
  historyLink: string;
  faqLink: string;
  vipActive: string;
  vipInactive: string;
  activeUser: string;
  inactiveUser: string;
  noRawPayload: string;
  noDebugPayload: string;
  accountDashboardBoundary: string;
};

export type WebProfileAccountDashboardProps = {
  username: string;
  level: number;
  totalBalance: string;
  mainBalance: string;
  bonusBalance: string;
  hideBalances?: boolean;
  isVip: boolean;
  isActive: boolean;
  walletCount: number;
  walletConnected: boolean;
  primaryWallet: string | null;
  historyCount: number;
  withdrawCount: number;
  latestWithdrawStatus: string | null;
  activePanels: number;
  updatedAt?: string | null;
  labels: WebProfileAccountDashboardLabels;
  onOpenProfile: () => void;
  onOpenWallet: () => void;
  onOpenHistory: () => void;
  onOpenFaq: () => void;
};

function masked(value: string, hidden?: boolean): string {
  if (hidden) return "••••••••";
  return value || "0";
}

function shortAddress(address: string | null): string {
  if (!address) return "—";
  if (address.length <= 18) return address;
  return `${address.slice(0, 8)}…${address.slice(-8)}`;
}

function accountProgress(props: WebProfileAccountDashboardProps): number {
  const parts = [
    Boolean(props.username),
    props.walletConnected,
    props.isActive,
    props.historyCount > 0 || props.withdrawCount > 0,
  ];
  const done = parts.filter(Boolean).length;
  return Math.round((done / parts.length) * 100);
}

function QuickLink(props: {
  label: string;
  onClick: () => void;
  marker: string;
}) {
  return (
    <button
      className="efhc-web-profile-dashboard__quick-link"
      data-web-profile-dashboard-quick-link={props.marker}
      onClick={props.onClick}
      type="button"
    >
      {props.label}
    </button>
  );
}

export function WebProfileAccountDashboard(
  props: WebProfileAccountDashboardProps,
) {
  const progress = accountProgress(props);
  const vipLabel = props.isVip
    ? props.labels.vipActive
    : props.labels.vipInactive;
  const activeLabel = props.isActive
    ? props.labels.activeUser
    : props.labels.inactiveUser;
  const walletLabel = props.walletConnected
    ? props.labels.walletConnected
    : props.labels.walletNotConnected;
  const latestWithdraw = props.latestWithdrawStatus || "—";

  return (
    <section
      className="efhc-web-profile-dashboard"
      data-dashboard-contract="web-profile-account-dashboard"
      data-web-profile-account-dashboard="1480"
      data-web-profile-dashboard-truth="raw-derived"
      data-web-profile-dashboard-no-write-actions="true"
      data-web-profile-dashboard-no-raw-payload="true"
      data-web-profile-dashboard-no-debug-payload="true"
    >
      <SimDashboardToolbar
        freshness={<SimFreshnessBadge freshness="fresh" label={props.labels.fresh} />}
        subtitle={props.labels.subtitle}
        title={props.labels.title}
        updatedAt={props.updatedAt ?? props.labels.source}
      />

      <SimDashboardGrid>
        <SimStatCard
          hint={props.labels.rawData}
          label={props.labels.totalBalance}
          tone="success"
          value={`${masked(props.totalBalance, props.hideBalances)} EFHC`}
        />
        <SimStatCard
          hint={props.labels.rawData}
          label={props.labels.mainBalance}
          tone="info"
          value={`${masked(props.mainBalance, props.hideBalances)} EFHCm`}
        />
        <SimStatCard
          hint={props.labels.rawData}
          label={props.labels.bonusBalance}
          tone="warning"
          value={`${masked(props.bonusBalance, props.hideBalances)} EFHCb`}
        />
        <SimStatCard
          hint={props.labels.rawData}
          label={props.labels.activePanels}
          tone={props.activePanels > 0 ? "success" : "neutral"}
          value={props.activePanels}
        />
      </SimDashboardGrid>

      <SimDashboardGrid>
        <SimPanelChrome
          source={props.labels.source}
          status="success"
          statusLabel={props.labels.fresh}
          subtitle={props.labels.accountStatusSubtitle}
          title={props.labels.accountStatusTitle}
          tone="info"
        >
          <div className="efhc-web-profile-dashboard__identity">
            <div>
              <span>{props.username}</span>
              <strong><span data-i18n-fixed-token="Lvl">Lvl</span> {props.level}</strong>
            </div>
            <div className="efhc-web-profile-dashboard__chips">
              <SimStatusPill label={vipLabel} tone={props.isVip ? "success" : "neutral"} />
              <SimStatusPill
                label={activeLabel}
                tone={props.isActive ? "success" : "warning"}
              />
            </div>
          </div>
          <SimProgressBar
            label={props.labels.derivedDisplay}
            showValue
            tone="success"
            value={progress}
          />
          <SimActivityStrip
            label={props.labels.accountDashboardBoundary}
            points={[
              { id: "profile", label: props.labels.profileLink, tone: "success", value: 1 },
              {
                id: "wallet",
                label: props.labels.walletLink,
                tone: props.walletConnected ? "success" : "warning",
                value: props.walletConnected ? 1 : 0,
              },
              {
                id: "history",
                label: props.labels.historyLink,
                tone: props.historyCount > 0 ? "info" : "neutral",
                value: props.historyCount > 0 ? 1 : 0,
              },
              { id: "faq", label: props.labels.faqLink, tone: "info", value: 1 },
            ]}
          />
        </SimPanelChrome>

        <SimPanelChrome
          source={props.labels.source}
          status="success"
          statusLabel={walletLabel}
          subtitle={props.labels.walletSubtitle}
          title={props.labels.walletTitle}
          tone={props.walletConnected ? "success" : "warning"}
        >
          <div className="efhc-web-profile-dashboard__metric-row">
            <span>{props.labels.walletCount}</span>
            <strong>{props.walletCount}</strong>
          </div>
          <div className="efhc-web-profile-dashboard__metric-row">
            <span>{props.labels.primaryWallet}</span>
            <strong>{shortAddress(props.primaryWallet)}</strong>
          </div>
          <div className="efhc-web-profile-dashboard__safe-note">
            {props.labels.noRawPayload}
          </div>
        </SimPanelChrome>

        <SimPanelChrome
          source={props.labels.source}
          status="success"
          statusLabel={props.labels.fresh}
          subtitle={props.labels.historySubtitle}
          title={props.labels.historyTitle}
          tone="neutral"
        >
          <div className="efhc-web-profile-dashboard__metric-row">
            <span>{props.labels.historyItems}</span>
            <strong>{props.historyCount}</strong>
          </div>
          <div className="efhc-web-profile-dashboard__metric-row">
            <span>{props.labels.withdrawRequests}</span>
            <strong>{props.withdrawCount}</strong>
          </div>
          <div className="efhc-web-profile-dashboard__metric-row">
            <span>{props.labels.latestWithdraw}</span>
            <strong>{latestWithdraw}</strong>
          </div>
          <div className="efhc-web-profile-dashboard__safe-note">
            {props.labels.noDebugPayload}
          </div>
        </SimPanelChrome>

        <SimPanelChrome
          source={props.labels.source}
          status="success"
          statusLabel={props.labels.fresh}
          subtitle={props.labels.quickLinksSubtitle}
          title={props.labels.quickLinksTitle}
          tone="success"
        >
          <div className="efhc-web-profile-dashboard__quick-links">
            <QuickLink
              label={props.labels.profileLink}
              marker="profile"
              onClick={props.onOpenProfile}
            />
            <QuickLink
              label={props.labels.walletLink}
              marker="wallet"
              onClick={props.onOpenWallet}
            />
            <QuickLink
              label={props.labels.historyLink}
              marker="history"
              onClick={props.onOpenHistory}
            />
            <QuickLink
              label={props.labels.faqLink}
              marker="faq"
              onClick={props.onOpenFaq}
            />
          </div>
        </SimPanelChrome>
      </SimDashboardGrid>
    </section>
  );
}
