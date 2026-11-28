import React from "react";

import { useT } from "../../hooks/useT";

type Props = {
  status: string;
  holdDone?: boolean;
  refundDone?: boolean;
};

type Step = {
  id: string;
  label: string;
  state: "done" | "current" | "waiting" | "stopped";
};

export function WithdrawStatusTimeline(props: Props) {
  const t = useT();
  const status = String(props.status || "").toUpperCase();
  const terminalPaid = status === "PAID";
  const terminalRejected = [
    "REJECTED",
    "CANCELED",
    "FAILED",
  ].includes(status);
  const steps: Step[] = [
    {
      id: "verification",
      label: t("withdraw.timeline_verification"),
      state: props.holdDone ? "done" : "current",
    },
    {
      id: "decision",
      label: terminalRejected
        ? t("withdraw.timeline_rejected")
        : t("withdraw.timeline_decision"),
      state: terminalPaid
        ? "done"
        : terminalRejected
          ? "stopped"
          : props.holdDone
            ? "current"
            : "waiting",
    },
    {
      id: "settlement",
      label: props.refundDone
        ? t("withdraw.timeline_refunded")
        : terminalPaid
          ? t("withdraw.timeline_sent")
          : t("withdraw.timeline_settlement"),
      state: terminalPaid || props.refundDone
        ? "done"
        : terminalRejected
          ? "current"
          : "waiting",
    },
  ];

  const stateLabel = (state: Step["state"]): string => {
    if (state === "done") return t("withdraw.timeline_done");
    if (state === "current") return t("withdraw.timeline_current");
    if (state === "stopped") return t("withdraw.timeline_stopped");
    return t("withdraw.timeline_waiting");
  };

  return (
    <ol
      className="efhc-withdraw-status-timeline"
      data-withdraw-status-timeline={status || "UNKNOWN"}
    >
      {steps.map((step, index) => (
        <li key={step.id} data-state={step.state}>
          <span>{index + 1}</span>
          <div>
            <strong>{step.label}</strong>
            <small>{stateLabel(step.state)}</small>
          </div>
        </li>
      ))}
    </ol>
  );
}
