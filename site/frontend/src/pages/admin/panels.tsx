import React, { FormEvent, useEffect, useMemo, useState } from "react";
import type { GlobalId } from "../../types/identity";
import { AdminPage } from "../../components/admin/AdminPage";
import { AdminPanelsObligationsRuntime } from "../../components/admin/AdminPanelsObligationsRuntime";
import { AdminSectionCard } from "../../components/admin/AdminSectionCard";
import { Button } from "../../components/ui/Button";
import { TelegramEmptyState } from "../../components/ui/telegram/TelegramEmptyState";
import { useT } from "../../hooks/useT";
import { ADMIN_PANELS_PANEL_ID_PATH, ADMIN_PANELS_PATH } from "../../lib/api/generated/adminSeams";
import { adminSafeLoadError, adminUiErrorMessage } from "../../lib/adminError";
import { format8 } from "../../lib/format";
import { useAdminPageGlobalIdSelection } from "../../hooks/admin/useAdminPageGlobalIdSelection";
import { useAdminLinkedTransport } from "../../queries/useAdminLinkedTransport";
import { useAdminLogExport } from "../../queries/useAdminLogExport";
import {
  type AdminLogExportFormat,
  type AdminLogExportRows,
} from "../../services/adminLogExport.service";
import type { DbId } from "../../types/db-id";

type PanelMeta = {
  protectively_voided?: boolean | null;
};

type PanelItem = {
  id: DbId;
  public_id: string;
  global_id: GlobalId;
  is_active: boolean;
  state?: string | null;
  meta?: PanelMeta | null;
  protectively_voided?: boolean | null;
  protectively_voided_at?: string | null;
  created_at?: string | null;
  activated_at?: string | null;
  expires_at?: string | null;
  archived_at?: string | null;
  remaining_seconds?: number | null;
  base_gen_per_sec?: string | null;
  generated_kwh: string;
};

type PanelsOut = { ok?: boolean; items?: PanelItem[]; item?: PanelItem; next_cursor?: string | null };

type SearchKind = "global" | "panel";
type SearchContour = "operational" | "dead";

function pad2(value: number): string {
  return value < 10 ? `0${value}` : String(value);
}

function formatUtcMinute(iso: string | null | undefined): string {
  if (!iso) return "—";
  const ms = Date.parse(iso);
  if (Number.isNaN(ms)) return "—";
  const date = new Date(ms);
  return `${pad2(date.getUTCDate())}.${pad2(date.getUTCMonth() + 1)}.${date.getUTCFullYear()} ${pad2(date.getUTCHours())}:${pad2(date.getUTCMinutes())} UTC`;
}

function panelPublicId(panel: PanelItem): string {
  if (typeof panel.public_id === "string" && /^PNL-(?!00000000$)[0-9]{8}$/.test(panel.public_id)) {
    return panel.public_id;
  }
  return "Ошибка целостности PNL";
}

function formatRemaining(seconds: number | null | undefined): string {
  const safe = Math.max(0, Math.floor(Number(seconds || 0)));
  const days = Math.floor(safe / 86400);
  const hours = Math.floor((safe % 86400) / 3600);
  const minutes = Math.floor((safe % 3600) / 60);
  return `${days}д ${hours}ч ${minutes}м`;
}

function parseSearch(raw: string): { kind: SearchKind; value: string } | null {
  const value = raw.trim();
  if (!value) return null;
  if (/^PNL-(?!00000000$)[0-9]{8}$/.test(value)) {
    return { kind: "panel", value };
  }
  if (/^\d{10}$/.test(value)) return { kind: "global", value };
  if (/^\d+$/.test(value)) return { kind: "panel", value };
  return null;
}

function isProtectivelyVoided(panel: PanelItem): boolean {
  return panel.protectively_voided === true || panel.meta?.protectively_voided === true;
}

function AdminPanelCard(props: {
  panel: PanelItem;
  busy: boolean;
  onDeactivate: (panel: PanelItem) => void;
  onReactivate: (panel: PanelItem) => void;
}) {
  const panel = props.panel;
  const dead = isProtectivelyVoided(panel);
  const active = panel.is_active && !dead;
  const activatedIso = panel.activated_at ?? panel.created_at ?? null;
  const deactivatedIso = dead
    ? panel.protectively_voided_at ?? panel.archived_at ?? null
    : panel.archived_at ?? panel.expires_at ?? null;
  return (
    <article
      className={`efhc-admin-panel-row-v188 efhc-admin-panel-search-card-v170 ${dead ? "efhc-admin-panel-dead-v183" : ""}`}
      data-admin-panel-search-card={String(panel.id)}
      data-panel-card={dead ? "dead" : active ? "active" : "archive"}
      data-panel-protective-deactivation="owner-contract-v1"
    >
      <div className="efhc-admin-panel-row-v188_head" data-panel-card-field="panel-id">
        <div className="min-w-0">
          <strong className="tabular-nums">{panelPublicId(panel)}</strong>
          <span>Panel ID {String(panel.id)} · Global ID {String(panel.global_id)}</span>
        </div>
        {dead ? (
          <span className="efhc-admin-panel-dead-status-v183" data-panel-state="dead">Мёртвая</span>
        ) : (
          <span
            className="efhc-panel-activ-status"
            data-status="activ"
            data-active={active ? "true" : "false"}
            data-i18n-fixed-token="Activ"
            aria-label={`Activ ${active ? "ON" : "OFF"}`}
          >
            Activ
          </span>
        )}
      </div>

      <div className="efhc-admin-panel-row-v188_metrics" data-panel-card-contract="date-countdown">
        <div className="efhc-admin-panel-row-v188_metric" data-panel-card-field="activated-at">
          <span>Активация</span>
          <strong className="tabular-nums">{formatUtcMinute(activatedIso)}</strong>
        </div>
        <div className="efhc-admin-panel-row-v188_metric" data-panel-card-field="deactivated-at">
          <span>{dead ? "Защитно деактивирована" : "Деактивация / срок"}</span>
          <strong className="tabular-nums">{formatUtcMinute(deactivatedIso)}</strong>
        </div>
        <div className="efhc-admin-panel-row-v188_metric" data-panel-card-field="generated-kwh">
          <span>Сгенерировано</span>
          <strong className="tabular-nums">{format8(panel.generated_kwh)} kWh</strong>
        </div>
        <div className="efhc-admin-panel-row-v188_metric" data-panel-card-field="remaining-countdown">
          <span>Осталось</span>
          <strong className="efhc-panel-countdown-live tabular-nums">
            {active ? formatRemaining(panel.remaining_seconds) : formatRemaining(0)}
          </strong>
        </div>
      </div>

      {dead ? (
        <div className="efhc-admin-panel-dead-note-v183">
          Исключена из обычных списков и агрегатов; Panel ID и история сохранены.
        </div>
      ) : null}

      <div className="efhc-admin-panel-search-card-v170_action">
        {active ? (
          <Button variant="secondary" className="efhc-admin-panel-deactivate-v170" disabled={props.busy} onClick={() => props.onDeactivate(panel)}>
            {props.busy ? "Деактивация…" : "Защитно деактивировать"}
          </Button>
        ) : dead ? (
          <Button variant="secondary" className="efhc-admin-panel-reactivate-v183" disabled={props.busy} onClick={() => props.onReactivate(panel)}>
            {props.busy ? "Активация…" : "Повторно активировать"}
          </Button>
        ) : (
          <span className="text-xs efhc-text-muted2">Обычная архивная Панель · восстановление не применяется</span>
        )}
      </div>
    </article>
  );
}

export default function AdminPanelsPage() {
  const adminApiRequest = useAdminLinkedTransport();
  const adminLogExport = useAdminLogExport();
  const { selectedGlobalId, restored, rememberGlobalId, clearGlobalId } = useAdminPageGlobalIdSelection("panels");
  const t = useT();
  const [searchTerm, setSearchTerm] = useState("");
  const [searchContour, setSearchContour] = useState<SearchContour>("operational");
  const [results, setResults] = useState<PanelItem[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [operationNotice, setOperationNotice] = useState("");
  const [exportError, setExportError] = useState("");
  const [exporting, setExporting] = useState<AdminLogExportFormat | null>(null);
  const [exportRows, setExportRows] = useState<AdminLogExportRows>("100000");

  async function loadPanelById(panelId: string, contour: SearchContour): Promise<PanelItem | null> {
    // EFHC_Bot_v174.63: direct Admin read is dead-capable without include_dead query.
    const path = ADMIN_PANELS_PANEL_ID_PATH.replace("{panel_id}", panelId);
    const data = await adminApiRequest<PanelsOut | PanelItem>(path, "GET");
    const envelope = data as PanelsOut;
    const direct = data as PanelItem;
    const item = envelope.item ?? (Array.isArray(envelope.items) ? envelope.items[0] : undefined) ?? (direct && typeof direct === "object" && "id" in direct ? direct : undefined);
    if (!item) return null;
    const dead = isProtectivelyVoided(item);
    if (contour === "dead" ? !dead : dead) return null;
    return item;
  }

  async function searchPanels(event?: FormEvent, contourOverride?: SearchContour, rawTerm?: string) {
    event?.preventDefault();
    const parsed = parseSearch(rawTerm ?? searchTerm);
    const contour = contourOverride ?? searchContour;
    if (!parsed) {
      setResults([]);
      setSearchError("Введите 10-значный Global ID или PNL-00000001.");
      return;
    }
    setSearchLoading(true);
    setSearchError("");
    setOperationNotice("");
    setResults([]);
    try {
      if (parsed.kind === "global") {
        if (contour === "dead") {
          throw new Error(
            "EFHC_Bot_v174.63 не публикует список мёртвых Панелей по Global ID. Для контура «Мёртвые» используйте точный Panel ID; поиск по Global ID безопасно заблокирован до появления серверного контракта.",
          );
        }
        const loaded: PanelItem[] = [];
        let cursor: string | null = null;
        do {
          const params = new URLSearchParams({ global_id: parsed.value, limit: "20" });
          if (cursor) params.set("cursor", cursor);
          const data = await adminApiRequest<PanelsOut>(`${ADMIN_PANELS_PATH}?${params.toString()}`, "GET");
          const rows = Array.isArray(data.items) ? data.items : [];
          for (const row of rows) {
            if (!isProtectivelyVoided(row) && !loaded.some((current) => String(current.id) === String(row.id))) {
              loaded.push(row);
            }
          }
          cursor = data.next_cursor || null;
        } while (cursor);
        setResults(loaded);
        if (loaded.length === 0) {
          setSearchError(`У Global ID ${parsed.value} Панели не найдены.`);
        } else {
          rememberGlobalId(parsed.value);
        }
      } else {
        const item = await loadPanelById(parsed.value, contour);
        if (!item) throw new Error(contour === "dead" ? "Мёртвая Панель не найдена в Admin dead contour." : "Панель не найдена в обычном contour.");
        setResults([item]);
        rememberGlobalId(String(item.global_id));
      }
    } catch (error: unknown) {
      setResults([]);
      setSearchError(adminSafeLoadError(error, t));
    } finally {
      setSearchLoading(false);
    }
  }


  useEffect(() => {
    if (!restored || !selectedGlobalId) return;
    const remembered = String(selectedGlobalId);
    setSearchTerm(remembered);
    void searchPanels(undefined, "operational", remembered);
  }, [restored]);

  function resetSearch() {
    clearGlobalId();
    setSearchTerm("");
    setResults([]);
    setSearchError("");
    setOperationNotice("");
  }

  async function protectiveDeactivate(panel: PanelItem) {
    const reason = window.prompt("Причина защитной деактивации", "Защитная ручная деактивация");
    if (!reason?.trim()) return;
    setOperationNotice("");
    setSearchError(
      `${panelPublicId(panel)}: деактивация недоступна — сервис не принимает обязательную причину. Данные не изменены.`,
    );
  }

  async function reactivateDeadPanel(panel: PanelItem) {
    const reason = window.prompt("Причина повторной активации", "Повторная активация мёртвой Панели");
    if (!reason?.trim()) return;
    setOperationNotice("");
    setSearchError(
      `${panelPublicId(panel)}: повторная активация недоступна — сервис не принимает обязательную причину. Данные не изменены.`,
    );
  }

  async function exportPanelLogs(format: AdminLogExportFormat) {
    if (exporting) return;
    setExporting(format);
    setExportError("");
    try {
      await adminLogExport.mutateAsync({
        scope: "panels",
        format,
        rows: exportRows,
        globalId: selectedGlobalId || null,
      });
    } catch (e: unknown) {
      setExportError(adminUiErrorMessage(e, t));
    } finally {
      setExporting(null);
    }
  }

  return (
    <AdminPage
      refreshBankSnapshot={false}
      title={t("admin.panels")}
      backHref="/admin"
    >
      <AdminPanelsObligationsRuntime />

      <AdminSectionCard
        title="Панели"
        subtitle="Global ID показывает активные Панели; Panel ID открывает точную Панель, включая мёртвую. Поиск мёртвых Панелей по Global ID пока недоступен."
      >
        <div
          className="mb-3 flex flex-wrap items-center justify-between gap-x-5 gap-y-1 rounded-xl border px-3 py-2 text-sm"
          data-admin-panels-result-line="v190"
        >
          <span>
            <span className="efhc-text-muted">Контур:</span>{" "}
            <strong>{searchContour === "dead" ? "Мёртвые" : "Панели"}</strong>
          </span>
          <span>
            <span className="efhc-text-muted">Результат:</span>{" "}
            <strong>{searchLoading ? "поиск…" : `найдено ${results.length}`}</strong>
          </span>
        </div>
        <div className="efhc-admin-panels-control-v442">
        <div className="efhc-admin-panels-contour-v183 efhc-admin-panels-contour-v442" role="group" aria-label="Контур поиска Панелей">
          <Button
            variant={searchContour === "operational" ? "primary" : "secondary"}
            onClick={() => {
              setSearchContour("operational");
              setResults([]);
              setSearchError("");
              setOperationNotice("");
            }}
          >
            Панели
          </Button>
          <Button
            variant={searchContour === "dead" ? "primary" : "secondary"}
            onClick={() => {
              setSearchContour("dead");
              setResults([]);
              setSearchError("");
              setOperationNotice("");
            }}
          >
            Мёртвые
          </Button>
        </div>

        <form
          className="efhc-admin-panels-search-v170 grid grid-cols-2 gap-2"
          data-eam-family="EAM-ADMIN-021"
          data-admin-selected-global-id={selectedGlobalId || "none"}
          data-admin-search-geometry="v425-v430"
          data-admin-panels-global-search-scope="v442"
          onSubmit={(event) => void searchPanels(event)}
          style={{ gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: ".45rem" }}
        >
          <label style={{ gridColumn: "1 / -1" }}>
            <span className="efhc-admin-panels-global-id-label-v442">Global ID или Panel ID</span>
            <input
              value={searchTerm}
              onChange={(event) => setSearchTerm(event.target.value)}
              placeholder="0000000001 или PNL-00000001"
              autoComplete="off"
              style={{ minHeight: "2.25rem", padding: ".52rem .62rem", borderRadius: ".68rem" }}
            />
          </label>
          <Button
            className="w-full min-w-0"
            type="button"
            variant="secondary"
            disabled={searchLoading || (!searchTerm && !selectedGlobalId)}
            onClick={resetSearch}
            style={{ minHeight: "2.25rem", padding: ".52rem .68rem", borderRadius: ".68rem" }}
          >
            Сбросить
          </Button>
          <Button
            className="w-full min-w-0"
            type="submit"
            disabled={searchLoading}
            style={{ minHeight: "2.25rem", padding: ".52rem .68rem", borderRadius: ".68rem" }}
          >
            {searchLoading ? "Поиск…" : "Найти"}
          </Button>
        </form>
        </div>

        <div className="efhc-admin-panels-protection-note-v170">
          {searchContour === "dead"
            ? "Мёртвая Панель сохраняет Panel ID и историю, имеет generated_kwh = 0.00000000 и не участвует в обычных списках и сводках. Повторная активация: списание 100 EFHC по порядку EFHCb → EFHCm → конвертация недостающих kWh в EFHCm → списание EFHCm."
            : "Защитная деактивация: новая проводка списания ровно 100 EFHC. Порядок EFHCb → EFHCm → конвертация недостающих kWh в EFHCm → списание EFHCm; без долга и возврата задним числом. Сервер аннулирует генерацию Панели, сохраняет прежние проводки и историю; браузер не пересчитывает суммы."}
        </div>

        {operationNotice ? <div className="efhc-admin-panel-operation-notice-v183">{operationNotice}</div> : null}
        {searchError ? <TelegramEmptyState title="Проверка Панели" detail={searchError} /> : null}
        {results.length > 0 ? (
          <div className="efhc-admin-panels-results-v188" data-admin-panel-search-results="real-panel-cards">
            {results.map((panel) => (
              <AdminPanelCard
                key={String(panel.id)}
                panel={panel}
                busy={false}
                onDeactivate={(item) => void protectiveDeactivate(item)}
                onReactivate={(item) => void reactivateDeadPanel(item)}
              />
            ))}
          </div>
        ) : null}
      </AdminSectionCard>

      <AdminSectionCard
        title="Логи Панелей"
      >
        <div className="efhc-admin-export-controls-v445 efhc-admin-panels-export-v442" data-admin-panels-log-export="json-csv-txt-xlsx-v445" data-admin-panels-export-transport="server-log-export">
          <select className="efhc-admin-export-rows-v445" value={exportRows} onChange={(event) => setExportRows(event.target.value as AdminLogExportRows)} disabled={Boolean(exporting)} aria-label="Строк экспорта">
            <option value="100">100</option>
            <option value="1000">1 000</option>
            <option value="100000">100 000</option>
            <option value="1000000">1 000 000</option>
            <option value="all">Все</option>
          </select>
          <div className="efhc-admin-panels-export-strip-v442">
            {(["json", "csv", "txt", "xlsx"] as AdminLogExportFormat[]).map((format) => (
              <Button
                key={format}
                className="w-full min-w-0"
                variant="secondary"
                onClick={() => void exportPanelLogs(format)}
                disabled={Boolean(exporting)}
                aria-busy={exporting === format}
              >
                {format.toUpperCase()}
              </Button>
            ))}
          </div>
        </div>
        {exportError ? <TelegramEmptyState title="Не удалось скачать логи Панелей" detail={exportError || undefined} /> : null}
      </AdminSectionCard>
    </AdminPage>
  );
}
