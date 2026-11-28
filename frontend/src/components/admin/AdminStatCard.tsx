import React from "react";

export function AdminStatCard(props: {
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
  icon?: React.ReactNode;
  meta?: React.ReactNode;
  tone?: "default" | "success" | "warning" | "neutral" | "danger";
}) {
  const toneClass = {
    success: "border-emerald-500/20",
    danger: "border-red-500/25",
    warning: "border-amber-500/20",
    neutral: "border-[color:var(--tg-hint)]/15",
    default: "border-[color:var(--tg-hint)]/20",
  }[props.tone ?? "default"];
  return (
    <div className={`efhc-admin-stat-card rounded-2xl border ${toneClass} bg-[var(--tg-secondary-bg)] px-4 py-3`} data-admin-primitive="kpi" data-admin-tone={props.tone ?? "default"} data-eam-family="EAM-ADMIN-005">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-xs uppercase tracking-wide text-[color:var(--tg-hint)]">
            {props.label}
          </div>
          <div className="mt-2 text-2xl font-semibold leading-none">
            {props.value}
          </div>
          {props.meta ? (
            <div className="mt-2 text-[11px] font-medium text-[color:var(--tg-text)]/80">
              {props.meta}
            </div>
          ) : null}
          {props.hint ? (
            <div className="mt-1 text-xs text-[color:var(--tg-hint)]">
              {props.hint}
            </div>
          ) : null}
        </div>
        {props.icon ? <div className="shrink-0">{props.icon}</div> : null}
      </div>
    </div>
  );
}
