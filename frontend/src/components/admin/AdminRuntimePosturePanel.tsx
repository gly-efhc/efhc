import React, {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";

import { adminSafeLoadError } from "../../lib/adminError";
import { useAdminLinkedTransport } from
  "../../queries/useAdminLinkedTransport";
import {
  AdminFreshnessBadge,
  AdminKpiCard,
  AdminPanelChrome,
  AdminStatusBadge,
} from "./AdminDashboardUiKit";

type RuntimeAlert = {
  id?: string;
  severity?: string;
  value?: number | string;
};

type RuntimeHealth = {
  ok: boolean;
  generated_at: string;
  posture: Record<string, string>;
  deployment: Record<string, string>;
  request_metrics: {
    total_requests?: number;
    sample_count?: number;
    recent_4xx?: number;
    recent_5xx?: number;
    latency_ms?: Record<string, number>;
    privacy?: Record<string, boolean>;
  };
  alerts: RuntimeAlert[];
};

const EMPTY_HEALTH: RuntimeHealth = {
  ok: false,
  generated_at: "",
  posture: {},
  deployment: {},
  request_metrics: {},
  alerts: [],
};

function normalizeRuntimeHealth(value: unknown): RuntimeHealth {
  if (!value || typeof value !== "object") return EMPTY_HEALTH;
  const raw = value as Partial<RuntimeHealth>;
  const requestMetrics = (
    raw.request_metrics
    && typeof raw.request_metrics === "object"
  ) ? raw.request_metrics : {};
  return {
    ok: Boolean(raw.ok),
    generated_at: String(raw.generated_at || ""),
    posture: (
      raw.posture
      && typeof raw.posture === "object"
    ) ? raw.posture : {},
    deployment: (
      raw.deployment
      && typeof raw.deployment === "object"
    ) ? raw.deployment : {},
    request_metrics: requestMetrics,
    alerts: Array.isArray(raw.alerts) ? raw.alerts : [],
  };
}

function toneFor(value: string) {
  if (value === "verified") return "success" as const;
  if (value === "attention") return "warning" as const;
  return "neutral" as const;
}

export function AdminRuntimePosturePanel() {
  const request = useAdminLinkedTransport();
  const [health, setHealth] = useState(EMPTY_HEALTH);
  const [loading, setLoading] = useState(true);
  const [safeLoadMessage, setError] = useState("");
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState("");

  const load = useCallback(() => {
    setLoading(true);
    setError("");
    void request<RuntimeHealth>(
      "/admin/observability/health",
      "GET",
    )
      .then((payload) => {
        setHealth(normalizeRuntimeHealth(payload));
      })
      .catch((caught: unknown) => {
        setHealth(EMPTY_HEALTH);
        setError(adminSafeLoadError(caught));
      })
      .finally(() => setLoading(false));
  }, [request]);

  useEffect(() => {
    load();
  }, [load]);

  const posture = useMemo(
    () => Object.entries(health.posture),
    [health.posture],
  );
  const latency = health.request_metrics.latency_ms || {};
  const critical = health.alerts.filter(
    (item) => item.severity === "critical",
  ).length;

  const copyFinding = async (finding: string) => {
    try {
      await navigator.clipboard.writeText(finding);
      setCopied(finding);
    } catch {
      setCopied("");
    }
  };

  return (
    <section
      className="efhc-admin-runtime-posture"
      data-admin-runtime-posture="cycle-1568"
      data-admin-runtime-critical={critical}
    >
      <div className="efhc-admin-runtime-posture_head">
        <div>
          <span>Безопасность и состояние приложения</span>
          <strong>
            {health.ok ? "Контур стабилен" : "Требуется внимание"}
          </strong>
        </div>
        <div className="flex flex-wrap gap-2">
          <AdminFreshnessBadge
            freshness={
              safeLoadMessage ? "stale" : loading ? "unknown" : "fresh"
            }
            label={
              loading ? "проверка" : safeLoadMessage ? "нет данных" : "актуально"
            }
          />
          <button
            type="button"
            className="efhc-admin-posture-toggle"
            onClick={() => setExpanded((value) => !value)}
          >
            {expanded ? "Скрыть технические данные" : "Открыть технические данные"}
          </button>
        </div>
      </div>

      <div className="efhc-admin-runtime-posture_grid">
        {posture.map(([key, value]) => (
          <AdminStatusBadge
            key={key}
            label={`${key.replaceAll("_", " ")}: ${value}`}
            tone={toneFor(value)}
          />
        ))}
      </div>

      <div className="efhc-admin-runtime-posture_kpis">
        <AdminKpiCard
          label="Запросы"
          value={String(
            health.request_metrics.total_requests || 0,
          )}
          meta={`${health.request_metrics.sample_count || 0} примеров`}
          hint="Без body, query string и пользовательских ID."
          tone="neutral"
        />
        <AdminKpiCard
          label="Задержка p95"
          value={`${latency.p95 || 0} ms`}
          meta={`p99 ${latency.p99 || 0} ms`}
          hint="Ограниченное текущее окно работы процесса."
          tone={
            Number(latency.p95 || 0) >= 1500
              ? "warning"
              : "success"
          }
        />
        <AdminKpiCard
          label="5xx"
          value={String(health.request_metrics.recent_5xx || 0)}
          meta={`${health.request_metrics.recent_4xx || 0} недавних 4xx`}
          hint="Только агрегированные классы ответов."
          tone={critical ? "warning" : "success"}
        />
        <AdminKpiCard
          label="Неизменяемый образ"
          value={health.deployment.immutability || "частично"}
          meta={health.deployment.environment || "неизвестно"}
          hint={health.deployment.image_digest || "отпечаток недоступен"}
          tone={
            health.deployment.immutability === "verified"
              ? "success"
              : "warning"
          }
        />
      </div>

      {expanded ? (
        <AdminPanelChrome
          title="Технические подробности"
          subtitle={
            "Идентификаторы предупреждений можно копировать; секреты и исходное содержимое ответа "
            + "в ответ не включаются."
          }
          status={health.alerts.length ? "error" : "success"}
          source="GET /admin/observability/health"
        >
          <div className="efhc-admin-posture-evidence">
            {health.alerts.length ? (
              health.alerts.map((item, index) => {
                const finding = item.id || `RUNTIME-${index + 1}`;
                return (
                  <button
                    key={finding}
                    type="button"
                    onClick={() => void copyFinding(finding)}
                  >
                    <span>{finding}</span>
                    <b>{copied === finding ? "Скопировано" : "Копировать"}</b>
                  </button>
                );
              })
            ) : (
              <p>Активных системных предупреждений нет.</p>
            )}
            <dl>
              <div>
                <dt>SHA сборки</dt>
                <dd>{health.deployment.build_sha || "недоступно"}</dd>
              </div>
              <div>
                <dt>Отпечаток образа</dt>
                <dd>{health.deployment.image_digest || "недоступно"}</dd>
              </div>
              <div>
                <dt>Сформировано</dt>
                <dd>{health.generated_at || "—"}</dd>
              </div>
            </dl>
          </div>
        </AdminPanelChrome>
      ) : null}
      {safeLoadMessage ? (
        <p className="efhc-safe-error-inline">
          {safeLoadMessage}
        </p>
      ) : null}
    </section>
  );
}
