import React, { useMemo, useState } from "react";
import {
  AdminActionTable,
  AdminChartCard,
  AdminEmptyState,
  AdminFlowMapCard,
  AdminSectionHeader,
  AdminStatusBadge,
} from "./AdminDashboardUiKit";

type Overview = {
  ok: boolean;
  ts: string;
  counters: Record<string, number>;
  facts?: Record<string, string>;
  notes?: string | null;
};

type ExportFormat = "json" | "csv" | "txt";
type ExportScope = "overview" | "counters" | "facts";

type ExportRow = {
  section: string;
  key: string;
  value: string;
};

type Props = {
  overview: Overview | null;
  loading: boolean;
  onRefresh: () => void;
};

const FORMAT_LABELS: Record<ExportFormat, string> = {
  json: "JSON",
  csv: "CSV",
  txt: "TXT",
};

function normalizeValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}

function buildRows(
  overview: Overview | null,
  scope: ExportScope,
  includeNotes: boolean,
): ExportRow[] {
  if (!overview) return [];
  const rows: ExportRow[] = [
    { section: "meta", key: "ok", value: normalizeValue(overview.ok) },
    { section: "meta", key: "ts", value: normalizeValue(overview.ts) },
  ];

  if (scope === "overview" || scope === "counters") {
    Object.entries(overview.counters || {}).forEach(([key, value]) => {
      rows.push({
        section: "counters",
        key,
        value: normalizeValue(value),
      });
    });
  }

  if (scope === "overview" || scope === "facts") {
    Object.entries(overview.facts || {}).forEach(([key, value]) => {
      rows.push({
        section: "facts",
        key,
        value: normalizeValue(value),
      });
    });
  }

  if (includeNotes) {
    rows.push({
      section: "notes",
      key: "notes",
      value: normalizeValue(overview.notes || ""),
    });
  }

  return rows;
}

function csvCell(value: string): string {
  return `"${value.replace(/"/g, '""')}"`;
}

function rowsToCsv(rows: ExportRow[]): string {
  const head = ["section", "key", "value"].map(csvCell).join(",");
  const body = rows.map((row) => (
    [row.section, row.key, row.value].map(csvCell).join(",")
  ));
  return [head, ...body].join("\n");
}

function rowsToText(rows: ExportRow[]): string {
  return rows.map((row) => (
    `${row.section}.${row.key}: ${row.value}`
  )).join("\n");
}

function rowsToJson(rows: ExportRow[], overview: Overview | null): string {
  return JSON.stringify({
    kind: "efhc_admin_reports_export",
    generated_at: new Date().toISOString(),
    source_ts: overview?.ts || null,
    rows,
  }, null, 2);
}

function buildFileBody(
  rows: ExportRow[],
  format: ExportFormat,
  overview: Overview | null,
): string {
  if (format === "csv") return rowsToCsv(rows);
  if (format === "txt") return rowsToText(rows);
  return rowsToJson(rows, overview);
}

function contentType(format: ExportFormat): string {
  if (format === "csv") return "text/csv;charset=utf-8";
  if (format === "txt") return "text/plain;charset=utf-8";
  return "application/json;charset=utf-8";
}

function fileName(format: ExportFormat, overview: Overview | null): string {
  const safeTs = (overview?.ts || new Date().toISOString())
    .replace(/[^0-9A-Za-z]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 48);
  return `efhc-admin-reports-${safeTs}.${format}`;
}

function downloadText(
  body: string,
  format: ExportFormat,
  overview: Overview | null,
): void {
  if (typeof window === "undefined") return;
  const blob = new Blob([body], { type: contentType(format) });
  const url = window.URL.createObjectURL(blob);
  const link = window.document.createElement("a");
  link.href = url;
  link.download = fileName(format, overview);
  window.document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

export function AdminReportsExportDownloadPanel(props: Props) {
  const [format, setFormat] = useState<ExportFormat>("json");
  const [scope, setScope] = useState<ExportScope>("overview");
  const [includeNotes, setIncludeNotes] = useState(true);
  const rows = useMemo(() => buildRows(
    props.overview,
    scope,
    includeNotes,
  ), [props.overview, scope, includeNotes]);
  const disabled = !props.overview || props.loading || rows.length === 0;
  const previewRows = rows.slice(0, 4);
  const body = useMemo(() => buildFileBody(
    rows,
    format,
    props.overview,
  ), [rows, format, props.overview]);

  function handleDownload(): void {
    if (disabled) return;
    downloadText(body, format, props.overview);
  }

  return (
    <section
      className="efhc-admin-reports-export"
      data-admin-sandbox-source="refine useExport; ExportButton; tma downloadFile"
    >
      <AdminSectionHeader
        eyebrow="Отчёты"
        title="Экспорт отчётов"
        subtitle={
          "Администратор может выгрузить подготовленный отчёт " +
          "в одном из доступных форматов."
        }
        actions={
          <button
            type="button"
            className="efhc-admin-live-dashboard_live"
            onClick={props.onRefresh}
            disabled={props.loading}
          >
            {props.loading ? "Обновление" : "Обновить перед экспортом"}
          </button>
        }
      />

      <div className="efhc-admin-reports-export_grid">
        <AdminChartCard
          title="Формат выгрузки"
          subtitle="Выберите формат файла и содержание отчёта."
          meta={<AdminStatusBadge label={FORMAT_LABELS[format]} />}
        >
          <div className="efhc-admin-reports-export_chips">
            {(["json", "csv", "txt"] as ExportFormat[]).map((item) => (
              <button
                aria-pressed={format === item}
                data-active={format === item ? "true" : "false"}
                key={item}
                onClick={() => setFormat(item)}
                type="button"
              >
                {FORMAT_LABELS[item]}
              </button>
            ))}
          </div>
          <div className="efhc-admin-reports-export_chips">
            {(["overview", "counters", "facts"] as ExportScope[]).map((item) => (
              <button
                aria-pressed={scope === item}
                data-active={scope === item ? "true" : "false"}
                key={item}
                onClick={() => setScope(item)}
                type="button"
              >
                {item === "overview" ? "Общая сводка" : item === "counters" ? "Счётчики" : "Факты"}
              </button>
            ))}
          </div>
          <label className="efhc-admin-reports-export_toggle">
            <input
              checked={includeNotes}
              onChange={(event) => setIncludeNotes(event.target.checked)}
              type="checkbox"
            />
            <span>Включить примечания</span>
          </label>
        </AdminChartCard>

        <AdminChartCard
          title="Скачать отчёт"
          subtitle="Скачать подготовленный отчёт"
          meta={
            <AdminStatusBadge
              label={disabled ? "нет данных" : `${rows.length} записей`}
              tone={disabled ? "warning" : "success"}
            />
          }
        >
          <AdminFlowMapCard
            title="Порядок экспорта"
            nodes={[
              {
                label: "1. Данные",
                value: props.overview?.ok ? "Готовы" : "Нет данных",
                hint: "Обновите отчёт перед выгрузкой",
                active: Boolean(props.overview?.ok),
              },
              {
                label: "2. Содержание",
                value: scope === "overview" ? "Общая сводка" : scope === "counters" ? "Счётчики" : "Факты",
                hint: "Выбранная часть отчёта",
                active: true,
              },
              {
                label: "3. Формат",
                value: FORMAT_LABELS[format],
                hint: "json / csv / txt",
                active: true,
              },
              {
                label: "4. Скачивание",
                value: disabled ? "Недоступно" : "Готово",
                hint: "Файл будет сохранён на устройство",
                active: !disabled,
              },
            ]}
          />
          <button
            className="efhc-admin-reports-export_download"
            disabled={disabled}
            onClick={handleDownload}
            type="button"
          >
            Скачать {FORMAT_LABELS[format]}
          </button>
        </AdminChartCard>
      </div>

      {props.overview ? (
        <AdminActionTable
          title="Предпросмотр выгрузки"
          rows={previewRows.map((row, index) => ({
            label: `Показатель ${index + 1}`,
            value: row.value || "—",
            hint: "Значение в выбранной части отчёта",
          }))}
        />
      ) : (
        <AdminEmptyState
          title="Нет данных для экспорта"
          text="Сначала обновите отчёт, затем скачайте файл в формате JSON, CSV или TXT."
        />
      )}
    </section>
  );
}
