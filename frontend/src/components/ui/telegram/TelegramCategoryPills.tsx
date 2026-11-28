import React from "react";

type Item = { id: string; label: string; count?: number };

type Props = {
  items: Item[];
  activeId?: string | null;
  onSelect: (id: string) => void;
};

export function TelegramCategoryPills(props: Props) {
  return (
    <div className="flex gap-2 overflow-x-auto pb-1">
      {props.items.map((item) => {
        const active = props.activeId === item.id;
        return (
          <button
            key={item.id}
            type="button"
            onClick={() => props.onSelect(item.id)}
            className={[
              "shrink-0 rounded-full px-3 py-1.5 text-xs font-semibold",
              active
                ? "bg-[var(--tg-button)] text-[var(--tg-button-text)]"
                : "bg-[var(--tg-secondary-bg)] text-[var(--tg-text)]",
            ].join(" ")}
          >
            {item.label}
            {typeof item.count === "number" ? ` · ${item.count}` : ""}
          </button>
        );
      })}
    </div>
  );
}
