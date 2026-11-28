import React from "react";

export function KwhIcon(
  { size = 16, className = "" }: { size?: number; className?: string },
) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-hidden="true"
      data-energy-mark="balanced-lightning-v2"
    >
      <circle
        cx="12"
        cy="12"
        r="9.25"
        stroke="currentColor"
        strokeWidth="1.55"
      />
      <path
        d="M12 1.9v2.05M12 20.05v2.05M1.9 12h2.05M20.05 12h2.05"
        stroke="currentColor"
        strokeWidth="1.25"
        strokeLinecap="round"
        opacity="0.72"
      />
      <path
        d="m13.15 4.25-5.7 8.2h3.85l-.55 7.3 5.8-8.2H12.7l.45-7.3Z"
        fill="currentColor"
        stroke="currentColor"
        strokeWidth="0.8"
        strokeLinejoin="round"
      />
    </svg>
  );
}
