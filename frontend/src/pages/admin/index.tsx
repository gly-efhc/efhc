import React, { useCallback, useEffect, useState } from "react";

import {
  AdminAppButtonGrid,
  type AdminAppItem,
} from "../../components/admin/AdminAppButtonGrid";
import { AdminPage } from "../../components/admin/AdminPage";
import { AdminPromptModal } from "../../components/admin/AdminPromptModal";
import { AdminSectionCard } from "../../components/admin/AdminSectionCard";
import { AdminStatCard } from "../../components/admin/AdminStatCard";
import { Button } from "../../components/ui/Button";
import { TelegramEmptyState } from "../../components/ui/telegram/TelegramEmptyState";
import { useT } from "../../hooks/useT";
import { adminUiErrorMessage } from "../../lib/adminError";
import {
  ADMIN_REPORTS_OVERVIEW_PATH,
  ADMIN_TON_RECONCILE_PATH,
} from "../../lib/api/generated/adminSeams";
import { newIdempotencyKey } from "../../lib/idempotency";
import { formatFixedDown, formatD8ToHuman, fromScaledBigint, toScaledBigintDown } from "../../lib/format";
import { useAdminLinkedTransport } from "../../queries/useAdminLinkedTransport";

type Overview = {
  ok: boolean;
  ts: string;
  counters?: Record<string, number>;
  facts?: Record<string, string>;
  notes?: string | null;
};

const CORE_MODULES: AdminAppItem[] = [
  { href: "/admin/users", label: "Пользователи", category: "finance" },
  { href: "/admin/bank", label: "Банк EFHC", category: "finance" },
  { href: "/admin/withdrawals", label: "Выплаты", category: "finance" },
  { href: "/admin/bonuses", label: "Аналитика начислений", category: "analytics" },
  { href: "/admin/shop", label: "Магазин", category: "commerce" },
  { href: "/admin/tasks", label: "Задания", category: "engagement" },
  { href: "/admin/reports", label: "Отчёты и журналы", category: "analytics" },
  { href: "/admin/referrals", label: "Рефералы", category: "engagement" },
  { href: "/admin/panels", label: "Панели", category: "analytics" },
];

const OPERATION_MODULES: AdminAppItem[] = [
  { href: "/admin/hub", label: "Центр ссылок", category: "engagement" },
  { href: "/admin/vip-nft", label: "Выдача / VIP NFT", category: "commerce" },
  { href: "/admin/efhc-deposits", label: "Входящие платежи EFHC", category: "finance" },
  { href: "/admin/ads", label: "Рекламные сервисы", category: "engagement" },
  { href: "/admin/shop?module=orders", label: "Заказы", category: "commerce" },
  { href: "/admin/system", label: "Система и диагностика", category: "system" },
  { href: "/admin/api-workbench", label: "Admin API Workbench", category: "system" },
];

const ADMIN_MODULES: AdminAppItem[] = [...CORE_MODULES, ...OPERATION_MODULES];

const ADMIN_CATEGORY_LEGEND = [
  { key: "finance", label: "Финансы" },
  { key: "analytics", label: "Аналитика" },
  { key: "commerce", label: "Продажи" },
  { key: "engagement", label: "Вовлечение" },
  { key: "system", label: "Система" },
] as const;

function bankPercentWidth(value: string | undefined): string {
  try {
    const scaled = toScaledBigintDown(value || "0.00000000", 8);
    const absolute = scaled < 0n ? -scaled : scaled;
    const clamped = absolute > 10_000_000_000n ? 10_000_000_000n : absolute;
    return `${fromScaledBigint(clamped, 8)}%`;
  } catch {
    return "0%";
  }
}

function bankPercentLabel(value: string | undefined): string {
  try {
    return `${formatFixedDown(String(value || "0").replace(",", "."), 2)}%`;
  } catch {
    return "—";
  }
}

export default function AdminHome() {
  const adminApiRequest = useAdminLinkedTransport();
  const t = useT();
  const [overview, setOverview] = useState<Overview | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [reconcileOpen, setReconcileOpen] = useState(false);
  const [reconcile, setReconcile] = useState<Record<string, string>>({ last_hours: "6" });

  const load = useCallback(async () => {
    setMessage(null);
    try {
      setOverview(await adminApiRequest<Overview>(ADMIN_REPORTS_OVERVIEW_PATH, "GET"));
    } catch (error: unknown) {
      setOverview(null);
      setMessage(adminUiErrorMessage(error, t));
    }
  }, [adminApiRequest, t]);

  useEffect(() => { void load(); }, [load]);

  async function runReconcile() {
    setMessage(null);
    try {
      const lastHours = Math.max(1, Math.min(168, Number(reconcile.last_hours || "6")));
      await adminApiRequest(ADMIN_TON_RECONCILE_PATH, "POST", {
        idempotencyKey: newIdempotencyKey(),
        body: { last_hours: lastHours, limit: 1000 },
      });
      setMessage(`Проверены входящие TON-операции за последние ${lastHours} ч.`);
      setReconcileOpen(false);
      await load();
    } catch (error: unknown) {
      setMessage(adminUiErrorMessage(error, t));
    }
  }

  const facts = overview?.facts || {};

  return (
    <AdminPage
      refreshBankSnapshot={false}
      title="Административный режим"
      subtitle="Рабочие модули, показатели и действия администратора."
      actions={(
        <Button variant="secondary" onClick={() => setReconcileOpen(true)}>
          Проверить входящие TON
        </Button>
      )}
    >
      {message ? (
        <AdminSectionCard title="Результат операции" subtitle={message}>
          <div className="flex justify-end">
            <Button variant="secondary" onClick={load}>Обновить данные</Button>
          </div>
        </AdminSectionCard>
      ) : null}

      <AdminSectionCard title="Банк и оборот" subtitle="Основные показатели банка.">
        <div className="efhc-admin-home-bank-charts admin-home-bank-charts-v218" data-admin-home-bank-charts="reserve-left-circulation-right" data-efhc-admin-canon-bank="v866" data-eam-family="EAM-ADMIN-003">
          {[
            { key: "reserve", label: "Резерв Банка EFHC", amount: facts.bank_metrics_reserve_efhc, percent: facts.bank_metrics_reserve_pct },
            { key: "circulation", label: "В обороте EFHC", amount: facts.bank_metrics_circulation_efhc, percent: facts.bank_metrics_circulation_pct },
          ].map((chart) => (
            <article key={chart.key} data-bank-chart={chart.key}>
              <span>{chart.label}</span>
              <strong>{facts.bank_metrics_ready === "1" ? formatD8ToHuman(chart.amount || "0.00000000") : "—"}</strong>
              <div aria-label={`${chart.label}: ${bankPercentLabel(chart.percent)}`} role="img"><i style={{ width: bankPercentWidth(chart.percent) }} /></div>
              <b>{facts.bank_metrics_ready === "1" ? bankPercentLabel(chart.percent) : "—"}</b>
            </article>
          ))}
        </div>
      </AdminSectionCard>

      <div className="admin-reference-stats grid gap-3 md:grid-cols-4" data-admin-business-summary="true" data-efhc-admin-canon-home-stats="v866">
        <AdminStatCard label="Пользователи" value={overview?.counters?.users_total === undefined ? "—" : String(overview.counters.users_total)} meta="всего" hint="Общее количество пользователей в системе." tone="success" />
        <AdminStatCard label="Активные панели" value={overview?.facts?.panels_total_active || "—"} meta="текущее состояние" hint="Количество активных пользовательских панелей." tone="neutral" />
        <AdminStatCard label="Сгенерировано kWh" value={overview?.facts?.users_total_generated_kwh || "—"} meta="всего" hint="Суммарная генерация пользователей." tone="neutral" />
        <AdminStatCard label="Основной баланс EFHCm" value={overview?.facts?.users_total__main__efhc || "—"} meta="на балансах" hint="Суммарный основной баланс пользователей." tone="neutral" />
      </div>

      <AdminSectionCard title="Административные модули">
        <div className="efhc-admin-category-legend" aria-label="Цветовые категории административных модулей">
          {ADMIN_CATEGORY_LEGEND.map((item) => (
            <span className="efhc-admin-category-legend_item" data-admin-category={item.key} key={item.key}>
              <i aria-hidden="true" />
              {item.label}
            </span>
          ))}
        </div>
        <AdminAppButtonGrid items={ADMIN_MODULES} />
      </AdminSectionCard>

      {!overview && !message ? (
        <TelegramEmptyState
          title="Данные пока не загружены"
          detail="Нажмите обновить, чтобы запросить текущие показатели."
          actionLabel={t("common.refresh")}
          onAction={() => void load()}
        />
      ) : null}

      <AdminPromptModal
        open={reconcileOpen}
        title="Проверить входящие операции"
        submitLabel="Запустить проверку"
        fields={[{ key: "last_hours", label: "Период проверки, часов", placeholder: "6", type: "number" }]}
        values={reconcile}
        onChange={(key, value) => setReconcile((previous) => ({ ...previous, [key]: value }))}
        onClose={() => setReconcileOpen(false)}
        onSubmit={() => { void runReconcile(); }}
      />
    </AdminPage>
  );
}
