import React from "react";

type Kind = "neutral" | "ok" | "warn" | "bad";

function pickKind(status: string): Kind {
  const s = String(status || "").toUpperCase();
  if (s === "PAID" || s === "DONE" || s === "SUCCESS") return "ok";
  if (s === "PENDING" || s === "UNDER_REVIEW" || s === "APPROVED") {
    return "warn";
  }
  if (s === "REJECTED" || s === "CANCELED" || s === "FAILED") {
    return "bad";
  }
  return "neutral";
}

export function EfhcStatus(props: { status: string }) {
  const k = pickKind(props.status);

  const icon =
    k === "ok" ? "✓" : k === "warn" ? "!" : k === "bad" ? "×" : "·";
  const cls =
    k === "ok"
      ? "efhc-status efhc-status-accent"
      : "efhc-status";

  return (
    <span
      className={[
        "inline-flex items-center",
        "text-[10px]",
        "px-2 py-0.5",
        "rounded-full",
        cls,
      ].join(" ")}
    >
      <span className="mr-1" aria-hidden="true">{icon}</span>
      <span>{props.status}</span>
    </span>
  );
}
