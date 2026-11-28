import React, { useEffect, useState } from "react";

import { useAdminLinkedTransport } from
  "../../queries/useAdminLinkedTransport";

type Health = {
  ok?: boolean;
  alerts?: Array<{ severity?: string }>;
};

export function AdminSecurityAttentionBadge() {
  const request = useAdminLinkedTransport();
  const [attention, setAttention] = useState(false);

  useEffect(() => {
    let active = true;
    void request<Health>("/admin/observability/health", "GET")
      .then((value) => {
        if (!active) return;
        const critical = (value.alerts || []).some(
          (item) => item.severity === "critical",
        );
        setAttention(value.ok === false || critical);
      })
      .catch(() => {
        if (active) setAttention(true);
      });
    return () => {
      active = false;
    };
  }, [request]);

  if (!attention) return null;

  return (
    <a
      href="/admin/diagnostics"
      className="efhc-admin-security-attention"
      data-security-attention="evidence-driven"
    >
      Security attention
    </a>
  );
}
