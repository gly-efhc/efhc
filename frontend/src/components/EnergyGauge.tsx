import React from "react";
import { useT } from "../hooks/useT";
import { Card } from "./ui/Card";

export function EnergyGauge(
  props: { availableKwh: string; totalKwh: string },
) {
  const t = useT();
  return (
    <Card title={t("energy.gauge_title")}>
      <div className="mt-2 text-sm text-zinc-400">
        {t("energy.total_label")}
      </div>
      <div className="text-2xl font-bold">{props.availableKwh}</div>
      <div className="mt-2 text-sm text-zinc-400">
        {t("energy.total_label")}
      </div>
      <div className="text-xl">{props.totalKwh}</div>
    </Card>
  );
}
