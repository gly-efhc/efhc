import React, { useMemo, useState } from "react";

import { formatD8ToHuman, toScaledBigintDown } from "../../lib/format";
import { hapticTap } from "../../lib/telegram";

type FocusMode = "available" | "preview" | "confirm";

type Props = {
  availableKwh: string;
  maxExchangeableKwh: string;
  mainBalance: string;
  rate: string;
  previewReady: boolean;
  pending: boolean;
  hideBalances: boolean;
  hapticsEnabled: boolean;
  onFocusForm: () => void;
  labels: {
    title: string;
    live: string;
    available: string;
    preview: string;
    confirm: string;
    oneWay: string;
    availableHint: string;
    previewHint: string;
    confirmHint: string;
    maxAmount: string;
    rate: string;
    receive: string;
    balance: string;
    formCta: string;
    pending: string;
    safeNote: string;
    ready: string;
    loading: string;
  };
};

function human(value: string, hidden: boolean): string {
  if (hidden) return "••••••••";
  return formatD8ToHuman(value || "0");
}

function progressToMax(available: string): number {
  const raw = toScaledBigintDown(available || "0", 8);
  const safe = raw < 0n ? 0n : raw;
  const target = 100n * 100_000_000n;
  const capped = safe > target ? target : safe;
  return Number((capped * 100n) / target);
}

export function PublicExchangeInteractivePreview(props: Props) {
  const [focus, setFocus] = useState<FocusMode>("available");
  const progressPct = useMemo(
    () => progressToMax(props.maxExchangeableKwh),
    [props.maxExchangeableKwh],
  );

  const choose = (next: FocusMode) => {
    setFocus(next);
    hapticTap(props.hapticsEnabled);
  };

  const focusRows = useMemo(() => {
    if (focus === "preview") {
      return [
        [props.labels.maxAmount, human(props.maxExchangeableKwh, props.hideBalances) + " kWh"],
        [props.labels.receive, human(props.maxExchangeableKwh, props.hideBalances) + " EFHCm"],
        [props.labels.rate, props.rate || "1"],
      ];
    }
    if (focus === "confirm") {
      return [
        [props.labels.oneWay, "kWh → EFHCm"],
        [props.labels.ready, props.previewReady ? props.labels.ready : props.labels.loading],
        [props.labels.balance, human(props.mainBalance, props.hideBalances) + " EFHCm"],
      ];
    }
    return [
      [props.labels.available, human(props.availableKwh, props.hideBalances) + " kWh"],
      [props.labels.maxAmount, human(props.maxExchangeableKwh, props.hideBalances) + " kWh"],
      [props.labels.rate, "1 kWh = 1 EFHCm"],
    ];
  }, [
    focus,
    props.availableKwh,
    props.hideBalances,
    props.labels,
    props.mainBalance,
    props.maxExchangeableKwh,
    props.previewReady,
    props.rate,
  ]);

  const focusHint = useMemo(() => {
    if (focus === "preview") return props.labels.previewHint;
    if (focus === "confirm") return props.labels.confirmHint;
    return props.labels.availableHint;
  }, [focus, props.labels]);

  const tabs: Array<{ id: FocusMode; label: string; x: number }> = [
    { id: "available", label: props.labels.available, x: 18 },
    { id: "preview", label: props.labels.preview, x: 50 },
    { id: "confirm", label: props.labels.confirm, x: 82 },
  ];

  return (
    <section
      className={
        "efhc-public-exchange-preview" +
        ` is-${focus}` +
        (props.previewReady ? " is-ready" : " is-loading")
      }
      data-public-visual-beauty="energy-panels-exchange"
      data-public-surface="exchange"
      data-public-exchange-boundary="kwh-to-efhc-only"
      data-public-ui-no-admin-internals="true"
      data-donor-patterns={
        "Telegram Mini App cells; DisplayData rows; " +
        "safe MainButton intent without source data"
      }
    >
      <div className="efhc-public-exchange-preview_head">
        <div>
          <span className="efhc-public-exchange-preview_eyebrow">
            {props.labels.live}
          </span>
          <h2>{props.labels.title}</h2>
        </div>
        <span
          className={
            "efhc-public-exchange-preview_status" +
            (props.previewReady ? " is-ready" : "")
          }
        >
          {props.previewReady ? props.labels.ready : props.labels.loading}
        </span>
      </div>

      <div
        className="efhc-public-exchange-preview_visual-rail"
        aria-hidden="true"
      >
        {tabs.map((tab) => (
          <span
            key={`rail-${tab.id}`}
            className={
              "efhc-public-exchange-preview_visual-chip" +
              (focus === tab.id ? " is-active" : "")
            }
          >
            {tab.label}
          </span>
        ))}
      </div>

      <div
        className="efhc-public-exchange-preview_tabs"
        role="tablist"
        aria-label={props.labels.title}
      >
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={focus === tab.id}
            className={
              "efhc-public-exchange-preview_tab" +
              (focus === tab.id ? " is-active" : "")
            }
            onClick={() => choose(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="efhc-public-exchange-preview_flow">
        <svg viewBox="0 0 100 38" role="img" aria-hidden="true">
          <path
            d="M18 21 C30 8 40 8 50 21 S70 34 82 21"
            fill="none"
            stroke="rgba(56,189,248,.42)"
            strokeLinecap="round"
            strokeWidth="2.2"
          />
          {tabs.map((tab) => (
            <g key={tab.id}>
              <circle
                cx={tab.x}
                cy="21"
                r={focus === tab.id ? 5.8 : 4.2}
                className={
                  "efhc-public-exchange-preview_dot" +
                  (focus === tab.id ? " is-active" : "")
                }
              />
            </g>
          ))}
        </svg>
      </div>

      <div className="efhc-public-exchange-preview_meter-row">
        <div
          className="efhc-public-exchange-preview_meter"
          style={{
            "--exchange-progress": `${progressPct}%`,
          } as React.CSSProperties}
        >
          <span />
        </div>
        <strong>{progressPct}%</strong>
      </div>

      <p className="efhc-public-exchange-preview_hint">{focusHint}</p>

      <div
        className="efhc-public-exchange-preview_facts"
        data-public-exchange-display-data="true"
      >
        {focusRows.map(([label, value]) => (
          <div key={label} className="efhc-public-exchange-preview_fact">
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>

      <button
        type="button"
        className="efhc-public-exchange-preview_cta"
        disabled={props.pending}
        onClick={() => {
          hapticTap(props.hapticsEnabled);
          props.onFocusForm();
        }}
      >
        <span>{props.labels.preview}</span>
        <strong>
          {props.pending ? props.labels.pending : props.labels.formCta}
        </strong>
      </button>

      <p className="efhc-public-exchange-preview_safe-note">
        {props.labels.safeNote}
      </p>
    </section>
  );
}
