import React, { useEffect, useState } from "react";
import { AdminPage } from "../../components/admin/AdminPage";
import {
  AdminDomainReportsDashboardRuntime,
} from "../../components/admin/AdminDomainReportsDashboardRuntime";
import {
  AdminObservabilityTimeseriesDashboardRuntime,
} from "../../components/admin/AdminObservabilityTimeseriesDashboardRuntime";
import {
  AdminReportsVisualDashboardPanel,
} from "../../components/admin/AdminReportsVisualDashboardPanel";
import { AdminLogsEventsDashboardRuntime } from "../../components/admin/AdminLogsEventsDashboardRuntime";
import { Button } from "../../components/ui/Button";
import { useAdminPageGlobalIdSelection } from "../../hooks/admin/useAdminPageGlobalIdSelection";
import { useT } from "../../hooks/useT";
import {
  ADMIN_REPORTS_OVERVIEW_PATH,
} from "../../lib/api/generated/adminSeams";
import { adminSafeLoadError } from "../../lib/adminError";
import { useAdminLinkedTransport } from "../../queries/useAdminLinkedTransport";
import { parseGlobalId } from "../../types/identity";

type Overview = {
  ok: boolean;
  ts: string;
  counters: Record<string, number>;
  facts?: Record<string, string>;
  notes?: string | null;
};

export default function AdminReportsPage() {
  const adminApiRequest = useAdminLinkedTransport();
  const t = useT();
  const [overview, setOverview] = useState<Overview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [globalIdInput, setGlobalIdInput] = useState("");
  const [globalIdError, setGlobalIdError] = useState<string | null>(null);
  const {
    selectedGlobalId,
    restored,
    rememberGlobalId,
    clearGlobalId,
  } = useAdminPageGlobalIdSelection("reports");

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await adminApiRequest<Overview>(
        ADMIN_REPORTS_OVERVIEW_PATH,
        "GET",
      );
      setOverview(res);
    } catch (e: unknown) {
      setError(adminSafeLoadError(e, t));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  useEffect(() => {
    if (!restored) return;
    setGlobalIdInput(selectedGlobalId ? String(selectedGlobalId) : "");
  }, [restored, selectedGlobalId]);

  function applyGlobalId() {
    try {
      const parsed = parseGlobalId(globalIdInput.trim());
      rememberGlobalId(parsed);
      setGlobalIdInput(String(parsed));
      setGlobalIdError(null);
    } catch {
      setGlobalIdError("Global ID должен содержать ровно 10 цифр.");
    }
  }

  function resetGlobalId() {
    clearGlobalId();
    setGlobalIdInput("");
    setGlobalIdError(null);
  }

  return (
    <AdminPage
      refreshBankSnapshot={false}
      title="Отчёты и журналы"
      backHref="/admin"
    >
      <AdminReportsVisualDashboardPanel
        error={error}
        loading={loading}
        onRefresh={() => void load()}
        overview={overview}
      />
      <AdminDomainReportsDashboardRuntime />
      <AdminObservabilityTimeseriesDashboardRuntime />

      <div
        className="efhc-admin-reports-global-id-v440"
        data-admin-reports-global-id-scope="v440"
      >
        <div className="efhc-admin-reports-global-id-label-v440">Global ID</div>
        <div
          className="grid grid-cols-2 items-end"
          data-admin-selected-global-id={selectedGlobalId || "none"}
          data-admin-search-geometry="v425-v431"
          data-admin-reports-global-search-scope="v440"
          style={{ gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: ".45rem" }}
        >
          <input
            className="efhc-input col-span-2 w-full"
            inputMode="numeric"
            maxLength={10}
            value={globalIdInput}
            onChange={(event) => {
              setGlobalIdInput(event.target.value.replace(/\D/g, "").slice(0, 10));
              if (globalIdError) setGlobalIdError(null);
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter") applyGlobalId();
            }}
            placeholder="Global ID — 10 цифр"
            aria-label="Global ID для всего модуля Отчёты и журналы"
            style={{ minHeight: "2.25rem", padding: ".52rem .62rem", borderRadius: ".68rem" }}
          />
          <Button
            className="w-full min-w-0"
            variant="secondary"
            disabled={!globalIdInput && !selectedGlobalId}
            onClick={resetGlobalId}
            style={{ minHeight: "2.25rem", padding: ".52rem .68rem", borderRadius: ".68rem" }}
          >
            Сбросить
          </Button>
          <Button
            className="w-full min-w-0"
            variant="secondary"
            disabled={globalIdInput.length !== 10}
            onClick={applyGlobalId}
            style={{ minHeight: "2.25rem", padding: ".52rem .68rem", borderRadius: ".68rem" }}
          >
            Найти
          </Button>
        </div>
        {globalIdError ? <p className="mt-2 text-sm text-red-200">{globalIdError}</p> : null}
      </div>

      <section className="grid gap-4" data-admin-reports-journals data-admin-flat-group="true" data-admin-reports-black-violet="v435">
        <AdminLogsEventsDashboardRuntime
          selectedGlobalId={selectedGlobalId}
          selectionRestored={restored}
        />
      </section>
    </AdminPage>
  );
}
