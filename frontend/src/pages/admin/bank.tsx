import React, { useCallback, useEffect, useRef, useState } from "react";

import { AdminPage } from "../../components/admin/AdminPage";
import { AdminSectionCard } from "../../components/admin/AdminSectionCard";
import { Button } from "../../components/ui/Button";
import { useT } from "../../hooks/useT";
import { adminSafeLoadError, adminUiErrorMessage } from "../../lib/adminError";
import { ADMIN_REPORTS_OVERVIEW_PATH } from "../../lib/api/generated/adminSeams";
import { formatD8ToHuman, fromScaledBigint, toScaledBigintDown } from "../../lib/format";
import { useAdminLinkedTransport } from "../../queries/useAdminLinkedTransport";
import { useAdminLogExport } from "../../queries/useAdminLogExport";
import {
  type AdminLogExportFormat,
  type AdminLogExportRows,
} from "../../services/adminLogExport.service";

import {requireBankSnapshot,type AdminBankSnapshot} from "../../lib/adminBankSnapshot";

type OverviewResponse = AdminBankSnapshot;

type BankMapSeriesKey =
  | "reserve"
  | "circulation"
  | "panel-new-obligations"
  | "main"
  | "bonus"
  | "actual"
  | "panel-obligations"
  | "panel-spend"
  | "panel-generated"
  | "panel-converted"
  | "panel-pending-conversion";

type BankMapRow = {
  key: BankMapSeriesKey;
  label: string;
  value: string;
  percent: string;
  unit: string;
};

const D8 = 8;
const PCT_SCALE = 100_000_000n;
const PCT_100_SCALED = 100n * PCT_SCALE;

function parseD8(value: string | undefined): bigint {
  try {
    return toScaledBigintDown(value || "0.00000000", D8);
  } catch {
    return 0n;
  }
}

function percentTextFromSnapshot(
  value: string | undefined,
  decimals = 2,
  trimTrailingZeros = false,
): string {
  const scaled = parseD8(value);
  const negative = scaled < 0n;
  const absolute = negative ? -scaled : scaled;
  const divisor = 10n ** BigInt(D8 - decimals);
  const rounded = decimals < D8 ? (absolute + divisor / 2n) / divisor : absolute;
  const displayScale = 10n ** BigInt(decimals);
  const whole = rounded / displayScale;
  const fraction = decimals ? (rounded % displayScale).toString().padStart(decimals, "0") : "";
  let text = `${negative ? "−" : ""}${whole.toString()}${decimals ? `.${fraction}` : ""}`;
  if (trimTrailingZeros && decimals) {
    text = text.replace(/(\.\d*?[1-9])0+$/, "$1").replace(/\.0+$/, "");
  }
  return `${text}%`;
}

function percentWidthFromSnapshot(value: string | undefined): string {
  const scaled = parseD8(value);
  const absolute = scaled < 0n ? -scaled : scaled;
  const clamped = absolute > PCT_100_SCALED ? PCT_100_SCALED : absolute;
  return `${fromScaledBigint(clamped, D8)}%`;
}

function amountParts(value: string): { whole: string; fraction: string } {
  const text = formatD8ToHuman(value || "0.00000000");
  const dot = text.lastIndexOf(".");
  return dot >= 0
    ? { whole: text.slice(0, dot), fraction: text.slice(dot) }
    : { whole: text, fraction: "" };
}

export default function AdminBankPage() {
  const adminApiRequest = useAdminLinkedTransport();
  const adminLogExport = useAdminLogExport();
  const t = useT();
  const [overview, setOverview] = useState<OverviewResponse | null>(null);
  const [bankMapVisible, setBankMapVisible] = useState<Record<BankMapSeriesKey, boolean>>({
    reserve: true,
    circulation: true,
    "panel-new-obligations": true,
    main: true,
    bonus: true,
    actual: true,
    "panel-obligations": true,
    "panel-spend": true,
    "panel-generated": true,
    "panel-converted": true,
    "panel-pending-conversion": true,
  });
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState<AdminLogExportFormat | null>(null);
  const [exportRows, setExportRows] = useState<AdminLogExportRows>("100000");
  const [msg, setMsg] = useState<string | null>(null);

  const inFlight=useRef(false);
  const alive=useRef(true);
  const load = useCallback(async () => {
    if(inFlight.current)return;
    inFlight.current=true;
    setLoading(true);
    setMsg(null);
    try {
      const overviewRaw = await adminApiRequest<OverviewResponse>(
        ADMIN_REPORTS_OVERVIEW_PATH,
        "GET",
      );
      const snapshot=requireBankSnapshot(overviewRaw);
      if(!alive.current)return;
      setOverview(snapshot);
    } catch (error: unknown) {
      if(alive.current){setMsg(adminSafeLoadError(error,t));}
    } finally {
      inFlight.current=false;
      if(alive.current)setLoading(false);
    }
  },[adminApiRequest,t]);

  async function exportBankLogs(format: AdminLogExportFormat) {
    if (exporting) return;
    setExporting(format);
    setMsg(null);
    try {
      await adminLogExport.mutateAsync({ scope: "bank", format, rows: exportRows });
    } catch (error: unknown) {
      setMsg(adminUiErrorMessage(error, t));
    } finally {
      setExporting(null);
    }
  }

  useEffect(() => {
    alive.current=true;
    void load();
    return()=>{alive.current=false;};
  }, [load]);

  const facts = overview?.facts || {};
  const integrityReady = facts.bank_metrics_ready === "1";
  const integrityOk = integrityReady && facts.bank_metrics_integrity_ok === "1";
  const reserveRaw = facts.bank_metrics_reserve_efhc || "0.00000000";
  const circulationRaw = facts.bank_metrics_circulation_efhc || "0.00000000";
  const expectedRaw = facts.bank_metrics_expected_supply_efhc || "0.00000000";
  const integrityDeltaRaw = facts.bank_metrics_integrity_delta_efhc || "0.00000000";
  const integrityPercentRaw = facts.bank_metrics_integrity_pct || "0.00000000";
  const reservePercentRaw = facts.bank_metrics_reserve_pct || "0.00000000";
  const circulationPercentRaw = facts.bank_metrics_circulation_pct || "0.00000000";
  const totalPercentDisplay = integrityReady
    ? percentTextFromSnapshot(integrityPercentRaw, 8, true)
    : "—";

  const bankMapRows: BankMapRow[] = [
    {
      key: "reserve",
      label: "Резерв Банка",
      value: reserveRaw,
      percent: reservePercentRaw,
      unit: "EFHC",
    },
    {
      key: "circulation",
      label: "Весь оборот",
      value: circulationRaw,
      percent: circulationPercentRaw,
      unit: "EFHC",
    },
    {
      key: "panel-new-obligations",
      label: "Новые обязательства",
      value: facts.bank_metrics_new_obligations_efhcm || "0.00000000",
      percent: facts.bank_metrics_new_obligations_pct || "0.00000000",
      unit: "EFHCm",
    },
    {
      key: "main",
      label: "EFHCm пользователей",
      value: facts.bank_metrics_users_main_efhc || "0.00000000",
      percent: facts.bank_metrics_users_main_pct || "0.00000000",
      unit: "EFHCm",
    },
    {
      key: "bonus",
      label: "EFHCb пользователей",
      value: facts.bank_metrics_users_bonus_efhc || "0.00000000",
      percent: facts.bank_metrics_users_bonus_pct || "0.00000000",
      unit: "EFHCb",
    },
    {
      key: "actual",
      label: "Общая масса",
      value: facts.bank_metrics_actual_mass_efhc || "0.00000000",
      percent: facts.bank_metrics_actual_mass_pct || "0.00000000",
      unit: "EFHC",
    },
    {
      key: "panel-obligations",
      label: "Зафиксированные обязательства",
      value: facts.bank_metrics_fixed_obligations_efhcm || "0.00000000",
      percent: facts.bank_metrics_fixed_obligations_pct || "0.00000000",
      unit: "EFHCm",
    },
    {
      key: "panel-spend",
      label: "Потрачено EFHCm + EFHCb на все панели",
      value: facts.bank_metrics_panel_spent_efhc || "0.00000000",
      percent: facts.bank_metrics_panel_spent_pct || "0.00000000",
      unit: "EFHC",
    },
    {
      key: "panel-generated",
      label: "Сгенерировано kWh",
      value: facts.bank_metrics_generated_kwh || "0.00000000",
      percent: facts.bank_metrics_generated_pct || "0.00000000",
      unit: "kWh",
    },
    {
      key: "panel-converted",
      label: "Обмен kWh → EFHCm",
      value: facts.bank_metrics_converted_kwh || "0.00000000",
      percent: facts.bank_metrics_converted_pct || "0.00000000",
      unit: "EFHCm",
    },
    {
      key: "panel-pending-conversion",
      label: "В ожидании kWh → EFHCm",
      value: facts.bank_metrics_pending_kwh || "0.00000000",
      percent: facts.bank_metrics_pending_pct || "0.00000000",
      unit: "kWh",
    },
  ];

  return (
    <AdminPage
      refreshBankSnapshot={false}
      title="Банк EFHC"
      subtitle="Текущий резерв Банка и EFHC в обороте. Вместе они должны точно составлять 100% общей массы системы."
      backHref="/admin"
      surfaceBadges={[{ label: "Резерв Банка", tone: "primary" }]}
      actions={
        <Button variant="secondary" onClick={() => void load()} disabled={loading}>
          {loading ? "Проверяется" : t("common.refresh")}
        </Button>
      }
    >
      <div data-admin-bank-cycle="FRONTEND_v182_BANK_INTEGER_SNAPSHOT" data-bank-state={loading ? "loading" : overview ? "ready" : "unavailable"} />

      {msg ? (
        <AdminSectionCard title="Не удалось обновить Банк" subtitle={msg}>
          <Button variant="secondary" onClick={() => void load()}>
            {t("common.refresh")}
          </Button>
        </AdminSectionCard>
      ) : null}

      <AdminSectionCard
        title="Целостность системы"
        subtitle="Резерв + Оборот = 100%"
        actions={
          <span
            className={`efhc-admin-bank-integrity-status-v177 ${
              integrityReady ? (integrityOk ? "is-ok" : "is-error") : "is-pending"
            }`}
            data-status={integrityReady && !integrityOk ? "bank-integrity-error" : undefined}
          >
            {integrityReady ? (integrityOk ? "✓ 100%" : totalPercentDisplay) : "Проверка…"}
          </span>
        }
      >
        <div className="efhc-admin-bank-integrity-v153" data-eam-family="EAM-ADMIN-011">
          <div className="efhc-admin-bank-integrity-v153_columns">
            <div className="efhc-admin-bank-integrity-v153_side" data-side="reserve">
              <span>Резерв Банка</span>
              <strong>{integrityReady ? formatD8ToHuman(reserveRaw) : "—"} EFHC</strong>
              <b>{integrityReady ? percentTextFromSnapshot(reservePercentRaw, 2) : "—"}</b>
            </div>
            <div className="efhc-admin-bank-integrity-v153_side" data-side="circulation">
              <span>В обороте</span>
              <strong>{integrityReady ? formatD8ToHuman(circulationRaw) : "—"} EFHC</strong>
              <b>{integrityReady ? percentTextFromSnapshot(circulationPercentRaw, 2) : "—"}</b>
              <small>EFHCm + EFHCb пользователей</small>
            </div>
          </div>

          <div className="efhc-admin-bank-integrity-v153_ratio" aria-label="Соотношение резерва Банка и EFHC в обороте">
            <span
              className="efhc-admin-bank-integrity-v153_ratio-reserve"
              style={{ width: percentWidthFromSnapshot(reservePercentRaw) }}
            />
            <span
              className="efhc-admin-bank-integrity-v153_ratio-circulation"
              style={{ width: percentWidthFromSnapshot(circulationPercentRaw) }}
            />
          </div>

          <div className="efhc-admin-bank-integrity-v153_total" data-integrity-ok={integrityOk ? "true" : "false"}>
            <span>Итого</span>
            <strong>{totalPercentDisplay}</strong>
            <small>
              {!integrityReady
                ? "Проверка общей массы..."
                : integrityOk
                  ? `Общая масса ${formatD8ToHuman(expectedRaw)} EFHC`
                  : `Отклонение ${formatD8ToHuman(integrityDeltaRaw)} EFHC`}
            </small>
          </div>
        </div>
      </AdminSectionCard>

      <AdminSectionCard title="Балансовая карта">
        <div className="efhc-admin-bank-map-v154" data-eam-family="EAM-ADMIN-014">
          <div className="efhc-admin-bank-map-v154_toggles" aria-label="Показатели балансовой карты">
            {bankMapRows.map((row) => (
              <label key={row.key}>
                <input
                  type="checkbox"
                  aria-label={row.label}
                  title={row.label}
                  checked={bankMapVisible[row.key]}
                  onChange={(event) =>
                    setBankMapVisible((current) => ({ ...current, [row.key]: event.target.checked }))
                  }
                />
              </label>
            ))}
          </div>
          <div className="efhc-admin-bank-map-v154_rows">
            {bankMapRows.some((row) => bankMapVisible[row.key]) ? (
              bankMapRows.filter((row) => bankMapVisible[row.key]).map((row) => {
                const amount = amountParts(row.value);
                return (
                  <div className="efhc-admin-bank-map-v154_row" data-series={row.key} key={row.key}>
                    <div className="efhc-admin-bank-map-v154_copy">
                      <strong>{row.label}</strong>
                      <span className="efhc-admin-bank-map-v179_amount">
                        <em className="efhc-admin-bank-map-v179_amount-whole">{integrityReady ? amount.whole : "—"}</em>
                        <em className="efhc-admin-bank-map-v179_amount-fraction">{integrityReady ? amount.fraction : ""}</em>{" "}
                        {row.unit}
                      </span>
                    </div>
                    <div className="efhc-admin-bank-map-v180_indicator">
                      <div className="efhc-admin-bank-map-v154_track" aria-hidden="true">
                        <span style={{ width: percentWidthFromSnapshot(row.percent) }} />
                      </div>
                      <b>{integrityReady ? percentTextFromSnapshot(row.percent, 2) : "—"}</b>
                    </div>
                  </div>
                );
              })
            ) : (
              <div className="text-sm text-[color:var(--tg-hint)]">Выберите хотя бы один показатель.</div>
            )}
          </div>
        </div>
      </AdminSectionCard>

      <AdminSectionCard title="Логи Банка">
        <div className="efhc-admin-export-controls-v445 efhc-admin-bank-log-export-v445" data-admin-bank-log-export="json-csv-xlsx-v445">
          <select
            className="efhc-admin-export-rows-v445"
            value={exportRows}
            onChange={(event) => setExportRows(event.target.value as AdminLogExportRows)}
            disabled={Boolean(exporting)}
            aria-label="Строк экспорта"
          >
            <option value="100">100</option>
            <option value="1000">1 000</option>
            <option value="100000">100 000</option>
            <option value="1000000">1 000 000</option>
            <option value="all">Все</option>
          </select>
          <div className="efhc-admin-bank-export-strip-v444">
            <Button variant="secondary" onClick={() => void exportBankLogs("json")} disabled={Boolean(exporting)} aria-busy={exporting === "json"}>JSON</Button>
            <Button variant="secondary" onClick={() => void exportBankLogs("csv")} disabled={Boolean(exporting)} aria-busy={exporting === "csv"}>CSV</Button>
            <Button variant="secondary" onClick={() => void exportBankLogs("xlsx")} disabled={Boolean(exporting)} aria-busy={exporting === "xlsx"}>XLSX</Button>
          </div>
        </div>
      </AdminSectionCard>
    </AdminPage>
  );
}
