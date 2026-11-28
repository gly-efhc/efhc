import React from "react";

export type AppNavIconKind =
  | "energy"
  | "panels"
  | "exchange"
  | "tasks"
  | "referrals"
  | "ranks";

export function AppNavIcon(props: {
  kind: AppNavIconKind;
  size?: number;
  className?: string;
}) {
  const size = props.size ?? 24;
  const common = {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    xmlns: "http://www.w3.org/2000/svg",
    className: props.className,
    "aria-hidden": true,
    focusable: false,
    "data-app-nav-icon": props.kind,
    "data-nav-icon-system": "rounded-outline-v2",
  } as const;
  const stroke = {
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
  };

  if (props.kind === "energy") {
    return (
      <svg {...common}>
        <circle cx="12" cy="12" r="8.8" {...stroke} />
        <path
          d="m13.1 4.7-5 7.2h3.35l-.52 7.05 5-7.2h-3.35l.52-7.05Z"
          fill="currentColor"
          stroke="currentColor"
          strokeWidth="0.75"
          strokeLinejoin="round"
        />
      </svg>
    );
  }

  if (props.kind === "panels") {
    return (
      <svg {...common}>
        <path d="M5.3 5h13.4l1.2 9.2H4.1L5.3 5Z" {...stroke} />
        <path d="M8.4 5 7.8 14.2M15.6 5l.6 9.2M4.7 9.6h14.6" {...stroke} opacity="0.82" />
        <path d="M12 14.2v4.1M8.7 19h6.6" {...stroke} />
        <path d="M18.7 2.8v1.1M21.2 5.2h-1.1M16.9 4.1l-.8-.8" {...stroke} opacity="0.75" />
      </svg>
    );
  }

  if (props.kind === "exchange") {
    return (
      <svg {...common}>
        <rect x="3.2" y="3.2" width="17.6" height="17.6" rx="5.2" {...stroke} opacity="0.42" />
        <path d="M6.4 8.2h10.8M14.5 5.7l2.7 2.5-2.7 2.5" {...stroke} />
        <path d="M17.6 15.8H6.8M9.5 13.3l-2.7 2.5 2.7 2.5" {...stroke} />
      </svg>
    );
  }

  if (props.kind === "tasks") {
    return (
      <svg {...common}>
        <rect x="4.4" y="3.5" width="15.2" height="17" rx="3.2" {...stroke} />
        <path d="m7.3 9 1.35 1.35 2.45-2.7M13 9h3.7M7.3 14.1h9.4M7.3 17.2h6.1" {...stroke} />
      </svg>
    );
  }

  if (props.kind === "referrals") {
    return (
      <svg {...common}>
        <circle cx="9" cy="8.1" r="2.7" {...stroke} />
        <circle cx="17" cy="9.1" r="2.05" {...stroke} />
        <path d="M3.7 19.2c.55-3.55 2.3-5.25 5.3-5.25s4.75 1.7 5.3 5.25" {...stroke} />
        <path d="M14.25 14.35c2.85-.15 4.7 1.35 5.25 4.45" {...stroke} opacity="0.8" />
      </svg>
    );
  }

  return (
    <svg {...common}>
      <path d="M7.2 4.2h9.6v4.2a4.8 4.8 0 0 1-9.6 0V4.2Z" {...stroke} />
      <path d="M7.2 6H4.5v1.6c0 2.1 1.15 3.2 3.15 3.35M16.8 6h2.7v1.6c0 2.1-1.15 3.2-3.15 3.35" {...stroke} />
      <path d="M12 13.2v3.1M8.8 19.2h6.4M9.6 16.3h4.8" {...stroke} />
      <path d="m12 5.8.55 1.1 1.25.18-.9.87.22 1.23L12 8.6l-1.12.58.22-1.23-.9-.87 1.25-.18L12 5.8Z" fill="currentColor" />
    </svg>
  );
}
