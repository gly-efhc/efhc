import React from "react";

type Props = {
  size?: number;
  className?: string;
};

export function EfhcCoinIcon({ size = 24, className = "" }: Props) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-hidden="true"
      focusable="false"
      data-efhc-energy-mark="universal-lightning"
    >
      <circle
        cx="12"
        cy="12"
        r="10"
        fill="currentColor"
        fillOpacity="0.12"
        stroke="currentColor"
        strokeWidth="1.7"
      />
      <path
        d="M13.35 3.7 6.9 13h4.25l-.5 7.3 6.45-9.3h-4.25l.5-7.3Z"
        fill="currentColor"
        stroke="currentColor"
        strokeLinejoin="round"
        strokeWidth="0.65"
      />
    </svg>
  );
}

export const EfhcCoin = EfhcCoinIcon;
