import React from "react";

/** OWNER 0548: the only Energy glyph, CT-coloured by its EI-07 container. */
export function EnergyVariantIcon(props: { variant?: string; size?: number }) {
  const size = props.size || 28;
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="m13 4.5-5 7.4h3.4l-.6 7.6 5.2-7.5h-3.5l.5-7.5Z" fill="currentColor" />
    </svg>
  );
}
