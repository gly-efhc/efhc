import React from "react";
import { Card } from "./ui/Card";
import { useT } from "../hooks/useT";

type Item = {
  global_id: string;
  username?: string | null;
  total_generated_kwh: string;
  rank_pos: number;
};

type Props = {
  items: Item[];
};

export function RanksTable(props: Props) {
  const t = useT();
  return (
    <Card title={t("ranks.table_title")}>
      <div className="grid gap-1">
        {props.items.length ? props.items.map((item) => (
          <div
            key={item.global_id}
            className="efhc-rank-card efhc-rank-row-compact"
            data-ranks-card="compact-row-32"
          >
            <div className="efhc-rank-position">{item.rank_pos}</div>
            <div className="efhc-rank-username">
              {item.username ? `@${item.username}` : t("ranks.user_hidden_fallback")}
            </div>
            <div className="efhc-rank-generated">
              {item.total_generated_kwh} kWh
            </div>
          </div>
        )) : (
          <div className="text-sm efhc-text-muted">
            {t("ranks.table_empty")}
          </div>
        )}
      </div>
    </Card>
  );
}
