import React from "react";

export function Skeleton(props: { className?: string }) {
  const base = [
    "rounded-2xl",
    "border border-[color:var(--tg-hint)]",
    "bg-[color:var(--tg-secondary-bg)]/60",
    "overflow-hidden",
    "relative",
    "animate-pulse",
  ].join(" ");
  return (
    <div
      className={`${base} ${props.className || ""}`}
      aria-hidden
    >
      <div className="h-full w-full" />
    </div>
  );
}
