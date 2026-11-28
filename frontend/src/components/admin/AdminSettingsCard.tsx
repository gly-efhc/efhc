import React from "react";
import { AdminSectionCard } from "./AdminSectionCard";

export function AdminSettingsCard(
  props: React.PropsWithChildren<{
    title: string;
    subtitle?: React.ReactNode;
    statusLabel?: React.ReactNode;
  }>,
) {
  return (
    <AdminSectionCard
      title={props.title}
      subtitle={props.subtitle}
      actions={props.statusLabel ? <div className="text-xs text-[color:var(--tg-hint)]">{props.statusLabel}</div> : null}
    >
      <div className="space-y-3">{props.children}</div>
    </AdminSectionCard>
  );
}
