import React from "react";

import { AdminCharts } from "../AdminCharts";
import { AdminTable } from "../AdminTable";
import { AdminSectionCard } from "./AdminSectionCard";

type StatItem = {
  label: string;
  value: number;
};

type TableRow = {
  label: string;
  value: string;
};

type Props = {
  title: string;
  subtitle: string;
  stats: StatItem[];
  actions: React.ReactNode;
  rows: TableRow[];
};

export function AdminFunctionalPageTemplate(props: Props) {
  return (
    <div
      className="grid gap-4"
      data-admin-functional-template="stats-actions-table-1318"
    >
      <AdminCharts
        title={props.title}
        subtitle={props.subtitle}
        items={props.stats}
      />
      <AdminSectionCard
        title="Операторские действия"
        subtitle="Действия расположены ниже статистики."
      >
        {props.actions}
      </AdminSectionCard>
      <AdminTable title="Таблица раздела" rows={props.rows} />
    </div>
  );
}
