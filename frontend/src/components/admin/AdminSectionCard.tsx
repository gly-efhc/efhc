import React from "react";

export function AdminSectionCard(
  props: React.PropsWithChildren<{
    title: string;
    subtitle?: React.ReactNode;
    actions?: React.ReactNode;
  }>,
) {
  return (
    <div className="efhc-admin-section-card rounded-3xl border border-[color:var(--tg-hint)]/20 bg-[var(--tg-secondary-bg)] p-4 shadow-sm" data-admin-primitive="section" data-eam-family="EAM-ADMIN-004">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-sm font-semibold">{props.title}</div>
          {props.subtitle ? (
            <div className="mt-1 text-xs text-[color:var(--tg-hint)]">
              {props.subtitle}
            </div>
          ) : null}
        </div>
        {props.actions ? <div className="shrink-0">{props.actions}</div> : null}
      </div>
      <div className="mt-4">{props.children}</div>
    </div>
  );
}
