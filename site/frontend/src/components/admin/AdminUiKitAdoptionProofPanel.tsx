import React, { useMemo, useState } from "react";
import {
  AdminActionTable,
  AdminChartCard,
  AdminFilterBar,
  AdminFlowMapCard,
  AdminKpiCard,
  AdminSectionHeader,
  AdminStatusBadge,
} from "./AdminDashboardUiKit";

type ProofScope = "core" | "operator" | "technical";

type ProofItem = {
  key: string;
  label: string;
  route: string;
  scope: ProofScope;
  cycle: string;
  components: string[];
  sandboxPattern: string;
  status: "active" | "bounded" | "technical";
};

const PROOF_ITEMS: ProofItem[] = [
  {
    key: "bank-users",
    label: "Bank / Users",
    route: "/admin/bank · /admin/users",
    scope: "core",
    cycle: "1327",
    components: ["FilterBar", "ChartCard", "FlowMap", "ActionTable"],
    sandboxPattern: "interactive chart + section cards",
    status: "active",
  },
  {
    key: "withdrawals",
    label: "Withdrawals",
    route: "/admin/withdrawals",
    scope: "operator",
    cycle: "1328",
    components: ["KPI", "FlowMap", "StatusBadge", "ActionTable"],
    sandboxPattern: "mobile list/detail decision deck",
    status: "bounded",
  },
  {
    key: "shop",
    label: "Shop / Web3",
    route: "/admin/shop",
    scope: "operator",
    cycle: "1339",
    components: ["KPI", "FilterBar", "ChartCard", "ActionTable"],
    sandboxPattern: "data table + payment lane split",
    status: "active",
  },
  {
    key: "tasks",
    label: "Tasks",
    route: "/admin/tasks",
    scope: "operator",
    cycle: "1341-1342",
    components: ["FilterBar", "FlowMap", "ChartCard", "ActionTable"],
    sandboxPattern: "moderation deck + execution trace",
    status: "active",
  },
  {
    key: "reports",
    label: "Reports",
    route: "/admin/reports",
    scope: "core",
    cycle: "1343-1344",
    components: ["FilterBar", "ChartCard", "FlowMap", "ActionTable"],
    sandboxPattern: "interactive area chart + export action",
    status: "active",
  },
  {
    key: "diagnostics",
    label: "Diagnostics",
    route: "/admin/diagnostics",
    scope: "technical",
    cycle: "1345",
    components: ["KPI", "FilterBar", "ChartCard", "ActionTable"],
    sandboxPattern: "technical tabs + selected detail",
    status: "technical",
  },
];

function statusLabel(status: ProofItem["status"]): string {
  if (status === "technical") return "technical-only";
  if (status === "bounded") return "decision boundary";
  return "active UI Kit";
}

function badgeTone(status: ProofItem["status"]) {
  if (status === "technical") return "neutral" as const;
  if (status === "bounded") return "warning" as const;
  return "success" as const;
}

export function AdminUiKitAdoptionProofPanel() {
  const [scope, setScope] = useState<ProofScope | "all">("all");
  const [selectedKey, setSelectedKey] = useState(PROOF_ITEMS[0].key);

  const visibleItems = useMemo(
    () => PROOF_ITEMS.filter((item) => scope === "all" || item.scope === scope),
    [scope],
  );
  const selected = useMemo(
    () => PROOF_ITEMS.find((item) => item.key === selectedKey) || PROOF_ITEMS[0],
    [selectedKey],
  );
  const activeCount = PROOF_ITEMS.filter(
    (item) => item.status === "active",
  ).length;
  const operatorCount = PROOF_ITEMS.filter(
    (item) => item.scope === "operator",
  ).length;
  const componentCount = new Set(
    PROOF_ITEMS.flatMap((item) => item.components),
  ).size;

  return (
    <section
      className="efhc-admin-ui-kit-proof"
      data-admin-sandbox-source="ui-main section-cards; data-table; chart-area-interactive; Telegram Mini App cells"
    >
      <AdminSectionHeader
        eyebrow="Admin UI Kit · proof pass"
        title="Доказательство внедрения UI Kit в Admin"
        subtitle={
          "Панель фиксирует, что UI Kit больше не является декларацией: " +
          "он применён на Bank, Users, Withdrawals, Shop, Tasks, Reports " +
          "и Diagnostics без смешивания с public UI."
        }
        actions={
          <AdminStatusBadge
            label="Адаптировано"
            tone="primary"
          />
        }
      />

      <AdminFilterBar
        groups={[
          {
            label: "Контур",
            value: scope,
            options: [
              { key: "all", label: "Все" },
              { key: "core", label: "Основное" },
              { key: "operator", label: "Администратор" },
              { key: "technical", label: "Служебный раздел" },
            ],
            onChange: (value) => setScope(value as ProofScope | "all"),
          },
        ]}
      />

      <div className="efhc-admin-ui-kit-proof_kpis">
        <AdminKpiCard
          label="Покрытых зон"
          value={PROOF_ITEMS.length}
          meta="Admin surfaces"
          hint="главные рабочие контуры админ-панели"
          tone="success"
        />
        <AdminKpiCard
          label="Активных"
          value={activeCount}
          meta="interactive surfaces"
          hint="не статические страницы"
          tone="primary"
        />
        <AdminKpiCard
          label="Разделы администратора"
          value={operatorCount}
          meta="decision / moderation"
          hint="опасные действия остаются отделены"
          tone="warning"
        />
        <AdminKpiCard
          label="UI primitives"
          value={componentCount}
          meta="shared kit usage"
          hint="Filter, Chart, Flow, Table, Badge"
          tone="neutral"
        />
      </div>

      <AdminFlowMapCard
        title="Проверка интерфейса"
        nodes={visibleItems.map((item) => ({
          label: item.label,
          value: item.cycle,
          hint: item.route,
          active: item.key === selected.key,
          onClick: () => setSelectedKey(item.key),
        }))}
      />

      <div className="efhc-admin-ui-kit-proof_grid">
        <AdminChartCard
          title="Adoption matrix"
          subtitle="Mobile-first карта внедрения без новых зависимостей"
          meta={
            <AdminStatusBadge
              label={statusLabel(selected.status)}
              tone={badgeTone(selected.status)}
            />
          }
        >
          <div className="efhc-admin-ui-kit-proof_bars">
            {visibleItems.map((item) => (
              <button
                key={item.key}
                type="button"
                style={{
                  height: `${Math.max(24, item.components.length * 16)}px`,
                }}
                data-active={item.key === selected.key ? "true" : "false"}
                onClick={() => setSelectedKey(item.key)}
              >
                <span>{item.label}</span>
                <strong>{item.components.length}</strong>
              </button>
            ))}
          </div>
        </AdminChartCard>

        <AdminActionTable
          title="Выбранный пример интерфейса"
          rows={[
            { label: "Раздел", value: selected.label, hint: selected.route },
            { label: "Цикл", value: selected.cycle, hint: "Источник оформления" },
            {
              label: "UI Kit",
              value: selected.components.join(" · "),
              hint: "shared primitives",
            },
            {
              label: "Песочница",
              value: selected.sandboxPattern,
              hint: "Шаблон оформления",
            },
            {
              label: "Граница",
              value: statusLabel(selected.status),
              hint: "Только для администратора",
            },
          ]}
        />
      </div>
    </section>
  );
}
