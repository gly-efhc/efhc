import { formatD8ToHuman } from "../../lib/format";
import React from "react";

import {
  AdminHeatStrip,
  AdminDashboardGrid,
  AdminDashboardToolbar,
  AdminFilterBar,
  AdminFlowMapCard,
  AdminFreshnessBadge,
  AdminKpiCard,
  AdminMiniBarChart,
  AdminPanelChrome,
  AdminProgressBar,
  AdminRefreshPicker,
  AdminStatusBadge,
} from "./AdminDashboardUiKit";
import type { DbId } from "../../types/db-id";


type AdminBankTone = "success" | "warning" | "danger" | "neutral";

type TransferLogItem = {
  id: DbId;
  amount: string;
  direction: string;
  balance_type: string;
  reason: string;
  created_at: string;
};

type BankChartPoint = {
  id: string;
  label: string;
  value: number;
  tone?: "success" | "warning" | "info" | "neutral" | "danger";
};

export type AdminBankDashboardRuntimeProps = {
  bankName: string;
  bankBalance: string;
  usersTotal: string;
  usersMain: string;
  usersBonus: string;
  bankUsersDiff: string;
  bankUsersMatch: string;
  panelsPaid: string;
  exchangedKwh: string;
  ledger: TransferLogItem[];
  updatedAt?: string;
  onRefresh: () => void;
};

const ZERO_D8 = "0.00000000";

function toNumber(value: string | undefined): number {
  if (!value) return 0;
  const parsed = Number(String(value).replace(/,/g, "."));
  return Number.isFinite(parsed) ? parsed : 0;
}

function absNumber(value: string | undefined): number {
  return Math.abs(toNumber(value));
}

function human(value: string | number | undefined): string {
  if (typeof value !== "number") return formatD8ToHuman(value);
  const numberValue = value;
  return numberValue.toLocaleString("ru-RU", {
    maximumFractionDigits: 8,
  });
}

function safeLabel(value: string | undefined): string {
  const trimmed = String(value || "").trim();
  return trimmed || "—";
}

function statusTone(match: string): AdminBankTone {
  if (match === "OK") return "success";
  if (!match || match === "no overview") return "warning";
  return "danger";
}

function recentLedgerTone(item: TransferLogItem) {
  if (item.direction === "user_credit") return "warning";
  if (item.direction === "user_debit") return "success";
  return "info";
}

function buildBankChartPoints(
  props: AdminBankDashboardRuntimeProps,
): BankChartPoint[] {
  return [
    {
      id: "bank",
      label: "Банк",
      value: absNumber(props.bankBalance),
      tone: "success",
    },
    {
      id: "users",
      label: "Пользователи",
      value: absNumber(props.usersTotal),
      tone: "info",
    },
    {
      id: "panels",
      label: "Панели",
      value: absNumber(props.panelsPaid),
      tone: "neutral",
    },
    {
      id: "diff",
      label: "Разница",
      value: absNumber(props.bankUsersDiff),
      tone: props.bankUsersMatch === "OK" ? "success" : "warning",
    },
  ];
}

function ledgerDirectionLabel(item: TransferLogItem): string {
  if (item.direction === "user_credit") return "Начисление пользователю уменьшает баланс банка";
  if (item.direction === "user_debit") return "Списание у пользователя возвращает EFHC в банк";
  return safeLabel(item.direction);
}

export function AdminBankDashboardRuntime(
  props: AdminBankDashboardRuntimeProps,
) {
  const chartPoints = buildBankChartPoints(props);
  const hasOverview = Boolean(props.bankUsersMatch);
  const matchTone = statusTone(props.bankUsersMatch);
  const source =
    "GET /admin/bank/balance + /admin/reports/overview + " +
    "GET /admin/logs/transfers";

  return (
    <section
      className="efhc-admin-bank-dashboard-runtime"
      data-admin-bank-dashboard-runtime="1483"
      data-admin-bank-truth="raw-derived"
      data-admin-bank-no-synthetic="true"
      data-admin-bank-no-write-actions="true"
      data-admin-bank-no-raw-payload="true"
      data-admin-bank-no-debug-json="true"
      data-admin-bank-canon="bank-can-go-negative"
    >
      <AdminDashboardToolbar
        title="Банк EFHC"
        subtitle="Понятный обзор баланса банка, движения EFHC и последних операций."
        breadcrumb="Admin / Bank"
        refresh={(
          <AdminRefreshPicker
            label="Обновление"
            onRefresh={props.onRefresh}
            refreshLabel="Обновить"
            value="manual"
          />
        )}
        updatedAt={props.updatedAt || "—"}
        freshness={(
          <AdminFreshnessBadge
            freshness={hasOverview ? "fresh" : "stale"}
            label={hasOverview ? "Данные загружены" : "Данные загружаются"}
          />
        )}
        filters={(
          <AdminFilterBar
            groups={[
              {
                key: "bank-scope",
                label: "Срез",
                value: "snapshot",
                options: [
                  { key: "snapshot", label: "Текущие данные" },
                  { key: "ledger", label: "История операций" },
                  { key: "flows", label: "Движение EFHC" },
                ],
                onChange: () => undefined,
              },
            ]}
          />
        )}
      />

      <AdminDashboardGrid>
        <AdminKpiCard
          label="Банк"
          value={safeLabel(props.bankName)}
          meta="EFHCm"
          hint="Системный баланс банка EFHC. Это не пользовательский кошелёк."
          tone="neutral"
        />
        <AdminKpiCard
          label="Баланс банка"
          value={human(props.bankBalance)}
          meta="банк может быть отрицательным"
          hint="Минус банка не является дефектом сам по себе."
          tone="success"
        />
        <AdminKpiCard
          label="Баланс пользователей"
          value={human(props.usersTotal)}
          meta="EFHCm + EFHCb"
          hint="Общая сумма EFHC на пользовательских балансах."
          tone="neutral"
        />
        <AdminKpiCard
          label="Согласованность балансов"
          value={props.bankUsersMatch === "OK" ? "Согласовано" : props.bankUsersMatch ? "Требует проверки" : "Ожидается"}
          meta={human(props.bankUsersDiff || ZERO_D8)}
          hint="Внимание требуется только при несогласованной операции; отрицательный баланс банка сам по себе разрешён."
          tone={matchTone}
        />
      </AdminDashboardGrid>

      <div className="efhc-admin-bank-dashboard-grid">
        <AdminPanelChrome
          title="Баланс системы"
          subtitle="Текущая сводка по банку, пользователям и панелям."
          status={hasOverview ? "success" : "stale"}
          tone="info"
          source={source}
          updatedAt={props.updatedAt || "—"}
        >
          <AdminMiniBarChart
            ariaLabel="Сравнение банка, пользователей, панелей и разницы"
            dataKind="derived"
            points={chartPoints}
            source="Расчёт по текущей банковской сводке"
            unit="EFHC"
          />
          <div className="efhc-admin-bank-dashboard-bars">
            {chartPoints.map((point) => (
              <div className="efhc-admin-bank-dashboard-row" key={point.id}>
                <span>{point.label}</span>
                <strong>{human(point.value)}</strong>
              </div>
            ))}
          </div>
        </AdminPanelChrome>

        <AdminPanelChrome
          title="Как движутся EFHC"
          subtitle="Показано, откуда и куда движутся EFHC при основных действиях."
          status="success"
          tone="success"
          source="Банковские операции EFHC"
        >
          <AdminFlowMapCard
            title="Банк, пользователи, панели и обмен"
            nodes={[
              {
                label: "Банк",
                value: human(props.bankBalance),
                hint: "EFHCm; отрицательный баланс разрешён",
                active: true,
              },
              {
                label: "Пользователи",
                value: human(props.usersTotal),
                hint: "EFHCm + EFHCb; отрицательный баланс пользователя запрещён",
              },
              {
                label: "Панели",
                value: human(props.panelsPaid),
                hint: "Активация панели — 100 EFHC",
              },
              {
                label: "История",
                value: String(props.ledger.length),
                hint: "Последние банковские операции",
              },
            ]}
          />
        </AdminPanelChrome>
      </div>

      <div className="efhc-admin-bank-dashboard-grid">
        <AdminPanelChrome
          title="Безопасность операций"
          subtitle="Обычная страница Банка не выполняет Mint/Burn. Аварийная корректировка вынесена в отдельный SUPERADMIN-контур."
          status="success"
          tone="success"
          source="BANK CANON + отдельная аварийная страница"
        >
          <div className="efhc-admin-bank-dashboard-status-grid">
            <AdminStatusBadge
              label="Обычная страница Банка: без Mint/Burn"
              tone="success"
            />
            <AdminStatusBadge
              label="Аварийные операции требуют отдельного подтверждения"
              tone="warning"
            />
            <AdminStatusBadge
              label="Повторное нажатие защищено идемпотентностью"
              tone="primary"
            />
            <AdminStatusBadge
              label="Операции по пользователю выполняются через Global ID"
              tone="neutral"
            />
          </div>
          <AdminProgressBar
            dataKind="derived"
            label="История последних операций"
            max={12}
            showValue
            source="История банковских операций"
            tone={props.ledger.length ? "success" : "warning"}
            value={Math.min(props.ledger.length, 12)}
          />
        </AdminPanelChrome>

        <AdminPanelChrome
          title="Последние операции банка"
          subtitle="Последние банковские операции."
          status={props.ledger.length ? "success" : "empty"}
          tone="neutral"
          source="История банковских операций"
        >
          <AdminHeatStrip
            ariaLabel="Последние операции банка"
            dataKind="raw"
            emptyLabel="История пока пуста"
            points={props.ledger.slice(0, 12).map((item, index) => ({
              id: String(item.id || index),
              label: item.created_at || `операция ${index + 1}`,
              value: props.ledger.length - index,
              tone: recentLedgerTone(item),
            }))}
            source="Последние банковские операции"
          />
          <div className="efhc-admin-bank-dashboard-ledger-preview">
            {props.ledger.slice(0, 4).map((item) => (
              <div key={item.id}>
                <span>{ledgerDirectionLabel(item)}</span>
                <strong>{human(item.amount)}</strong>
                <small>{safeLabel(item.reason)}</small>
              </div>
            ))}
            {!props.ledger.length ? (
              <p>История операций пока пуста или временно недоступна.</p>
            ) : null}
          </div>
        </AdminPanelChrome>
      </div>

      <AdminPanelChrome
        title="Правила безопасности банка"
        subtitle="Раздел помогает контролировать банк, но денежные операции выполняются только по действующим правилам."
        status="success"
        tone="warning"
        source="Правила банка EFHC"
      >
        <div className="efhc-admin-bank-dashboard-boundary">
          <span>Начисление пользователю уменьшает баланс банка</span>
          <span>Списание у пользователя возвращает EFHC в банк</span>
          <span>Банк может иметь отрицательный баланс</span>
          <span>Баланс изменяется только через предусмотренные административные действия</span>
          <span>Финансовые действия выполняются по установленным правилам</span>
          <span>Опасные действия требуют подтверждения</span>
        </div>
      </AdminPanelChrome>
    </section>
  );
}
