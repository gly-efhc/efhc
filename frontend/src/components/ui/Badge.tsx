import React from "react";

type Variant = "vip" | "admin" | "neutral";

type Props = React.PropsWithChildren<{ variant?: Variant }>;

export function Badge(props: Props) {
  const v = props.variant || "neutral";
  const cls =
    v === "vip"
      ? "bg-[var(--tg-button)] text-[var(--tg-button-text)]"
      : v === "admin"
        ? "bg-[var(--tg-link)] text-[var(--tg-bg)]"
        : "bg-[var(--tg-secondary-bg)] text-[var(--tg-text)] "
          + "border border-[color:var(--tg-hint)]";

  return (
    <span
      className={[
        "inline-flex items-center text-[10px] px-2 py-0.5 rounded-full",
        cls,
      ].join(" ")}
    >
      {props.children}
    </span>
  );
}
