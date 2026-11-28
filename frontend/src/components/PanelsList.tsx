import React from "react";
import { Card } from "./ui/Card";
import { useT } from "../hooks/useT";

export function PanelsList(props: { count: number }) {
  const t = useT();
  return (
    <Card title={t("panels.title")}>
      <div className="text-2xl font-bold">{props.count}</div>
      <div className="text-sm efhc-text-muted">
        {t("panels.active_count")}
      </div>
    </Card>
  );
}
