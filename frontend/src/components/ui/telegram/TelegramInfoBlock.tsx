import React from "react";

export function TelegramInfoBlock(
  props: React.PropsWithChildren<
    React.HTMLAttributes<HTMLDivElement> & {
      title?: string;
      description?: React.ReactNode;
    }
  >,
) {
  const {
    title,
    description,
    children,
    className,
    ...rest
  } = props;
  const body = description ?? children;
  return (
    <div
      {...rest}
      className={[
        "efhc-user-info-block rounded-2xl border px-4 py-3",
        "border-[color:var(--tg-hint)]/20",
        "bg-[var(--tg-secondary-bg)]/80",
        className || "",
      ].join(" ")}
    >
      {title ? (
        <div className="text-sm font-semibold">{title}</div>
      ) : null}
      <div className="text-sm text-[color:var(--tg-hint)]">{body}</div>
    </div>
  );
}
