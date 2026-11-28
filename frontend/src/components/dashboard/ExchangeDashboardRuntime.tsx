import React, { useMemo, useState } from "react";

import { formatD8ToHuman, toScaledBigintDown } from "../../lib/format";
import {
  SimActivityStrip,
  SimDashboardGrid,
  SimDashboardToolbar,
  SimExchangeScopeFilter,
  SimFilterBar,
  SimFreshnessBadge,
  SimMiniBarChart,
  SimPanelChrome,
  SimProgressBar,
  SimStatCard,
  SimStatusPill,
} from "./SimulationDashboardUiKit";

type ExchangeWidgetScope = "summary" | "flow" | "rules";


export type ExchangeDashboardRuntimeLabels = {
  title: string;
  subtitle: string;
  fresh: string;
  loading: string;
  error: string;
  source: string;
  rawData: string;
  derivedDisplay: string;
  available: string;
  maxExchangeable: string;
  receive: string;
  mainBalance: string;
  rate: string;
  oneWay: string;
  noReverse: string;
  flowTitle: string;
  flowSubtitle: string;
  readinessTitle: string;
  readinessSubtitle: string;
  historyTitle: string;
  historySubtitle: string;
  historyCta: string;
  scopeLabel: string;
  scopeSummary: string;
  scopeFlow: string;
  scopeRules: string;
  reset: string;
  previewReady: string;
  previewLoading: string;
  previewError: string;
  convertBoundary: string;
  noFakeHistory: string;
};

type ExchangeDashboardRuntimeProps = {
  availableKwh: string;
  maxExchangeableKwh: string;
  mainBalance: string;
  rate: string;
  previewReady: boolean;
  loading?: boolean;
  error?: boolean;
  pending?: boolean;
  hideBalances?: boolean;
  updatedAt?: string | null;
  labels: ExchangeDashboardRuntimeLabels;
  onOpenHistory?: () => void;
};

function human(value: string, hidden?: boolean): string {
  if (hidden) return "••••••••";
  return formatD8ToHuman(value || "0");
}

function ratioPct(numerator: string, denominator: string): number {
  const num = toScaledBigintDown(numerator || "0", 8);
  const den = toScaledBigintDown(denominator || "0", 8);
  if (num <= 0n || den <= 0n) return 0;
  const capped = num > den ? den : num;
  return Number((capped * 100n) / den);
}

function positive(value: string): boolean {
  return toScaledBigintDown(value || "0", 8) > 0n;
}

export function ExchangeDashboardRuntime(
  props: ExchangeDashboardRuntimeProps,
) {
  const [scope, setScope] = useState<ExchangeWidgetScope>("summary");
  const maxPct = useMemo(
    () => ratioPct(props.maxExchangeableKwh, props.availableKwh),
    [props.availableKwh, props.maxExchangeableKwh],
  );
  const canExchange = positive(props.maxExchangeableKwh);
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
  const readinessLabel = props.error
    ? props.labels.previewError
    : props.previewReady
      ? props.labels.previewReady
      : props.labels.previewLoading;

  return (
    <section
      className="efhc-exchange-dashboard-runtime"
      data-dashboard-contract="exchange-dashboard-runtime"
      data-exchange-dashboard-runtime="1479"
      data-exchange-dashboard-rate="1-kwh-1-efhc"
      data-exchange-dashboard-one-way="kwh-to-efhc-only"
      data-exchange-dashboard-no-reverse="true"
      data-exchange-dashboard-no-write-bypass="true"
      data-exchange-dashboard-no-fake-history="true"
      data-exchange-dashboard-truth="raw-derived"
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
        onReset={() => setScope("summary")}
        resetLabel={props.labels.reset}
      >
        <SimExchangeScopeFilter
          label={props.labels.scopeLabel}
          onChange={(value) => setScope(value as ExchangeWidgetScope)}
          options={[
            { key: "summary", label: props.labels.scopeSummary },
            { key: "flow", label: props.labels.scopeFlow },
            { key: "rules", label: props.labels.scopeRules },
          ]}
          value={scope}
        />
      </SimFilterBar>

      <SimDashboardGrid>
        <SimStatCard
          hint={props.labels.rawData}
          label={props.labels.available}
          tone={canExchange ? "success" : "neutral"}
          value={`${human(props.availableKwh, props.hideBalances)} kWh`}
        />
        <SimStatCard
          hint={props.labels.rawData}
          label={props.labels.maxExchangeable}
          tone={canExchange ? "info" : "neutral"}
          value={`${human(props.maxExchangeableKwh, props.hideBalances)} kWh`}
        />
        <SimStatCard
          hint={props.labels.derivedDisplay}
          label={props.labels.receive}
          tone="success"
          value={`${human(props.maxExchangeableKwh, props.hideBalances)} EFHCm`}
        />
        <SimStatCard
          hint={props.labels.rawData}
          label={props.labels.mainBalance}
          tone="neutral"
          value={`${human(props.mainBalance, props.hideBalances)} EFHCm`}
        />
      </SimDashboardGrid>

      <SimDashboardGrid>
        <SimPanelChrome
          source={props.labels.source}
          status={panelStatus}
          statusLabel={statusLabel}
          subtitle={props.labels.flowSubtitle}
          title={props.labels.flowTitle}
          tone="info"
        >
          <div className="efhc-exchange-dashboard-runtime__flow">
            <span>kWh</span>
            <b aria-hidden="true">→</b>
            <span>EFHCm</span>
          </div>
          <SimProgressBar
            label={props.labels.maxExchangeable}
            showValue
            tone="success"
            value={maxPct}
          />
          <div className="efhc-exchange-dashboard-runtime__chips">
            <SimStatusPill label={props.labels.rate} tone="success" />
            <SimStatusPill label={props.labels.oneWay} tone="info" />
            <SimStatusPill label={props.labels.noReverse} tone="warning" />
          </div>
        </SimPanelChrome>

        <SimPanelChrome
          source={props.labels.source}
          status={panelStatus}
          statusLabel={readinessLabel}
          subtitle={props.labels.readinessSubtitle}
          title={props.labels.readinessTitle}
          tone={props.error ? "danger" : "success"}
        >
          <SimMiniBarChart
            dataKind="derived"
            label={props.labels.readinessTitle}
            points={[
              {
                id: "available",
                label: props.labels.available,
                value: positive(props.availableKwh) ? 1 : 0,
              },
              {
                id: "max-exchangeable",
                label: props.labels.maxExchangeable,
                value: canExchange ? 1 : 0,
              },
              {
                id: "preview-ready",
                label: props.labels.previewReady,
                value: props.previewReady ? 1 : 0,
              },
            ]}
            source={props.labels.derivedDisplay}
            synthetic={false}
          />
          <SimActivityStrip
            dataKind="derived"
            label={props.labels.convertBoundary}
            points={[
              { id: "raw", label: props.labels.rawData, value: 1 },
              { id: "one-way", label: props.labels.oneWay, value: 1 },
              { id: "no-reverse", label: props.labels.noReverse, value: 1 },
              { id: "no-fake-history", label: props.labels.noFakeHistory, value: 1 },
            ]}
            source={props.labels.derivedDisplay}
            synthetic={false}
          />
        </SimPanelChrome>
      </SimDashboardGrid>

      <SimPanelChrome
        source={props.labels.source}
        status={panelStatus}
        statusLabel={statusLabel}
        subtitle={props.labels.historySubtitle}
        title={props.labels.historyTitle}
        tone="neutral"
      >
        <div className="efhc-exchange-dashboard-runtime__history">
          <span>{props.labels.noFakeHistory}</span>
          <button
            type="button"
            className="efhc-exchange-dashboard-runtime__history-link"
            data-exchange-dashboard-history-link="account-history"
            onClick={props.onOpenHistory}
          >
            {props.labels.historyCta}
          </button>
        </div>
      </SimPanelChrome>
    </section>
  );
}
