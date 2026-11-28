import React from "react";

export function AdminSurfaceTabs(props: {
  items: Array<{ key: string; label: string }>;
  activeKey: string;
  onChange: (key: string) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {props.items.map((item) => {
        const active = item.key === props.activeKey;
        return (
          <button
            key={item.key}
            type="button"
            className={[
              "rounded-full border px-3 py-1.5 text-sm transition",
              active
                ? "border-[var(--tg-link)] bg-[var(--tg-link)]/10 text-[var(--tg-link)]"
                : "border-[color:var(--tg-hint)]/20 bg-[var(--tg-secondary-bg)] text-[color:var(--tg-hint)]",
            ].join(" ")}
            onClick={() => props.onChange(item.key)}
          >
            {item.label}
          </button>
        );
      })}
    </div>
  );
}
