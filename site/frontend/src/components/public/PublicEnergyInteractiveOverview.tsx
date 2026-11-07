import Link from "next/link";
import React, { useMemo, useState } from "react";

import type { SyncSnapshot } from "../../hooks/useSnapshot";
import { format8 } from "../../lib/format";
import { hapticTap } from "../../lib/telegram";

type FocusMode = "overview" | "panels" | "exchange";

type Props = {
  snap: SyncSnapshot | null;
  hideBalances: boolean;
  hapticsEnabled: boolean;
  labels: {
    title: string;
    live: string;
    overview: string;
    panels: string;
    exchange: string;
    available: string;
    total: string;
    rate: string;
    activePanels: string;
    exchanged: string;
    nextAction: string;
    open: string;
    safeNote: string;
    panelsHint: string;
    exchangeHint: string;
    overviewHint: string;
  };
};

function safeText(
  value: string | number | null | undefined,
  hidden: boolean,
): string {
  if (hidden) return "••••••••";
  if (value === null || value === undefined) return "0";
  return String(value || "0");
}

function human(
  value: string | number | null | undefined,
  hidden: boolean,
): string {
  if (hidden) return "••••••••";
  return format8(value ?? "0");
}

export function PublicEnergyInteractiveOverview(props: Props) {
  const [focus, setFocus] = useState<FocusMode>("overview");
  const profile = props.snap?.profile;
  const panels = props.snap?.panels;
  const meta = props.snap?.meta;

  const available = human(profile?.available_kwh, props.hideBalances);
  const total = human(
    (profile as any)?.lifetime_generated_kwh || profile?.total_generated_kwh,
    props.hideBalances,
  );
  const rate = human(meta?.gen_per_sec_effective, props.hideBalances);
  const exchanged = human(
    props.snap?.exchange_preview?.max_exchangeable_kwh,
    props.hideBalances,
  );

  const activePanels = safeText(panels?.active_count, false);
  const archivedPanels = safeText((panels as any)?.archived_count, false);

  const selected = useMemo(() => {
    if (focus === "panels") {
      return {
        title: props.labels.panels,
        href: "/panels",
        icon: "☀",
        hint: props.labels.panelsHint,
        rows: [
          [props.labels.activePanels, activePanels],
          ["Archive", archivedPanels],
          [props.labels.rate, `${rate} kWh/с`],
        ],
      };
    }
    if (focus === "exchange") {
      return {
        title: props.labels.exchange,
        href: "/exchange",
        icon: "↔",
        hint: props.labels.exchangeHint,
        rows: [
          [props.labels.available, `${available} kWh`],
          [props.labels.exchanged, `${exchanged} kWh`],
        ],
      };
    }
    return {
      title: props.labels.overview,
      href: "/panels",
      icon: "⚡",
      hint: props.labels.overviewHint,
      rows: [
        [props.labels.total, `${total} kWh`],
        [props.labels.available, `${available} kWh`],
        [props.labels.rate, `${rate} kWh/с`],
      ],
    };
  }, [
    activePanels,
    archivedPanels,
    available,
    exchanged,
    focus,
    props.labels,
    rate,
    total,
  ]);

  const choose = (next: FocusMode) => {
    setFocus(next);
    hapticTap(props.hapticsEnabled);
  };

  const nodes: Array<{ id: FocusMode; label: string; x: number }> = [
    { id: "overview", label: props.labels.overview, x: 18 },
    { id: "panels", label: props.labels.panels, x: 50 },
    { id: "exchange", label: props.labels.exchange, x: 82 },
  ];

  return (
    <section
      className={`efhc-public-energy-interactive is-${focus}`}
      data-public-visual-beauty="energy-panels-exchange"
      data-public-surface="energy"
      data-public-ui-no-admin-internals="true"
      data-donor-patterns={
        "DisplayData rows; Haptic feedback wrapper; " +
        "Telegram Theme / Viewport CSS vars"
      }
    >
      <div className="efhc-public-energy-interactive_head">
        <div>
          <span className="efhc-public-energy-interactive_eyebrow">
            {props.labels.live}
          </span>
          <h2>{props.labels.title}</h2>
        </div>
        <span className="efhc-public-energy-interactive_pulse" />
      </div>

      <div
        className="efhc-public-energy-interactive_visual-rail"
        aria-hidden="true"
      >
        {nodes.map((node) => (
          <span
            key={`rail-${node.id}`}
            className={
              "efhc-public-energy-interactive_visual-chip" +
              (focus === node.id ? " is-active" : "")
            }
          >
            {node.label}
          </span>
        ))}
      </div>

      <div
        className="efhc-public-energy-interactive_tabs"
        role="tablist"
        aria-label={props.labels.title}
      >
        {nodes.map((node) => (
          <button
            key={node.id}
            type="button"
            role="tab"
            aria-selected={focus === node.id}
            className={
              "efhc-public-energy-interactive_tab" +
              (focus === node.id ? " is-active" : "")
            }
            onClick={() => choose(node.id)}
          >
            {node.label}
          </button>
        ))}
      </div>

      <div className="efhc-public-energy-interactive_flow">
        <svg viewBox="0 0 100 36" role="img" aria-hidden="true">
          <path
            d="M18 18 C32 5 38 31 50 18 S68 5 82 18"
            fill="none"
            stroke="rgba(244,210,122,.38)"
            strokeWidth="2.2"
            strokeLinecap="round"
          />
          {nodes.map((node) => (
            <g key={node.id}>
              <circle
                cx={node.x}
                cy="18"
                r={focus === node.id ? 5.8 : 4.2}
                className={
                  "efhc-public-energy-interactive_dot" +
                  (focus === node.id ? " is-active" : "")
                }
              />
            </g>
          ))}
        </svg>
      </div>

      <div className="efhc-public-energy-interactive_selected">
        <div className="efhc-public-energy-interactive_selected-top">
          <span>{selected.icon}</span>
          <div>
            <strong>{selected.title}</strong>
            <p>{selected.hint}</p>
          </div>
        </div>

        <div
          className="efhc-public-energy-interactive_facts"
          data-public-energy-display-data="true"
        >
          {selected.rows.map(([label, value]) => (
            <div key={label} className="efhc-public-energy-interactive_fact">
              <span>{label}</span>
              <strong>{value}</strong>
            </div>
          ))}
        </div>

        <Link
          href={selected.href}
          className="efhc-public-energy-interactive_cta"
          onClick={() => hapticTap(props.hapticsEnabled)}
        >
          <span>{props.labels.nextAction}</span>
          <strong>{props.labels.open}</strong>
        </Link>
      </div>

      <p className="efhc-public-energy-interactive_safe-note">
        {props.labels.safeNote}
      </p>
    </section>
  );
}
