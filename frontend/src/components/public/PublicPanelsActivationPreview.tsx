import React, { useMemo, useState } from "react";

import { formatD8ToHuman, toScaledBigintDown } from "../../lib/format";
import { hapticTap } from "../../lib/telegram";

type FocusMode = "activation" | "active" | "archive";

type PreviewPanel = {
  label: string;
  generated: string;
  remaining: string;
};

type Props = {
  activePanels: number | null;
  archivedPanels: number | null;
  totalActivationBalance: string;
  mainBalance: string;
  bonusBalance: string;
  effectiveRate: string | null;
  activeGeneration: string;
  canActivate: boolean;
  activating: boolean;
  hapticsEnabled: boolean;
  activePreview: PreviewPanel[];
  onActivate: () => void | Promise<void>;
  labels: {
    title: string;
    live: string;
    activation: string;
    active: string;
    archive: string;
    price: string;
    progress: string;
    ready: string;
    notReady: string;
    totalBalance: string;
    mainBalance: string;
    bonusBalance: string;
    debitOrder: string;
    activePanels: string;
    archivedPanels: string;
    effectiveRate: string;
    activeGeneration: string;
    previewTitle: string;
    generated: string;
    remaining: string;
    activateNow: string;
    needsMore: string;
    safeNote: string;
    emptyPreview: string;
  };
};

function pctToActivation(balance: string): number {
  const raw = toScaledBigintDown(balance || "0", 8);
  const safe = raw < 0n ? 0n : raw;
  const target = 100n * 100_000_000n;
  const capped = safe > target ? target : safe;
  return Number((capped * 100n) / target);
}

function maskedHuman(value: string): string {
  return `${formatD8ToHuman(value)} EFHC`;
}

export function PublicPanelsActivationPreview(props: Props) {
  const [focus, setFocus] = useState<FocusMode>("activation");
  const progressPct = useMemo(
    () => pctToActivation(props.totalActivationBalance),
    [props.totalActivationBalance],
  );

  const focusRows = useMemo(() => {
    if (focus === "active") {
      return [
        [props.labels.activePanels, String(props.activePanels ?? 0)],
        [props.labels.effectiveRate, props.effectiveRate ?? "—"],
        [props.labels.activeGeneration, props.activeGeneration],
      ];
    }
    if (focus === "archive") {
      return [
        [props.labels.archivedPanels, String(props.archivedPanels ?? 0)],
        [props.labels.generated, props.labels.previewTitle],
        [props.labels.remaining, props.labels.emptyPreview],
      ];
    }
    return [
      [props.labels.totalBalance, maskedHuman(props.totalActivationBalance)],
      [props.labels.mainBalance, maskedHuman(props.mainBalance)],
      [props.labels.bonusBalance, maskedHuman(props.bonusBalance)],
    ];
  }, [
    focus,
    props.activePanels,
    props.archivedPanels,
    props.bonusBalance,
    props.effectiveRate,
    props.labels,
    props.mainBalance,
    props.activeGeneration,
    props.totalActivationBalance,
  ]);

  const choose = (next: FocusMode) => {
    setFocus(next);
    hapticTap(props.hapticsEnabled);
  };

  const activate = () => {
    hapticTap(props.hapticsEnabled);
    void props.onActivate();
  };

  const tabs: Array<{ id: FocusMode; label: string; x: number }> = [
    { id: "activation", label: props.labels.activation, x: 18 },
    { id: "active", label: props.labels.active, x: 50 },
    { id: "archive", label: props.labels.archive, x: 82 },
  ];

  return (
    <section
      className={
        "efhc-public-panels-preview" +
        ` is-${focus}` +
        (props.canActivate ? " is-ready" : " is-locked")
      }
      data-public-visual-beauty="energy-panels-exchange"
      data-public-surface="panels"
      data-panel-activation-preview="100-efhc"
      data-public-ui-no-admin-internals="true"
      data-donor-patterns={
        "Telegram Mini App cells; DisplayData rows; " +
        "safe haptic activation intent"
      }
    >
      <div className="efhc-public-panels-preview_head">
        <div>
          <span className="efhc-public-panels-preview_eyebrow">
            {props.labels.live}
          </span>
          <h2>{props.labels.title}</h2>
        </div>
        <span
          className={
            "efhc-public-panels-preview_status" +
            (props.canActivate ? " is-ready" : "")
          }
        >
          {props.canActivate ? props.labels.ready : props.labels.notReady}
        </span>
      </div>

      <div
        className="efhc-public-panels-preview_visual-rail"
        aria-hidden="true"
      >
        {tabs.map((tab) => (
          <span
            key={`rail-${tab.id}`}
            className={
              "efhc-public-panels-preview_visual-chip" +
              (focus === tab.id ? " is-active" : "")
            }
          >
            {tab.label}
          </span>
        ))}
      </div>

      <div
        className="efhc-public-panels-preview_tabs"
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
              "efhc-public-panels-preview_tab" +
              (focus === tab.id ? " is-active" : "")
            }
            onClick={() => choose(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="efhc-public-panels-preview_flow">
        <svg viewBox="0 0 100 38" role="img" aria-hidden="true">
          <path
            d="M18 21 C28 7 40 7 50 21 S72 35 82 21"
            fill="none"
            stroke="rgba(244,210,122,.36)"
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
                  "efhc-public-panels-preview_dot" +
                  (focus === tab.id ? " is-active" : "")
                }
              />
            </g>
          ))}
        </svg>
      </div>

      <div className="efhc-public-panels-preview_activation">
        <div className="efhc-public-panels-preview_ring-wrap">
          <div
            className="efhc-public-panels-preview_ring"
            style={{
              "--panel-progress": `${progressPct}%`,
            } as React.CSSProperties}
          >
            <strong>{progressPct}%</strong>
            <span>{props.labels.progress}</span>
          </div>
        </div>
        <div className="efhc-public-panels-preview_price">
          <span>{props.labels.price}</span>
          <strong>100 EFHC</strong>
          <p>{props.labels.debitOrder}</p>
        </div>
      </div>

      <div
        className="efhc-public-panels-preview_facts"
        data-public-panels-display-data="true"
      >
        {focusRows.map(([label, value]) => (
          <div key={label} className="efhc-public-panels-preview_fact">
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>

      <div className="efhc-public-panels-preview_deck">
        <div className="efhc-public-panels-preview_deck-title">
          {props.labels.previewTitle}
        </div>
        {props.activePreview.length > 0 ? (
          props.activePreview.map((item) => (
            <div
              key={item.label}
              className="efhc-public-panels-preview_panel-row"
            >
              <strong>{item.label}</strong>
              <span>{item.generated}</span>
              <em>{item.remaining}</em>
            </div>
          ))
        ) : (
          <div className="efhc-public-panels-preview_empty">
            {props.labels.emptyPreview}
          </div>
        )}
      </div>

      <button
        type="button"
        className="efhc-public-panels-preview_cta"
        disabled={!props.canActivate || props.activating}
        onClick={activate}
      >
        <span>{props.labels.activation}</span>
        <strong>
          {props.canActivate
            ? props.labels.activateNow
            : props.labels.needsMore}
        </strong>
      </button>

      <p className="efhc-public-panels-preview_safe-note">
        {props.labels.safeNote}
      </p>
    </section>
  );
}
