import React from "react";

type Props = {
  kind: "activ" | "vip";
  active: boolean;
  label: string;
  className?: string;
};

export function StatusIndicator(props: Props) {
  return (
    <span
      className={["efhc-game-header_status", props.className || ""]
        .filter(Boolean)
        .join(" ")}
      data-status={props.kind}
      data-active={props.active ? "true" : "false"}
      aria-label={props.label}
    >
      {props.label}
    </span>
  );
}
