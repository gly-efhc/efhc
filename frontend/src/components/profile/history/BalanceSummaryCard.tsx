import React from "react";

type Props = {
  title: string;
  value: string;
  tone: "neutral" | "main" | "bonus";
  asset: "EFHC" | "EFHCm" | "EFHCb";
};

export function BalanceSummaryCard(props: Props) {
  return (
    <div
      className="efhc-history-balance-row"
      data-balance-tone={props.tone}
      data-balance-asset={props.asset}
    >
      <span className="efhc-history-balance-label">
        <span className="efhc-history-balance-dot" aria-hidden="true" />
        <span>{props.title}</span>
      </span>
      <strong className="efhc-history-balance-value efhc-financial-number">
        {props.value}
      </strong>
    </div>
  );
}
