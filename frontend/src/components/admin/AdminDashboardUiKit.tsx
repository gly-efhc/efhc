import React from "react";

import { AdminListExpandControl, useAdminListWindow } from "./AdminListWindow";

import {
  DashboardFilterBar,
  DashboardFilterGroup,
  DashboardVariableBar,
} from "../dashboard/DashboardFilters";
import {
  DashboardFreshnessBadge,
  DashboardRefreshPicker,
  DashboardTimeRangePicker,
  DashboardToolbar,
} from "../dashboard/DashboardToolbar";
import {
  DashboardActivityStrip,
  DashboardMiniAreaChart,
  DashboardMiniBarChart,
  DashboardMiniSparkline,
} from "../dashboard/MiniCharts";
import { PanelChrome } from "../dashboard/PanelChrome";
import { DashboardProgressBar } from "../dashboard/ProgressSystem";

import type {
  DashboardComponentContract,
  DashboardPanelStatus,
  DashboardPanelTone,
} from "../../lib/dashboard/componentContract";

export type AdminUiTone =
  | "primary"
  | "success"
  | "warning"
  | "neutral"
  | "danger"
  | "info";

type FilterOption = {
  key: string;
  label: React.ReactNode;
  description?: React.ReactNode;
  disabled?: boolean;
};

type FilterGroup = {
  key?: string;
  label: React.ReactNode;
  value: string;
  options: FilterOption[];
  onChange: (value: string) => void;
  queryKey?: string;
  querySync?: "disabled" | "safe_display_only";
};

type AdminFilterBarProps = React.PropsWithChildren<{
  groups: FilterGroup[];
  resetLabel?: React.ReactNode;
  onReset?: () => void;
  className?: string;
}>;

type AdminSingleFilterProps = {
  label?: React.ReactNode;
  value: string;
  options: FilterOption[];
  onChange: (value: string) => void;
  queryKey?: string;
  querySync?: "disabled" | "safe_display_only";
};

type FlowNode = {
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
  active?: boolean;
  onClick?: () => void;
};

type ActionRow = {
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
};

type AdminDashboardShellProps = React.PropsWithChildren<{
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  actions?: React.ReactNode;
  contract?: DashboardComponentContract;
}>;

type AdminDashboardToolbarProps = React.PropsWithChildren<{
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  breadcrumb?: React.ReactNode;
  timeRange?: React.ReactNode;
  refresh?: React.ReactNode;
  updatedAt?: React.ReactNode;
  filters?: React.ReactNode;
  freshness?: React.ReactNode;
  actions?: React.ReactNode;
}>;

type AdminTimeRangePickerProps = React.ComponentProps<
  typeof DashboardTimeRangePicker
>;

type AdminRefreshPickerProps = React.ComponentProps<
  typeof DashboardRefreshPicker
>;

type AdminFreshnessBadgeProps = React.ComponentProps<
  typeof DashboardFreshnessBadge
>;

type AdminPanelChromeProps = React.PropsWithChildren<{
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  status?: DashboardPanelStatus;
  tone?: DashboardPanelTone;
  updatedAt?: React.ReactNode;
  source?: React.ReactNode;
  actions?: React.ReactNode;
  footer?: React.ReactNode;
  contract?: DashboardComponentContract;
}>;


type AdminMiniSparklineProps = React.ComponentProps<
  typeof DashboardMiniSparkline
>;

type AdminMiniAreaChartProps = React.ComponentProps<
  typeof DashboardMiniAreaChart
>;

type AdminMiniBarChartProps = React.ComponentProps<
  typeof DashboardMiniBarChart
>;

type AdminActivityStripProps = React.ComponentProps<
  typeof DashboardActivityStrip
>;

type AdminStatusCardProps = {
  label: React.ReactNode;
  value: React.ReactNode;
  status?: DashboardPanelStatus;
  tone?: AdminUiTone;
  hint?: React.ReactNode;
};

type AdminTrendCardProps = {
  label: React.ReactNode;
  value: React.ReactNode;
  delta?: React.ReactNode;
  hint?: React.ReactNode;
  tone?: AdminUiTone;
};

function adminNodeToText(
  value: React.ReactNode,
  fallback = "dashboard element",
): string {
  if (typeof value === "string") return value;
  if (typeof value === "number") return String(value);
  if (Array.isArray(value)) {
    const text = value
      .map((item) => adminNodeToText(item, ""))
      .filter(Boolean)
      .join(" ");
    return text || fallback;
  }
  return fallback;
}

function toneClass(tone: AdminUiTone | undefined): string {
  if (tone === "success") return "efhc-admin-ui-tone--success";
  if (tone === "warning") return "efhc-admin-ui-tone--warning";
  if (tone === "danger") return "efhc-admin-ui-tone--danger";
  if (tone === "info") return "efhc-admin-ui-tone--info";
  if (tone === "neutral") return "efhc-admin-ui-tone--neutral";
  return "efhc-admin-ui-tone--primary";
}

function statusClass(status: DashboardPanelStatus | undefined): string {
  if (status === "loading") return "is-loading";
  if (status === "empty") return "is-empty";
  if (status === "error") return "is-error";
  if (status === "stale") return "is-stale";
  return "is-success";
}

export function AdminDashboardShell(props: AdminDashboardShellProps) {
  return (
    <section
      aria-label={adminNodeToText(props.title, "EFHC Admin Dashboard")}
      className="efhc-admin-dashboard-shell efhc-dashboard-surface"
      data-admin-accessibility-overflow-qa="1494"
      data-admin-dashboard-shell="1461"
      data-dashboard-contract={props.contract?.id ?? "admin-dashboard-shell"}
      role="region"
    >
      <header className="efhc-admin-dashboard-shell__header">
        <div>
          <p className="efhc-admin-dashboard-eyebrow">Административная панель</p>
          <h1>{props.title}</h1>
          {props.subtitle ? <p>{props.subtitle}</p> : null}
        </div>
        {props.actions ? (
          <div className="efhc-admin-dashboard-shell__actions">
            {props.actions}
          </div>
        ) : null}
      </header>
      <div className="efhc-admin-dashboard-shell__body">{props.children}</div>
    </section>
  );
}

export function AdminDashboardPage(props: AdminDashboardShellProps) {
  return <AdminDashboardShell {...props}>{props.children}</AdminDashboardShell>;
}

export function AdminDashboardToolbar(props: AdminDashboardToolbarProps) {
  return (
    <DashboardToolbar
      actions={props.actions}
      breadcrumb={props.breadcrumb}
      className="efhc-admin-dashboard-toolbar"
      filters={props.filters}
      freshness={props.freshness}
      mode="admin"
      refresh={props.refresh}
      subtitle={props.subtitle}
      timeRange={props.timeRange}
      title={props.title}
      updatedAt={props.updatedAt}
    >
      {props.children}
    </DashboardToolbar>
  );
}

export function AdminTimeRangePicker(props: AdminTimeRangePickerProps) {
  return <DashboardTimeRangePicker {...props} mode="admin" />;
}

export function AdminRefreshPicker(props: AdminRefreshPickerProps) {
  return <DashboardRefreshPicker {...props} mode="admin" />;
}

export function AdminFreshnessBadge(props: AdminFreshnessBadgeProps) {
  return <DashboardFreshnessBadge {...props} mode="admin" />;
}

export function AdminDashboardGrid(props: React.PropsWithChildren) {
  return (
    <div
      className="efhc-admin-dashboard-grid efhc-dashboard-grid"
      data-admin-accessibility-overflow-qa="1494"
      data-admin-dashboard-grid="1461"
    >
      {props.children}
    </div>
  );
}

export function AdminPanelStatus(props: {
  status?: DashboardPanelStatus;
  label: React.ReactNode;
}) {
  return (
    <span
      aria-label={adminNodeToText(props.label, "panel status")}
      className={`efhc-admin-panel-status ${statusClass(props.status)}`}
      data-admin-accessibility-overflow-qa="1494"
      data-admin-panel-status="1461"
      role="status"
    >
      {props.label}
    </span>
  );
}

export function AdminPanelHeader(props: {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  status?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <div className="efhc-admin-panel-header" data-admin-panel-header="1461">
      <div>
        <h3>{props.title}</h3>
        {props.subtitle ? <p>{props.subtitle}</p> : null}
      </div>
      <div className="efhc-admin-panel-header__right">
        {props.status}
        {props.actions}
      </div>
    </div>
  );
}

export function AdminPanelBody(props: React.PropsWithChildren) {
  return (
    <div className="efhc-admin-panel-body" data-admin-panel-body="1461">
      {props.children}
    </div>
  );
}

export function AdminPanelFooter(props: React.PropsWithChildren) {
  return (
    <footer className="efhc-admin-panel-footer" data-admin-panel-footer="1461">
      {props.children}
    </footer>
  );
}

export function AdminPanelChrome(props: AdminPanelChromeProps) {
  const tone = props.tone ?? "neutral";
  return (
    <PanelChrome
      actions={props.actions}
      className={`efhc-admin-panel-chrome ${toneClass(tone)}`}
      contract={props.contract}
      dataMarker="admin-panel-chrome"
      footer={props.footer}
      mode="admin"
      status={props.status}
      statusLabel={
        props.status ? (
          <AdminPanelStatus label={props.status} status={props.status} />
        ) : null
      }
      subtitle={props.subtitle}
      title={props.title}
      tone={tone}
      updatedAt={props.updatedAt}
    >
      {props.children}
    </PanelChrome>
  );
}


export function AdminProgressBar(props: React.ComponentProps<
  typeof DashboardProgressBar
>) {
  return (
    <DashboardProgressBar
      {...props}
      dataKind={props.dataKind ?? "derived"}
      source={undefined}
    />
  );
}

export function AdminStatusCard(props: AdminStatusCardProps) {
  return (
    <article
      className={`efhc-admin-status-card ${toneClass(props.tone)}`}
      data-admin-status-card="1461"
      data-status={props.status ?? "success"}
    >
      <span>{props.label}</span>
      <strong>{props.value}</strong>
      {props.hint ? <small>{props.hint}</small> : null}
    </article>
  );
}

export function AdminTrendCard(props: AdminTrendCardProps) {
  return (
    <article
      className={`efhc-admin-trend-card ${toneClass(props.tone)}`}
      data-admin-trend-card="1461"
    >
      <span>{props.label}</span>
      <strong>{props.value}</strong>
      {props.delta ? <b>{props.delta}</b> : null}
      {props.hint ? <small>{props.hint}</small> : null}
    </article>
  );
}

export function AdminPanelInspectorDrawer(
  props: React.PropsWithChildren<{
    title: React.ReactNode;
    open?: boolean;
    source?: React.ReactNode;
    closeLabel?: React.ReactNode;
  }>,
) {
  return (
    <aside
      className="efhc-admin-panel-inspector"
      data-admin-panel-inspector="1461"
      data-open={props.open ? "true" : "false"}
    >
      <div className="efhc-admin-panel-inspector__head">
        <strong>{props.title}</strong>
        {props.closeLabel ? <span>{props.closeLabel}</span> : null}
      </div>
      <div>{props.children}</div>
    </aside>
  );
}

export function AdminSectionHeader(props: {
  eyebrow?: React.ReactNode;
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <div
      className="efhc-admin-ui-section-header"
      data-admin-ui-kit-section-header="1326"
    >
      <div>
        {props.eyebrow ? (
          <div className="efhc-admin-ui-eyebrow">{props.eyebrow}</div>
        ) : null}
        <h2>{props.title}</h2>
        {props.subtitle ? <p>{props.subtitle}</p> : null}
      </div>
      {props.actions ? (
        <div className="efhc-admin-ui-section-header_actions">
          {props.actions}
        </div>
      ) : null}
    </div>
  );
}

export function AdminStatusBadge(props: {
  label: React.ReactNode;
  tone?: AdminUiTone;
}) {
  return (
    <span
      aria-label={adminNodeToText(props.label, "status badge")}
      className={`efhc-admin-ui-status ${toneClass(props.tone)}`}
      data-admin-accessibility-overflow-qa="1494"
      data-admin-ui-kit-status-badge="1326"
      data-admin-primitive="badge"
      role="status"
    >
      {props.label}
    </span>
  );
}

export function AdminKpiCard(props: {
  instanceId?: string;
  eamFamily?: string;
  visualPrimitive?: string;
  label: React.ReactNode;
  value: React.ReactNode;
  meta?: React.ReactNode;
  hint?: React.ReactNode;
  tone?: AdminUiTone;
}) {
  return (
    <article
      aria-label={[
        adminNodeToText(props.label, "KPI"),
        adminNodeToText(props.value, "value"),
      ].join(": ")}
      className={`efhc-admin-ui-kpi ${toneClass(props.tone)}`}
      data-admin-accessibility-overflow-qa="1494"
      data-admin-ui-kit-kpi-card="1326"
      data-admin-primitive="kpi"
      data-admin-visual-primitive={props.visualPrimitive}
      data-eam-family={props.eamFamily}
      data-admin-instance={props.instanceId}
      data-admin-tone={props.tone ?? "primary"}
    >
      <div className="efhc-admin-ui-kpi_label">{props.label}</div>
      <div className="efhc-admin-ui-kpi_value">{props.value}</div>
      {props.meta ? (
        <div className="efhc-admin-ui-kpi_meta">{props.meta}</div>
      ) : null}
      {props.hint ? (
        <div className="efhc-admin-ui-kpi_hint">{props.hint}</div>
      ) : null}
    </article>
  );
}

export function AdminSparkline(props: AdminMiniSparklineProps) {
  return <DashboardMiniSparkline {...props} dataKind="derived" source={undefined} />;
}

export function AdminAreaChart(props: AdminMiniAreaChartProps) {
  return <DashboardMiniAreaChart {...props} dataKind="derived" source={undefined} />;
}

export function AdminMiniBarChart(props: AdminMiniBarChartProps) {
  return <DashboardMiniBarChart {...props} dataKind="derived" source={undefined} />;
}

export function AdminHeatStrip(props: AdminActivityStripProps) {
  return <DashboardActivityStrip {...props} dataKind="derived" source={undefined} />;
}

export function AdminChartCard(
  props: React.PropsWithChildren<{
    title: React.ReactNode;
    subtitle?: React.ReactNode;
    meta?: React.ReactNode;
  }>,
) {
  return (
    <section
      className="efhc-admin-ui-chart-card"
      data-admin-ui-kit-chart-card="1326"
    >
      <div className="efhc-admin-ui-chart-card_head">
        <div>
          <div className="efhc-admin-ui-chart-card_title">{props.title}</div>
          {props.subtitle ? (
            <div className="efhc-admin-ui-chart-card_subtitle">
              {props.subtitle}
            </div>
          ) : null}
        </div>
        {props.meta ? <div>{props.meta}</div> : null}
      </div>
      <div className="efhc-admin-ui-chart-card_body">{props.children}</div>
    </section>
  );
}

export function AdminVariableBar(props: AdminFilterBarProps) {
  return (
    <DashboardVariableBar
      className={`efhc-admin-dashboard-variable-bar ${props.className ?? ""}`}
      groups={props.groups}
      mode="admin"
      onReset={props.onReset}
      resetLabel={props.resetLabel}
    >
      {props.children}
    </DashboardVariableBar>
  );
}

export function AdminFilterBar(props: AdminFilterBarProps) {
  return (
    <DashboardFilterBar
      className={[
        "efhc-admin-ui-filter-bar",
        "efhc-admin-dashboard-filter-bar",
        props.className ?? "",
      ].join(" ")}
      groups={props.groups}
      mode="admin"
      onReset={props.onReset}
      resetLabel={props.resetLabel}
    >
      {props.children}
    </DashboardFilterBar>
  );
}

function buildAdminFilterGroup(
  key: string,
  kind: "status" | "operation_type" | "date_range" | "route",
  fallbackLabel: React.ReactNode,
  props: AdminSingleFilterProps,
) {
  return {
    key,
    kind,
    label: props.label ?? fallbackLabel,
    onChange: props.onChange,
    options: props.options,
    queryKey: props.queryKey,
    querySync: props.querySync ?? "disabled",
    value: props.value,
  };
}

export function AdminStatusFilter(props: AdminSingleFilterProps) {
  return (
    <DashboardFilterGroup
      group={buildAdminFilterGroup(
        "admin-status",
        "status",
        "Status",
        props,
      )}
      mode="admin"
    />
  );
}

export function AdminOperationTypeFilter(props: AdminSingleFilterProps) {
  return (
    <DashboardFilterGroup
      group={buildAdminFilterGroup(
        "admin-operation-type",
        "operation_type",
        "Operation type",
        props,
      )}
      mode="admin"
    />
  );
}

export function AdminDateRangeFilter(props: AdminSingleFilterProps) {
  return (
    <DashboardFilterGroup
      group={buildAdminFilterGroup(
        "admin-date-range",
        "date_range",
        "Date range",
        props,
      )}
      mode="admin"
    />
  );
}

export function AdminRouteFilter(props: AdminSingleFilterProps) {
  return (
    <DashboardFilterGroup
      group={buildAdminFilterGroup("admin-route", "route", "Route", props)}
      mode="admin"
    />
  );
}

export function AdminFlowMapCard(props: {
  title?: React.ReactNode;
  nodes: FlowNode[];
}) {
  return (
    <section
      aria-label={adminNodeToText(props.title, "admin flow map")}
      className="efhc-admin-ui-flow-map"
      data-admin-accessibility-overflow-qa="1494"
      data-admin-ui-kit-flow-map-card="1326"
      role="group"
    >
      {props.title ? (
        <div className="efhc-admin-ui-flow-map_title">{props.title}</div>
      ) : null}
      <div className="efhc-admin-ui-flow-map_grid">
        {props.nodes.map((node) => {
          const content = (
            <>
              <span>{node.label}</span>
              <strong>{node.value}</strong>
              {node.hint ? <small>{node.hint}</small> : null}
            </>
          );
          if (node.onClick) {
            return (
              <button
                key={node.label}
                type="button"
                className="efhc-admin-ui-flow-map_node"
                data-active={node.active ? "true" : "false"}
                onClick={node.onClick}
              >
                {content}
              </button>
            );
          }
          return (
            <div
              key={node.label}
              className="efhc-admin-ui-flow-map_node"
              data-active={node.active ? "true" : "false"}
            >
              {content}
            </div>
          );
        })}
      </div>
    </section>
  );
}

export function AdminActionTable(props: {
  title?: React.ReactNode;
  rows: ActionRow[];
}) {
  return (
    <div
      aria-label={adminNodeToText(props.title, "admin action table")}
      className="efhc-admin-ui-action-table"
      data-admin-accessibility-overflow-qa="1494"
      data-admin-ui-kit-action-table="1326"
      role="group"
    >
      {props.title ? <strong>{props.title}</strong> : null}
      {props.rows.map((row) => (
        <div className="efhc-admin-ui-action-table_row" key={row.label}>
          <span>{row.label}</span>
          <b>{row.value}</b>
          {row.hint ? <small>{row.hint}</small> : null}
        </div>
      ))}
    </div>
  );
}

export function AdminConfirmationBlock(props: {
  title: React.ReactNode;
  text: React.ReactNode;
  confirmed?: boolean;
}) {
  return (
    <div
      className="efhc-admin-ui-confirmation"
      data-admin-ui-kit-confirmation-block="1326"
      data-confirmed={props.confirmed ? "true" : "false"}
    >
      <strong>{props.title}</strong>
      <span>{props.text}</span>
    </div>
  );
}

export function AdminEmptyState(props: {
  title: React.ReactNode;
  text?: React.ReactNode;
}) {
  return (
    <div className="efhc-admin-ui-empty" data-admin-ui-kit-empty-state="1326">
      <strong>{props.title}</strong>
      {props.text ? <span>{props.text}</span> : null}
    </div>
  );
}

export function AdminErrorState(props: {
  title: React.ReactNode;
  text?: React.ReactNode;
}) {
  return (
    <div className="efhc-admin-ui-error" data-admin-ui-kit-error-state="1326">
      <strong>{props.title}</strong>
      {props.text ? <span>{props.text}</span> : null}
    </div>
  );
}


type AdminDashboardSectionProps = React.PropsWithChildren<{
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  actions?: React.ReactNode;
}>;

type AdminPanelMenuItem = {
  id: string;
  label: React.ReactNode;
  disabled?: boolean;
  onSelect?: () => void;
};

type AdminDataColumn = {
  key: string;
  label: React.ReactNode;
};

type AdminDataRow = Record<string, React.ReactNode> & { id?: string };

type AdminEventItem = {
  id: string;
  title: React.ReactNode;
  ts?: React.ReactNode;
  description?: React.ReactNode;
  tone?: AdminUiTone;
};

type AdminStatusTimelineItem = {
  id: string;
  label: React.ReactNode;
  status?: React.ReactNode;
  tone?: AdminUiTone;
};

export function AdminDashboardSection(
  props: AdminDashboardSectionProps,
) {
  return (
    <section
      className="efhc-admin-dashboard-section"
      data-admin-dashboard-section="1497"
    >
      <AdminPanelHeader
        actions={props.actions}
        subtitle={props.subtitle}
        title={props.title}
      />
      <div className="efhc-admin-dashboard-section__body">
        {props.children}
      </div>
    </section>
  );
}

export function AdminPanelActions(props: React.PropsWithChildren) {
  return (
    <div
      className="efhc-admin-panel-actions"
      data-admin-panel-actions="1497"
    >
      {props.children}
    </div>
  );
}

export function AdminPanelMenu(props: {
  label?: React.ReactNode;
  items: AdminPanelMenuItem[];
}) {
  return (
    <div
      aria-label={adminNodeToText(props.label, "panel menu")}
      className="efhc-admin-panel-menu"
      data-admin-panel-menu="1497"
      role="menu"
    >
      {props.label ? <strong>{props.label}</strong> : null}
      {props.items.map((item) => (
        <button
          aria-disabled={item.disabled ? "true" : undefined}
          className="efhc-admin-panel-menu__item"
          disabled={item.disabled}
          key={item.id}
          onClick={item.onSelect}
          role="menuitem"
          type="button"
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}

export function AdminStatCard(props: AdminStatusCardProps) {
  return <AdminStatusCard {...props} />;
}

export function AdminDataTable(props: {
  columns: AdminDataColumn[];
  rows: AdminDataRow[];
  emptyLabel?: React.ReactNode;
}) {
  const resetKey = `${props.rows.length}:${String(props.rows[0]?.id ?? "")}:${String(props.rows[props.rows.length - 1]?.id ?? "")}`;
  const rowWindow = useAdminListWindow(props.rows, resetKey);
  if (!props.rows.length) {
    return (
      <AdminPanelEmpty
        title={props.emptyLabel ?? "Нет данных"}
      />
    );
  }
  return (
    <div className="efhc-admin-data-table" data-admin-data-table="1497" data-admin-list-window="20">
      <table>
        <thead>
          <tr>
            {props.columns.map((column) => (
              <th key={column.key}>{column.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rowWindow.visibleItems.map((row, index) => (
            <tr key={row.id ?? String(index)}>
              {props.columns.map((column) => (
                <td key={column.key}>{row[column.key] ?? "—"}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <AdminListExpandControl
        shown={rowWindow.visibleCount}
        total={rowWindow.totalCount}
        onExpand={rowWindow.expand}
        onCollapse={rowWindow.collapse}
      />
    </div>
  );
}

export function AdminCompactTable(props: {
  rows: ActionRow[];
  title?: React.ReactNode;
}) {
  return <AdminActionTable rows={props.rows} title={props.title} />;
}

export function AdminEventFeed(props: { items: AdminEventItem[] }) {
  const resetKey = `${props.items.length}:${props.items[0]?.id ?? ""}:${props.items[props.items.length - 1]?.id ?? ""}`;
  const eventWindow = useAdminListWindow(props.items, resetKey);
  return (
    <div className="efhc-admin-event-feed" data-admin-event-feed="1497" data-admin-list-window="20">
      {eventWindow.visibleItems.map((item) => (
        <article
          className={`efhc-admin-event-feed__item ${toneClass(item.tone)}`}
          key={item.id}
        >
          <strong>{item.title}</strong>
          {item.ts ? <small>{item.ts}</small> : null}
          {item.description ? <p>{item.description}</p> : null}
        </article>
      ))}
      <AdminListExpandControl
        shown={eventWindow.visibleCount}
        total={eventWindow.totalCount}
        onExpand={eventWindow.expand}
        onCollapse={eventWindow.collapse}
      />
    </div>
  );
}

export function AdminLogList(props: { items: AdminEventItem[] }) {
  return <AdminEventFeed items={props.items} />;
}

export function AdminLineChart(props: AdminMiniSparklineProps) {
  return <AdminSparkline {...props} />;
}

export function AdminBarChart(props: AdminMiniBarChartProps) {
  return <AdminMiniBarChart {...props} />;
}

export function AdminStackedBarChart(props: AdminMiniBarChartProps) {
  return <AdminMiniBarChart {...props} />;
}

export function AdminStatusTimeline(props: {
  items: AdminStatusTimelineItem[];
}) {
  return (
    <ol
      className="efhc-admin-status-timeline"
      data-admin-status-timeline="1497"
    >
      {props.items.map((item) => (
        <li className={toneClass(item.tone)} key={item.id}>
          <span>{item.label}</span>
          {item.status ? <strong>{item.status}</strong> : null}
        </li>
      ))}
    </ol>
  );
}

export function AdminPanelLoading(props: {
  title?: React.ReactNode;
}) {
  return (
    <div className="efhc-admin-panel-loading" data-admin-loading="1497">
      {props.title ?? "Загрузка…"}
    </div>
  );
}

export function AdminPanelEmpty(props: { title: React.ReactNode }) {
  return <AdminEmptyState title={props.title} />;
}

export function AdminPanelError(props: {
  title: React.ReactNode;
  text?: React.ReactNode;
}) {
  return <AdminErrorState text={props.text} title={props.title} />;
}

export function AdminPanelSkeleton(props: {
  label?: React.ReactNode;
}) {
  return (
    <div
      className="efhc-admin-panel-skeleton"
      data-admin-skeleton="1497"
    >
      {props.label ?? "…"}
    </div>
  );
}






