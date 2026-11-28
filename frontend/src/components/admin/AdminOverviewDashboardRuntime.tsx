import React from "react";

import {
  AdminAreaChart,
  AdminHeatStrip,
  AdminDashboardGrid,
  AdminDashboardToolbar,
  AdminFreshnessBadge,
  AdminPanelChrome,
  AdminProgressBar,
  AdminStatusCard,
  AdminTrendCard,
} from "./AdminDashboardUiKit";

export type AdminOverviewModuleState =
  | "live"
  | "helper"
  | "draft"
  | "deferred";

export type AdminOverviewReleaseTier =
  | "core"
  | "non_core"
  | "deferred";

export type AdminOverviewModule = {
  href: string;
  label: string;
  note: string;
  state: AdminOverviewModuleState;
  releaseTier: AdminOverviewReleaseTier;
};

export type AdminOverviewSnapshot = {
  ok: boolean;
  ts: string;
  counters: Record<string, number>;
  facts?: Record<string, string>;
  notes?: string | null;
};

type AdminOverviewDashboardRuntimeProps = {
  overview: AdminOverviewSnapshot | null;
  modules: AdminOverviewModule[];
  operationModules: AdminOverviewModule[];
  serviceModules: AdminOverviewModule[];
  hasTelegramAuth: boolean;
  onRefresh: () => void;
};

const FACT_LABELS: Record<string, string> = {
  panels_total_active: "Активные панели",
  panels_total_archived: "Архивные панели",
  panels_total_bought: "Панелей всего",
  panels_total_paid_efhc: "EFHC списано",
  users_total__main__efhc: "EFHCm",
  users_total_bonus_efhc: "EFHCb",
  users_total_exchanged_kwh: "kWh обменяно",
  users_total_generated_kwh: "kWh сгенерировано",
};

const CORE_FACTS = [
  "users_total__main__efhc",
  "users_total_bonus_efhc",
  "users_total_generated_kwh",
  "users_total_exchanged_kwh",
  "panels_total_active",
  "panels_total_archived",
];

function numericFact(value: string | undefined): number {
  if (!value) return 0;
  const parsed = Number(String(value).replace(/,/g, "."));
  return Number.isFinite(parsed) ? parsed : 0;
}

function countByState(
  modules: AdminOverviewModule[],
  state: AdminOverviewModuleState,
): number {
  return modules.filter((module) => module.state === state).length;
}

function factLabel(key: string): string {
  return FACT_LABELS[key] ?? key.replaceAll("_", " ");
}

function moduleTone(module: AdminOverviewModule): "success" | "warning" {
  return module.state === "live" ? "success" : "warning";
}

function moduleStateLabel(state: AdminOverviewModuleState): string {
  if (state === "live") return "Доступно";
  if (state === "helper") return "Вспомогательный";
  if (state === "deferred") return "Резерв";
  return "Подготовка";
}

function freshnessLabel(overview: AdminOverviewSnapshot | null): string {
  if (!overview) return "ожидание сводки";
  if (!overview.ok) return "сводка с предупреждением";
  return "сводка свежая";
}

export function AdminOverviewDashboardRuntime(
  props: AdminOverviewDashboardRuntimeProps,
) {
  const allModules = [
    ...props.modules,
    ...props.operationModules,
    ...props.serviceModules,
  ];
  const facts = props.overview?.facts ?? {};
  const factKeys = CORE_FACTS.filter((key) => key in facts);
  const chartPoints = factKeys.map((key) => ({
    id: key,
    label: factLabel(key),
    value: numericFact(facts[key]),
  }));
  const liveModules = countByState(allModules, "live");
  const helperModules = countByState(allModules, "helper");
  const deferredModules = countByState(allModules, "deferred");
  const moduleProgress = allModules.length
    ? Math.round((liveModules / allModules.length) * 100)
    : 0;

  return (
    <section
      className="efhc-admin-overview-dashboard"
      data-admin-overview-dashboard="1481"
      data-admin-overview-dashboard-truth="raw-derived"
      data-admin-overview-no-write-actions="true"
      data-admin-overview-no-raw-payload="true"
      data-admin-overview-no-debug-json="true"
    >
      <AdminDashboardToolbar
        actions={(
          <button
            className="efhc-admin-overview-dashboard__refresh"
            onClick={props.onRefresh}
            type="button"
          >
            Обновить сводку
          </button>
        )}
        freshness={(
          <AdminFreshnessBadge
            freshness={props.overview ? "fresh" : "unknown"}
            label={freshnessLabel(props.overview)}
            updatedAt={props.overview?.ts ?? "нет данных"}
          />
        )}
        subtitle={
          "Карта системы за 10 секунд: состояние, ключевые домены, "
          + "переходы между разделами и доступные показатели."
        }
        title="Обзор админ-панели"
        updatedAt={props.overview?.ts ?? "ожидание данных"}
      />

      <AdminDashboardGrid>
        <AdminStatusCard
          hint="Текущая административная сводка."
          label="Общая сводка"
          status={props.overview?.ok ? "success" : "stale"}
          tone={props.overview?.ok ? "success" : "warning"}
          value={props.overview?.ok ? "OK" : "ожидание"}
        />
        <AdminStatusCard
          hint="Доступ администратора подтверждён."
          label="Доступ администратора"
          status={props.hasTelegramAuth ? "success" : "stale"}
          tone={props.hasTelegramAuth ? "success" : "warning"}
          value={props.hasTelegramAuth ? "активна" : "нужна"}
        />
        <AdminTrendCard
          hint="Доступные рабочие разделы."
          label="Доступные разделы"
          tone="success"
          value={`${liveModules}/${allModules.length}`}
        />
        <AdminTrendCard
          hint="Основные административные показатели."
          label="Показатели"
          tone="info"
          value={String(Object.keys(props.overview?.counters ?? {}).length)}
        />
      </AdminDashboardGrid>

      <div className="efhc-admin-overview-dashboard__main">
        <AdminPanelChrome
          footer="Сводка предназначена только для просмотра."
          source="Сводка"
          status={props.overview ? "success" : "stale"}
          title="Ключевые показатели"
          tone="info"
          updatedAt={props.overview?.ts ?? "нет сводки"}
        >
          <div className="efhc-admin-overview-dashboard__facts">
            {factKeys.length ? factKeys.map((key) => (
              <div key={key}>
                <span>{factLabel(key)}</span>
                <strong>{facts[key]}</strong>
              </div>
            )) : (
              <div>
                <span>Факты</span>
                <strong>нет данных</strong>
              </div>
            )}
          </div>
          <AdminAreaChart
            emptyLabel="Нет данных"
            label="Экономическая сводка"
            points={chartPoints}
            source="Расчётное значение"
            unit="Текущие данные"
          />
        </AdminPanelChrome>

        <AdminPanelChrome
          footer="Вспомогательные разделы отделены от финансовых действий."
          source="Разделы администрирования"
          status="success"
          title="Операторская готовность"
          tone="success"
        >
          <AdminProgressBar
            ariaLabel="Доля доступных разделов"
            label="Готовность разделов"
            max={100}
            showValue
            source="Расчёт по доступным разделам"
            value={moduleProgress}
          />
          <AdminHeatStrip
            ariaLabel="Состояние разделов"
            label="Состояние разделов"
            points={[
              { id: "live", label: "Доступно", tone: "success", value: liveModules },
              {
                id: "helper",
                label: "Вспомогательный",
                tone: "warning",
                value: helperModules,
              },
              {
                id: "deferred",
                label: "Резерв",
                tone: "neutral",
                value: deferredModules,
              },
            ]}
            source="Состояние разделов"
          />
          <div className="efhc-admin-overview-dashboard__domain-grid">
            {props.modules.slice(0, 8).map((module) => (
              <a
                className="efhc-admin-overview-dashboard__domain"
                data-admin-overview-domain-card="1481"
                href={module.href}
                key={module.href}
              >
                <span>{module.label}</span>
                <b data-state={module.state}>{moduleStateLabel(module.state)}</b>
                <small>{module.note}</small>
              </a>
            ))}
          </div>
        </AdminPanelChrome>
      </div>

      <AdminPanelChrome
        footer="Показываются только сведения, необходимые администратору."
        source="Навигация администратора"
        status="success"
        title="Быстрые операторские переходы"
        tone="neutral"
      >
        <div className="efhc-admin-overview-dashboard__quick-links">
          {[...props.operationModules, ...props.serviceModules].map(
            (module) => (
              <a
                className="efhc-admin-overview-dashboard__quick-link"
                data-tier={module.releaseTier}
                href={module.href}
                key={module.href}
              >
                <span>{module.label}</span>
                <b>{moduleStateLabel(module.state)}</b>
                <small>{module.note}</small>
              </a>
            ),
          )}
        </div>
      </AdminPanelChrome>

      <AdminPanelChrome
        footer="Сводка не изменяет данные."
        source="Правила обзорной страницы"
        status="success"
        title="Правила безопасности"
        tone="warning"
      >
        <div className="efhc-admin-overview-dashboard__boundary">
          <span>Текущие и расчётные показатели</span>
          <span>Только доступные показатели</span>
          <span>Изменения выполняются только через подтверждённые действия</span>
          <span>Основные сведения</span>
        </div>
      </AdminPanelChrome>
    </section>
  );
}

