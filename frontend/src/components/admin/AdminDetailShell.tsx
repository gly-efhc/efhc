import React from "react";
import { AdminSectionCard } from "./AdminSectionCard";

export function AdminDetailShell(
  props: React.PropsWithChildren<{
    title: string;
    subtitle?: React.ReactNode;
    actions?: React.ReactNode;
  }>,
) {
  return (
    <AdminSectionCard title={props.title} subtitle={props.subtitle} actions={props.actions}>
      <div className="space-y-3">{props.children}</div>
    </AdminSectionCard>
  );
}
