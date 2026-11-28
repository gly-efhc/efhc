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

type DiagnosticScope = "admin" | "public" | "release";
type DiagnosticWindow = "now" | "next" | "guard";

type DiagnosticCard = {
  key: string;
  label: string;
  value: string;
  hint: string;
  scope: DiagnosticScope;
  severity: "neutral" | "success" | "warning";
};

const CARDS: DiagnosticCard[] = [
  {
    key: "admin-diagnostics",
    label: "Диагностика Admin",
    value: "только технический контур",
    hint: "Маршруты и исходные технические факты остаются только в Диагностике.",
    scope: "admin",
    severity: "success",
  },
  {
    key: "route-health",
    label: "Состояние маршрутов",
    value: "видно только здесь",
    hint: "Названия API-маршрутов не возвращаются на рабочие страницы.",
    scope: "admin",
    severity: "neutral",
  },
  {
    key: "public-ui",
    label: "Публичный интерфейс",
    value: "без отладки",
    hint: "Публичные страницы получают обычный интерфейс без внутренних технических данных.",
    scope: "public",
    severity: "success",
  },
  {
    key: "public-plan",
    label: "Публичная интерактивность",
    value: "запланировано",
    hint: "Энергия, Панели, Обмен, Задания, Рефералы, История.",
    scope: "public",
    severity: "warning",
  },
  {
    key: "release-core",
    label: "Данные релиза",
    value: "отделены",
    hint: "Диагностика не считается рабочим бизнес-действием релиза.",
    scope: "release",
    severity: "success",
  },
  {
    key: "ci-boundary",
    label: "Граница автоматических проверок",
    value: "вручную",
    hint: "Workflow files остаются вручную-control зоной.",
    scope: "release",
    severity: "warning",
  },
];

const WINDOW_LABELS: Record<DiagnosticWindow, string> = {
  now: "Сейчас",
  next: "Дальше",
  guard: "Защита",
};

function scopeLabel(scope: DiagnosticScope): string {
  if (scope === "admin") return "Admin";
  if (scope === "public") return "Публичный интерфейс";
  return "Релиз";
}

function chartPath(items: DiagnosticCard[]): string {
  const max = Math.max(items.length, 1);
  return items
    .map((item, index) => {
      const x = items.length === 1
        ? 20
        : Math.round((index / (items.length - 1)) * 100);
      const base = item.severity === "success" ? 22 : 40;
      const bump = item.severity === "warning" ? 20 : 0;
      const y = Math.round(base + bump + (index % max) * 5);
      return `${index === 0 ? "M" : "L"}${x},${y}`;
    })
    .join(" ");
}

export function AdminDiagnosticsTechnicalBoundaryPanel() {
  const [scope, setScope] = useState<DiagnosticScope>("admin");
  const [window, setWindow] = useState<DiagnosticWindow>("now");
  const [selected, setSelected] = useState(0);

  const filtered = useMemo(
    () => CARDS.filter((item) => item.scope === scope),
    [scope],
  );
  const current = filtered[selected % Math.max(filtered.length, 1)];
  const publicCount = CARDS.filter((item) => item.scope === "public").length;
  const adminCount = CARDS.filter((item) => item.scope === "admin").length;
  const releaseCount = CARDS.filter((item) => item.scope === "release").length;

  return (
    <section
      className="efhc-admin-diagnostics-boundary"
      data-admin-sandbox-source="техническая поверхность диагностики"
    >
      <AdminSectionHeader
        eyebrow="Диагностика Admin · только технический контур"
        title="Техническая диагностика без бизнес-действий"
        subtitle={
          "Диагностика остаётся единственным местом для проверки доступности маршрутов, " +
          "endpoint labels, helper-фактов и public/admin boundary review."
        }
        actions={
          <AdminStatusBadge
            label="без рабочих изменений"
            tone="warning"
          />
        }
      />

      <div className="efhc-admin-diagnostics-boundary_kpis">
        <AdminKpiCard
          label="Внутренние данные Admin"
          value={adminCount}
          meta="состояние маршрутов / вспомогательные факты"
          tone="neutral"
        />
        <AdminKpiCard
          label="Публичный интерфейс roadmap"
          value={publicCount}
          meta="интерактивный интерфейс без отладки"
          tone="success"
        />
        <AdminKpiCard
          label="Релиз boundaries"
          value={releaseCount}
          meta="вручную CI / evidence separation"
          tone="warning"
        />
      </div>

      <AdminFilterBar
        groups={[
          {
            label: "Контур",
            value: scope,
            options: [
              { key: "admin", label: "Admin" },
              { key: "public", label: "Публичный" },
              { key: "release", label: "Релиз" },
            ],
            onChange: (value) => {
              setScope(value as DiagnosticScope);
              setSelected(0);
            },
          },
          {
            label: "Окно",
            value: window,
            options: [
              { key: "now", label: "Сейчас" },
              { key: "next", label: "Дальше" },
              { key: "guard", label: "Защита" },
            ],
            onChange: (value) => setWindow(value as DiagnosticWindow),
          },
        ]}
      />

      <AdminChartCard
        title="Сигнал границы"
        subtitle={
          "Кликабельные точки показывают, какие технические факты " +
          "разрешены только внутри Diagnostics."
        }
        meta={<AdminStatusBadge label={WINDOW_LABELS[window]} />}
      >
        {filtered.length ? (
          <svg
            viewBox="0 0 100 80"
            className="efhc-admin-diagnostics-boundary_chart"
            role="img"
            aria-label="Сигнал технической границы"
          >
            <path d={chartPath(filtered)} fill="none" />
            {filtered.map((item, index) => {
              const x = filtered.length === 1
                ? 20
                : Math.round((index / (filtered.length - 1)) * 100);
              const y = item.severity === "success"
                ? 22
                : item.severity === "warning"
                  ? 60
                  : 40;
              return (
                <circle
                  key={item.key}
                  cx={x}
                  cy={y}
                  r={4}
                  className="efhc-admin-diagnostics-boundary_point"
                  role="button"
                  tabIndex={0}
                  aria-label={item.label}
                  onClick={() => setSelected(index)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      setSelected(index);
                    }
                  }}
                />
              );
            })}
          </svg>
        ) : null}
      </AdminChartCard>

      <AdminFlowMapCard
        title="Карта технической границы"
        nodes={filtered.map((item, index) => ({
          label: item.label,
          value: item.value,
          hint: item.hint,
          active: index === selected,
          onClick: () => setSelected(index),
        }))}
      />

      {current ? (
        <AdminActionTable
          title="Выбранная диагностическая карточка"
          rows={[
            {
              label: "Контур",
              value: scopeLabel(current.scope),
              hint: "Выбранный технический контур.",
            },
            {
              label: "Граница",
              value: current.value,
              hint: current.hint,
            },
            {
              label: "Публичный rule",
              value: "без исходных данных запроса",
              hint: "Публичный интерфейс получает UX-интерактив, а не diagnostics.",
            },
          ]}
        />
      ) : null}
    </section>
  );
}
