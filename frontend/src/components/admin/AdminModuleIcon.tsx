import React from "react";

function IconShell(props: React.PropsWithChildren<{ label: string }>) {
  return (
    <svg
      aria-label={props.label}
      className="efhc-admin-module-icon"
      fill="none"
      role="img"
      viewBox="0 0 24 24"
    >
      {props.children}
    </svg>
  );
}

export function AdminModuleIcon(props: { href: string; label: string }) {
  const common = {
    stroke: "currentColor",
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    strokeWidth: 1.8,
  };
  const href = props.href;
  if (href.includes("users") || href.includes("referrals")) {
    return (
      <IconShell label={props.label}>
        <circle cx="9" cy="8" r="3" {...common} />
        <path d="M3.5 19c.6-3.5 2.4-5.3 5.5-5.3s4.9 1.8 5.5 5.3" {...common} />
        <path d="M16 7.5c2.3.2 3.7 1.6 4 4M16.5 14c2.2.5 3.4 2.1 3.8 5" {...common} />
      </IconShell>
    );
  }
  if (href.includes("withdraw") || href.includes("deposits") || href.includes("bank")) {
    return (
      <IconShell label={props.label}>
        <rect x="3" y="5" width="18" height="14" rx="3" {...common} />
        <path d="M3 9h18M15 14h3" {...common} />
      </IconShell>
    );
  }
  if (href.includes("shop") || href.includes("package")) {
    return (
      <IconShell label={props.label}>
        <path d="M4 7h16l-1.4 11H5.4L4 7Z" {...common} />
        <path d="M8 9V6a4 4 0 0 1 8 0v3" {...common} />
      </IconShell>
    );
  }
  if (href.includes("task") || href.includes("ads")) {
    return (
      <IconShell label={props.label}>
        <rect x="4" y="3" width="16" height="18" rx="3" {...common} />
        <path d="m8 9 1.5 1.5L12 8M8 15h8" {...common} />
      </IconShell>
    );
  }
  if (href.includes("panels")) {
    return (
      <IconShell label={props.label}>
        <path d="M5 8h14l2 9H3l2-9Z" {...common} />
        <path d="M8 8 7 17M12 8v9M16 8l1 9M6 12h12M12 17v4" {...common} />
      </IconShell>
    );
  }
  if (href.includes("reports") || href.includes("logs")) {
    return (
      <IconShell label={props.label}>
        <path d="M5 20V10M12 20V4M19 20v-7" {...common} />
      </IconShell>
    );
  }
  if (href.includes("diagnostics") || href.includes("system")) {
    return (
      <IconShell label={props.label}>
        <circle cx="12" cy="12" r="3" {...common} />
        <path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1" {...common} />
      </IconShell>
    );
  }
  return (
    <IconShell label={props.label}>
      <path d="M4 7 12 3l8 4-8 4-8-4Z" {...common} />
      <path d="M4 12l8 4 8-4M4 17l8 4 8-4" {...common} />
    </IconShell>
  );
}
