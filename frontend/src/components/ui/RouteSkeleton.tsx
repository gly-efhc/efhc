import React from "react";
import { useT } from "../../hooks/useT";

type Props = {
  kind?: "cards" | "table" | "legal";
  rows?: number;
};

export function RouteSkeleton({
  kind = "cards",
  rows = 4,
}: Props) {
  const t = useT();
  return (
    <section
      className={`efhc-route-skeleton is-${kind}`}
      data-route-skeleton={kind}
      aria-busy="true"
      aria-label={t("common.loading")}
    >
      <div className="efhc-route-skeleton_title" />
      {Array.from({ length: rows }).map((_, index) => (
        <div
          key={index}
          className="efhc-route-skeleton_row"
        />
      ))}
    </section>
  );
}
