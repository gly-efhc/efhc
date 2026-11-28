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

type QaScope = "core" | "decision" | "technical";
type QaViewport = "mobile" | "telegram" | "desktop" | "state";

type QaSurface = {
  key: string;
  title: string;
  route: string;
  scope: QaScope;
  ownerCycle: string;
  screenshots: string[];
  risk: "low" | "medium" | "high";
  sandboxPattern: string;
};

const QA_SURFACES: QaSurface[] = [
  {
    key: "admin-home",
    title: "Admin Home",
    route: "/admin",
    scope: "core",
    ownerCycle: "1325 / 1353",
    screenshots: ["390px", "telegram", "desktop", "empty"],
    risk: "medium",
    sandboxPattern: "section cards + adoption matrix",
  },
  {
    key: "bank-users",
    title: "Bank / Users",
    route: "/admin/bank · /admin/users",
    scope: "core",
    ownerCycle: "1327",
    screenshots: ["390px", "desktop", "table", "error"],
    risk: "medium",
    sandboxPattern: "interactive chart + data table",
  },
  {
    key: "withdrawals",
    title: "Withdrawals",
    route: "/admin/withdrawals",
    scope: "decision",
    ownerCycle: "1328",
    screenshots: ["390px", "decision", "final", "empty"],
    risk: "high",
    sandboxPattern: "mobile decision deck",
  },
  {
    key: "shop-web3",
    title: "Shop / Web3",
    route: "/admin/shop",
    scope: "decision",
    ownerCycle: "1339",
    screenshots: ["390px", "catalog", "payment", "empty"],
    risk: "high",
    sandboxPattern: "payment lane split + table",
  },
  {
    key: "tasks",
    title: "Tasks",
    route: "/admin/tasks",
    scope: "decision",
    ownerCycle: "1341-1342",
    screenshots: ["390px", "moderation", "trace", "empty"],
    risk: "medium",
    sandboxPattern: "moderation cards + trace rows",
  },
  {
    key: "reports",
    title: "Reports",
    route: "/admin/reports",
    scope: "core",
    ownerCycle: "1343-1344",
    screenshots: ["390px", "chart", "export", "desktop"],
    risk: "low",
    sandboxPattern: "area chart + export action",
  },
  {
    key: "diagnostics",
    title: "Diagnostics",
    route: "/admin/diagnostics",
    scope: "technical",
    ownerCycle: "1345",
    screenshots: ["390px", "technical", "guard", "desktop"],
    risk: "medium",
    sandboxPattern: "technical tabs + selected detail",
  },
];

function riskTone(risk: QaSurface["risk"]) {
  if (risk === "high") return "warning" as const;
  if (risk === "medium") return "primary" as const;
  return "success" as const;
}

function riskLabel(risk: QaSurface["risk"]): string {
  if (risk === "high") return "high attention";
  if (risk === "medium") return "visual proof";
  return "standard proof";
}

function viewportLabel(viewport: QaViewport): string {
  if (viewport === "telegram") return "Telegram narrow";
  if (viewport === "desktop") return "Desktop";
  if (viewport === "state") return "Empty / error";
  return "Mobile 390";
}

export function AdminScreenshotQaPreparationPanel() {
  const [scope, setScope] = useState<QaScope | "all">("all");
  const [viewport, setViewport] = useState<QaViewport>("mobile");
  const [selectedKey, setSelectedKey] = useState(QA_SURFACES[0].key);

  const visible = useMemo(
    () => QA_SURFACES.filter((item) => scope === "all" || item.scope === scope),
    [scope],
  );
  const selected = useMemo(
    () => QA_SURFACES.find((item) => item.key === selectedKey) || QA_SURFACES[0],
    [selectedKey],
  );
  const mobileCount = QA_SURFACES.filter((item) =>
    item.screenshots.includes("390px"),
  ).length;
  const highRiskCount = QA_SURFACES.filter(
    (item) => item.risk === "high",
  ).length;
  const screenshotTargets = QA_SURFACES.reduce(
    (total, item) => total + item.screenshots.length,
    0,
  );

  return (
    <section
      className="efhc-admin-screenshot-qa"
      data-admin-screenshot-qa-sandbox-source="ui-main cards; data-table; Telegram cells"
      data-admin-screenshot-qa-ci-boundary="manual"
    >
      <AdminSectionHeader
        eyebrow="Admin screenshot QA · work pass"
        title="Подготовка скриншотного QA для Admin"
        subtitle={
          "Панель фиксирует, какие admin-экраны нужно проверять на "
          + "mobile, Telegram-like и desktop viewport без запуска CI "
          + "и без смешивания Diagnostics с бизнес-действиями."
        }
        actions={
          <AdminStatusBadge
            label="Проверка отображения"
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
              { key: "decision", label: "Decision" },
              { key: "technical", label: "Служебный раздел" },
            ],
            onChange: (value) => setScope(value as QaScope | "all"),
          },
          {
            label: "Viewport",
            value: viewport,
            options: [
              { key: "mobile", label: "390" },
              { key: "telegram", label: "Telegram" },
              { key: "desktop", label: "Desktop" },
              { key: "state", label: "States" },
            ],
            onChange: (value) => setViewport(value as QaViewport),
          },
        ]}
      />

      <div className="efhc-admin-screenshot-qa_kpis">
        <AdminKpiCard
          label="Экранов"
          value={QA_SURFACES.length}
          meta="admin surfaces"
          hint="Home, Bank, Users, Withdrawals, Shop, Tasks, Reports, Diagnostics"
          tone="primary"
        />
        <AdminKpiCard
          label="Мобильный вид"
          value={mobileCount}
          meta="390px viewport"
          hint="обязательная мобильная проверка"
          tone="success"
        />
        <AdminKpiCard
          label="Targets"
          value={screenshotTargets}
          meta="screenshot states"
          hint="mobile, desktop, empty, error и decision states"
          tone="neutral"
        />
        <AdminKpiCard
          label="High risk"
          value={highRiskCount}
          meta="decision zones"
          hint="Withdrawals и Shop/Web3 требуют особого контроля"
          tone="warning"
        />
      </div>

      <AdminFlowMapCard
        title="Проверка отображения"
        nodes={visible.map((item) => ({
          label: item.title,
          value: item.ownerCycle,
          hint: item.route,
          active: item.key === selected.key,
          onClick: () => setSelectedKey(item.key),
        }))}
      />

      <div className="efhc-admin-screenshot-qa_grid">
        <AdminChartCard
          title="Coverage matrix"
          subtitle={viewportLabel(viewport)}
          meta={
            <AdminStatusBadge
              label={riskLabel(selected.risk)}
              tone={riskTone(selected.risk)}
            />
          }
        >
          <div className="efhc-admin-screenshot-qa_bars">
            {visible.map((item) => (
              <button
                key={item.key}
                type="button"
                style={{
                  height: `${Math.max(26, item.screenshots.length * 15)}px`,
                }}
                data-active={item.key === selected.key ? "true" : "false"}
                onClick={() => setSelectedKey(item.key)}
              >
                <span>{item.title}</span>
                <strong>{item.screenshots.length}</strong>
              </button>
            ))}
          </div>
        </AdminChartCard>

        <AdminActionTable
          title="Selected screenshot checklist"
          rows={[
            { label: "Экран", value: selected.title, hint: selected.route },
            { label: "Цикл-владелец", value: selected.ownerCycle },
            {
              label: "Viewport",
              value: viewportLabel(viewport),
              hint: "manual screenshot target",
            },
            {
              label: "Состояния",
              value: selected.screenshots.join(" · "),
              hint: "minimum capture list",
            },
            {
              label: "Шаблон интерфейса",
              value: selected.sandboxPattern,
              hint: "Источник оформления",
            },
            {
              label: "Boundary",
              value: "no CI claim / no raw payload / no public admin internals",
              hint: "manual QA discipline",
            },
          ]}
        />
      </div>
    </section>
  );
}
