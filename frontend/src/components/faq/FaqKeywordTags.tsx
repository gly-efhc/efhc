import React from "react";

export function FaqKeywordTags(props: { tags?: string[] }) {
  if (!props.tags?.length) return null;
  return (
    <div className="flex flex-wrap gap-2">
      {props.tags.slice(0, 6).map((tag) => (
        <span
          key={tag}
          className={[
            "rounded-full px-2.5 py-1 text-[11px]",
            "bg-[var(--tg-bg)] text-[color:var(--tg-hint)]",
          ].join(" ")}
        >
          {tag}
        </span>
      ))}
    </div>
  );
}
