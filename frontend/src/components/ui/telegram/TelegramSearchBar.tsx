import React from "react";

type Props = {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  inputLabel: string;
  clearLabel: string;
  resultCount?: number;
  resultCountLabel?: string;
  onClear?: () => void;
  loading?: boolean;
  className?: string;
};

export function TelegramSearchBar(props: Props) {
  return (
    <div className={props.className}>
      <div
        className={[
          "rounded-2xl border px-3 py-3",
          "border-[color:var(--tg-hint)]/20",
          "bg-[var(--tg-secondary-bg)]",
        ].join(" ")}
      >
        <div className="flex items-center gap-3">
          <span className="text-sm text-[color:var(--tg-hint)]">⌕</span>
          <input
            type="search"
            value={props.value}
            onChange={(event) => props.onChange(event.target.value)}
            placeholder={props.placeholder}
            aria-label={props.inputLabel}
            className={[
              "min-w-0 flex-1 bg-transparent outline-none",
              "text-sm text-[var(--tg-text)]",
              "placeholder:text-[color:var(--tg-hint)]",
            ].join(" ")}
          />
          {props.value ? (
            <button
              type="button"
              onClick={props.onClear}
              aria-label={props.clearLabel}
              title={props.clearLabel}
              className="text-xs text-[color:var(--tg-hint)]"
            >
              ×
            </button>
          ) : null}
        </div>
      </div>
      {typeof props.resultCount === "number" || props.loading ? (
        <div
          className="mt-1 px-1 text-xs text-[color:var(--tg-hint)]"
          role="status"
          aria-live="polite"
          aria-atomic="true"
        >
          {props.loading ? "…" : (props.resultCountLabel || props.resultCount)}
        </div>
      ) : null}
    </div>
  );
}
