import React from "react";
import { Card } from "./ui/Card";

type Item = {
  label: string;
  value: string | number;
  tone?: "neutral" | "success" | "warning";
};

type Props = {
  title?: string;
  subtitle?: string;
  items: Item[];
};

function normalizeValue(value: string | number): number {
  if (typeof value === "number") return Math.abs(value);
  const parsed = Number(String(value).replace(/,/g, "."));
  return Number.isFinite(parsed) ? Math.abs(parsed) : 0;
}

export function AdminCharts(props: Props) {
  const max = Math.max(...props.items.map((item) => normalizeValue(item.value)), 1);
  return (
    <Card title={props.title || "Графики админки"}>
      {props.subtitle ? (
        <div className="mb-3 text-xs efhc-text-muted2">{props.subtitle}</div>
      ) : null}
      <div className="space-y-3">
        {props.items.map((item) => {
          const width = `${Math.max(8, Math.round((normalizeValue(item.value) / max) * 100))}%`;
          const toneClass =
            item.tone === "success"
              ? "bg-emerald-500/25"
              : item.tone === "warning"
                ? "bg-amber-500/25"
                : "bg-[color:var(--tg-link-color)]/20";
          return (
            <div key={item.label} className="rounded-2xl border border-[color:var(--tg-hint)] p-3">
              <div className="flex items-center justify-between gap-3">
                <div className="text-xs efhc-text-muted2">{item.label}</div>
                <div className="text-base font-semibold">{item.value}</div>
              </div>
              <div className="mt-2 h-2 overflow-hidden rounded-full bg-[color:var(--tg-secondary-bg)]">
                <div className={`h-full rounded-full ${toneClass}`} style={{ width }} />
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}
