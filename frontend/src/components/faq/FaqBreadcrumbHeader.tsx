import React from "react";

type Props = {
  parts: string[];
  onBack?: () => void;
};

export function FaqBreadcrumbHeader(props: Props) {
  return (
    <div className="space-y-2">
      {props.onBack ? (
        <button
          type="button"
          onClick={props.onBack}
          className="text-xs text-[color:var(--tg-hint)]"
        >
          ←
        </button>
      ) : null}
      <div className="text-xs text-[color:var(--tg-hint)]">
        {props.parts.join(" / ")}
      </div>
    </div>
  );
}
