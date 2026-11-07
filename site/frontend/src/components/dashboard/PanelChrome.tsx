import React from "react";

import type {
  DashboardComponentContract,
  DashboardPanelSize,
  DashboardPanelStatus,
  DashboardPanelTone,
} from "../../lib/dashboard/componentContract";

export type PanelChromeMode = "admin" | "simulation";

export type PanelChromeProps = React.PropsWithChildren<{
  mode: PanelChromeMode;
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  status?: DashboardPanelStatus;
  statusLabel?: React.ReactNode;
  tone?: DashboardPanelTone;
  size?: DashboardPanelSize;
  updatedAt?: React.ReactNode;
  source?: React.ReactNode;
  actions?: React.ReactNode;
  footer?: React.ReactNode;
  contract?: DashboardComponentContract;
  className?: string;
  bodyClassName?: string;
  dataMarker?: string;
}>;

const toneClass: Record<DashboardPanelTone, string> = {
  neutral: "efhc-panel-chrome--neutral",
  info: "efhc-panel-chrome--info",
  success: "efhc-panel-chrome--success",
  warning: "efhc-panel-chrome--warning",
  danger: "efhc-panel-chrome--danger",
};

function statusClass(status: DashboardPanelStatus | undefined): string {
  if (status === "loading") return "is-loading";
  if (status === "empty") return "is-empty";
  if (status === "error") return "is-error";
  if (status === "stale") return "is-stale";
  return "is-success";
}

function statusText(status: DashboardPanelStatus): string {
  if (status === "loading") return "loading";
  if (status === "empty") return "empty";
  if (status === "error") return "error";
  if (status === "stale") return "stale";
  return "success";
}

export function PanelChrome(props: PanelChromeProps) {
  const tone = props.tone ?? props.contract?.tone ?? "neutral";
  const size = props.size ?? props.contract?.size ?? "normal";
  const status = props.status ?? props.contract?.state.status ?? "success";
  const contractId = props.contract?.id ?? `${props.mode}-panel-chrome`;
  const className = [
    "efhc-panel-chrome",
    `efhc-panel-chrome--${props.mode}`,
    `efhc-panel-chrome--${size}`,
    toneClass[tone],
    props.className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <section
      className={className}
      data-dashboard-panel-chrome="1462"
      data-dashboard-mode={props.mode}
      data-dashboard-contract={contractId}
      data-dashboard-data-kind={props.contract?.source.dataKind ?? "raw"}
      data-panel-status={status}
      data-panel-synthetic={
        props.contract?.source.synthetic ? "true" : "false"
      }
      data-panel-marker={props.dataMarker ?? "panel-chrome"}
      aria-label={props.contract?.ariaLabel}
    >
      <header className="efhc-panel-chrome__header">
        <div className="efhc-panel-chrome__title-block">
          <h3>{props.title}</h3>
          {props.subtitle ? <p>{props.subtitle}</p> : null}
        </div>
        <div className="efhc-panel-chrome__meta">
          <span className={`efhc-panel-chrome__status ${statusClass(status)}`}>
            {props.statusLabel ?? statusText(status)}
          </span>
          {props.actions ? (
            <div className="efhc-panel-chrome__actions">
              {props.actions}
            </div>
          ) : null}
        </div>
      </header>
      <div className={props.bodyClassName ?? "efhc-panel-chrome__body"}>
        {props.children}
      </div>
      {props.footer || props.updatedAt ? (
        <footer className="efhc-panel-chrome__footer">
          {props.footer}
          {props.updatedAt ? <span>{props.updatedAt}</span> : null}
        </footer>
      ) : null}
    </section>
  );
}

