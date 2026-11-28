import React from "react";

export function AdminHeroPanel(
  props: React.PropsWithChildren<{
    eyebrow?: string;
    title: string;
    subtitle?: React.ReactNode;
    badges?: React.ReactNode;
    actions?: React.ReactNode;
  }>,
) {
  return (
    <div className="rounded-3xl border border-[color:var(--tg-link)]/15 bg-[var(--tg-secondary-bg)] p-5 shadow-sm">
      {props.eyebrow ? (
        <div className="text-xs uppercase tracking-wide text-[color:var(--tg-hint)]">
          {props.eyebrow}
        </div>
      ) : null}
      <div className="mt-2 text-2xl font-semibold">{props.title}</div>
      {props.subtitle ? (
        <div className="mt-2 text-sm text-[color:var(--tg-hint)]">
          {props.subtitle}
        </div>
      ) : null}
      {props.badges ? (
        <div className="mt-3 flex flex-wrap gap-2">{props.badges}</div>
      ) : null}
      {props.actions ? (
        <div className="mt-4 flex flex-wrap gap-2">{props.actions}</div>
      ) : null}
      {props.children ? <div className="mt-4">{props.children}</div> : null}
    </div>
  );
}
