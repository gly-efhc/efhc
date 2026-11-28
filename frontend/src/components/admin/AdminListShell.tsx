import React from "react";
import { AdminSectionCard } from "./AdminSectionCard";

export function AdminListShell(
  props: React.PropsWithChildren<{
    title: string;
    subtitle?: React.ReactNode;
    actions?: React.ReactNode;
  }>,
) {
  return (
    <AdminSectionCard title={props.title} subtitle={props.subtitle} actions={props.actions}>
      <div className="space-y-2">{props.children}</div>
    </AdminSectionCard>
  );
}
