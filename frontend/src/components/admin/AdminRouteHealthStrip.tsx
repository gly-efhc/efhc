import React, { useEffect, useState } from "react";

import { TelegramInfoBlock } from "../ui/telegram/TelegramInfoBlock";
import { TelegramStatusBadge } from "../ui/telegram/TelegramStatusBadge";
import { useAdminLinkedTransport } from "../../queries/useAdminLinkedTransport";

type RouteFact = {
  label: string;
  path: string;
  tone?: "neutral" | "connected" | "warning" | "primary";
};

type RuntimeHealth = {
  ok: boolean;
  backend?: { ok?: boolean };
  db?: { ok?: boolean };
  watcher?: {
    ok?: boolean;
    status?: string;
    heartbeat_age_sec?: number | null;
  };
};

type Props = {
  title?: string;
  subtitle?: string;
  items: RouteFact[];
};

function watcherLabel(runtime: RuntimeHealth | null) {
  const age = runtime?.watcher?.heartbeat_age_sec;
  const status = runtime?.watcher?.status || "unknown";
  if (age === null || age === undefined) return `watcher · ${status}`;
  return `watcher · ${status} · ${Math.round(age)}s`;
}

export function AdminRouteHealthStrip({
  title = "Диагностика маршрута",
  subtitle,
  items,
}: Props) {
  const apiRequest = useAdminLinkedTransport();
  const [runtime, setRuntime] = useState<RuntimeHealth | null>(null);

  useEffect(() => {
    let alive = true;
    void apiRequest<RuntimeHealth>("/api/health/runtime", "GET")
      .then((res) => {
        if (alive) setRuntime(res);
      })
      .catch(() => {
        if (alive) setRuntime(null);
      });
    return () => {
      alive = false;
    };
  }, [apiRequest]);

  return (
    <TelegramInfoBlock title={title}>
      {subtitle ? <div className="mt-2 text-xs opacity-80">{subtitle}</div> : null}
      <div className="mt-3 flex flex-wrap gap-2">
        <TelegramStatusBadge
          label={`сервер · ${runtime?.backend?.ok ? "работает" : "неизвестно"}`}
          tone={runtime?.backend?.ok ? "connected" : "warning"}
        />
        <TelegramStatusBadge
          label={`база · ${runtime?.db?.ok ? "работает" : "неизвестно"}`}
          tone={runtime?.db?.ok ? "connected" : "warning"}
        />
        <TelegramStatusBadge
          label={watcherLabel(runtime)}
          tone={runtime?.watcher?.ok ? "connected" : "warning"}
        />
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {items.map((item) => (
          <TelegramStatusBadge
            key={`${item.label}:${item.path}`}
            label={`${item.label} · ${item.path}`}
            tone={item.tone || "neutral"}
          />
        ))}
      </div>
    </TelegramInfoBlock>
  );
}
