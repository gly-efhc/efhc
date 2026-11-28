import React from "react";
import { Card } from "./ui/Card";

type Row = {
  label: string;
  value: string;
};

type Props = {
  title?: string;
  rows: Row[];
};

export function AdminTable(props: Props) {
  return (
    <Card title={props.title || "Таблица админки"}>
      <div className="space-y-2">
        {props.rows.map((row) => (
          <div
            key={row.label}
            className="flex items-center justify-between gap-3 rounded-2xl border border-[color:var(--tg-hint)] p-3"
          >
            <div className="text-sm efhc-text-muted2">{row.label}</div>
            <div className="text-sm font-semibold">{row.value}</div>
          </div>
        ))}
      </div>
    </Card>
  );
}
