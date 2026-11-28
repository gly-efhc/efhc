import React, { useCallback, useEffect, useMemo, useState } from "react";

import { AdminSectionCard } from "./AdminSectionCard";
import { ADMIN_REPORTS_OVERVIEW_PATH } from "../../lib/api/generated/adminSeams";
import { adminSafeLoadError } from "../../lib/adminError";
import { useAdminLinkedTransport } from "../../queries/useAdminLinkedTransport";
import { Button } from "../ui/Button";

type OverviewResponse = {
  ok: boolean;
  ts: string;
  counters: Record<string, number>;
  facts?: Record<string, string>;
  notes?: string | null;
};

type PanelOverviewModel = {
  activeTotal: bigint;
  deactivatedTotal: bigint;
  total: bigint;
};

function count(value: string | undefined): bigint {
  if (!value || !/^\d+$/.test(value)) return 0n;
  return BigInt(value);
}

function percentParts(part: bigint, total: bigint): { label: string; width: string } {
  if (total <= 0n || part <= 0n) return { label: "0%", width: "0%" };
  const scaled = (part * 10_000n) / total;
  const whole = scaled / 100n;
  const fraction = (scaled % 100n).toString().padStart(2, "0");
  const label = fraction === "00" ? `${whole}%` : `${whole}.${fraction.replace(/0$/, "")}%`;
  return { label, width: `${whole}.${fraction}%` };
}

function PanelMapRow(props: {
  label: string;
  value: bigint;
  total: bigint;
  note: string;
  tone: "total" | "active" | "archive";
}) {
  const percent = percentParts(props.value, props.total);
  return (
    <div className="efhc-admin-panels-map-v188_row" data-series={props.tone}>
      <div className="efhc-admin-panels-map-v188_copy">
        <strong>{props.label}</strong>
        <span>{props.value.toString()}</span>
      </div>
      <div className="efhc-admin-panels-map-v188_indicator">
        <div className="efhc-admin-panels-map-v188_track" aria-hidden="true">
          <span style={{ width: percent.width }} />
        </div>
        <b>{percent.label}</b>
      </div>
      <small>{props.note}</small>
    </div>
  );
}

export function AdminPanelsObligationsRuntime() {
  const adminApiRequest = useAdminLinkedTransport();
  const [overview, setOverview] = useState<OverviewResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await adminApiRequest<OverviewResponse>(
        ADMIN_REPORTS_OVERVIEW_PATH,
        "GET",
      );
      setOverview(response);
    } catch (err: unknown) {
      setOverview(null);
      setError(adminSafeLoadError(err));
    } finally {
      setLoading(false);
    }
  }, [adminApiRequest]);

  useEffect(() => {
    void load();
  }, [load]);

  const model = useMemo<PanelOverviewModel>(() => {
    const facts = overview?.facts ?? {};
    const activeTotal = count(facts.panels_total_active);
    const deactivatedTotal = count(facts.panels_total_archived);
    return {
      activeTotal,
      deactivatedTotal,
      total: activeTotal + deactivatedTotal,
    };
  }, [overview]);

  return (
    <section
      className="space-y-4"
      data-admin-panels-overview="FRONTEND_v188"
      data-admin-panels-source="GET /admin/reports/overview"
    >
      <AdminSectionCard
        title="Карта Панелей"
        actions={
          <Button variant="secondary" onClick={() => void load()} disabled={loading}>
            {loading ? "Проверяется" : "Обновить"}
          </Button>
        }
      >
        <div className="efhc-admin-panels-map-v188" data-eam-family="EAM-ADMIN-019">
          <PanelMapRow
            label="Всего панелей"
            value={model.total}
            total={model.total}
            note="Все активные и завершённые панели"
            tone="total"
          />
          <PanelMapRow
            label="Активные панели"
            value={model.activeTotal}
            total={model.total}
            note="Сейчас работают"
            tone="active"
          />
          <PanelMapRow
            label="Завершённые панели"
            value={model.deactivatedTotal}
            total={model.total}
            note="Обычный архив, без мёртвых Панелей"
            tone="archive"
          />
        </div>
        {error ? <div className="mt-3 text-sm text-[color:var(--efhc-danger,#ef4444)]">{error}</div> : null}
      </AdminSectionCard>
    </section>
  );
}
