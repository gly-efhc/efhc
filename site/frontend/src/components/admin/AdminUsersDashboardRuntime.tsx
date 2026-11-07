import React, { useCallback, useMemo, useState } from "react";

import { useLargeAdminFilter } from "../../hooks/admin/useLargeAdminFilter";
import { format8, formatD8ToHuman, sumScaledDown } from "../../lib/format";
import {
  AdminDashboardGrid,
  AdminDashboardToolbar,
  AdminFilterBar,
  AdminFlowMapCard,
  AdminFreshnessBadge,
  AdminHeatStrip,
  AdminKpiCard,
  AdminMiniBarChart,
  AdminPanelChrome,
  AdminProgressBar,
  AdminRefreshPicker,
  AdminStatusBadge,
} from "./AdminDashboardUiKit";


type UserDashboardItem = {
  username?: string | null;
  is_active: boolean;
  is_vip: boolean;
  ton_wallet?: string | null;
  main_balance: string;
  bonus_balance: string;
  available_kwh: string;
  total_generated_kwh: string;
  last_seen_at?: string | null;
};

type UserSegment = "all" | "active" | "inactive" | "vip" | "wallets";

type ChartPointTone = "success" | "warning" | "info" | "neutral" | "danger";

type UserChartPoint = {
  id: string;
  label: string;
  value: number;
  tone?: ChartPointTone;
};

export type AdminUsersDashboardRuntimeProps = {
  users: UserDashboardItem[];
  selected?: UserDashboardItem | null;
  query: string;
  loading?: boolean;
  error?: string;
  updatedAt?: string;
  onRefresh: () => void;
};

function toNumber(value: string | number | undefined | null): number {
  if (value === null || value === undefined) return 0;
  const parsed = Number(String(value).replace(/,/g, "."));
  return Number.isFinite(parsed) ? parsed : 0;
}

function totalD8(
  users: UserDashboardItem[],
  key: keyof Pick<
    UserDashboardItem,
    "main_balance" | "bonus_balance" | "available_kwh" | "total_generated_kwh"
  >,
): string {
  return users.reduce(
    (acc, user) => sumScaledDown(acc, String(user[key] || "0"), 8),
    "0",
  );
}

function userDisplayName(user?: UserDashboardItem | null): string {
  if (!user) return "не выбран";
  const username = String(user.username || "").trim();
  return username ? `@${username}` : "пользователь без username";
}

function freshnessLabel(props: AdminUsersDashboardRuntimeProps): string {
  if (props.error) return "ошибка среза";
  if (props.loading) return "обновление списка";
  if (!props.users.length) return "пустой срез";
  return "срез загружен";
}

function segmentLabel(segment: UserSegment): string {
  if (segment === "active") return "Активные";
  if (segment === "inactive") return "Неактивные";
  if (segment === "vip") return "VIP";
  if (segment === "wallets") return "Кошельки TON";
  return "Все";
}


function buildStatusPoints(
  activeCount: number,
  inactiveCount: number,
  vipCount: number,
  walletCount: number,
): UserChartPoint[] {
  return [
    {
      id: "active",
      label: "Активные",
      value: activeCount,
      tone: "success",
    },
    {
      id: "inactive",
      label: "Неактивные",
      value: inactiveCount,
      tone: "warning",
    },
    {
      id: "vip",
      label: "VIP",
      value: vipCount,
      tone: "info",
    },
    {
      id: "wallets",
      label: "Кошельки TON",
      value: walletCount,
      tone: "neutral",
    },
  ];
}

export function AdminUsersDashboardRuntime(
  props: AdminUsersDashboardRuntimeProps,
) {
  const [segment, setSegment] = useState<UserSegment>("all");
  const users = props.users;
  const syncUserFilter = useCallback(
    (user: UserDashboardItem) => {
      if (segment === "active") return user.is_active;
      if (segment === "inactive") return !user.is_active;
      if (segment === "vip") return user.is_vip;
      if (segment === "wallets") return Boolean(user.ton_wallet);
      return true;
    },
    [segment],
  );
  const largeFilter = useLargeAdminFilter(
    users,
    "users",
    { segment },
    syncUserFilter,
  );
  const filteredUsers = largeFilter.filtered;
  const activeCount = users.filter((user) => user.is_active).length;
  const inactiveCount = Math.max(0, users.length - activeCount);
  const vipCount = users.filter((user) => user.is_vip).length;
  const walletCount = users.filter((user) => user.ton_wallet).length;
  const usersMainTotal = totalD8(users, "main_balance");
  const usersBonusTotal = totalD8(users, "bonus_balance");
  const usersTotalBalance = sumScaledDown(usersMainTotal, usersBonusTotal, 8);
  const generatedKwh = totalD8(users, "total_generated_kwh");
  const availableKwh = totalD8(users, "available_kwh");
  const selectedBalance = props.selected
    ? sumScaledDown(props.selected.main_balance, props.selected.bonus_balance, 8)
    : "0";
  const activePercent = users.length
    ? Math.round((activeCount / users.length) * 100)
    : 0;
  const walletPercent = users.length
    ? Math.round((walletCount / users.length) * 100)
    : 0;
  const statusPoints = buildStatusPoints(
    activeCount,
    inactiveCount,
    vipCount,
    walletCount,
  );
  const freshness = props.error
    ? "stale"
    : props.loading
      ? "unknown"
      : users.length
        ? "fresh"
        : "stale";

  return (
    <section
      className="efhc-admin-users-dashboard-runtime"
      data-admin-users-dashboard-runtime="1484"
      data-admin-users-truth="raw-derived"
      data-admin-users-no-synthetic="true"
      data-admin-users-no-write-actions="true"
      data-admin-users-no-raw-payload="true"
      data-admin-users-no-debug-json="true"
      data-admin-users-no-secrets="true"
      data-admin-users-no-raw-tg-id="true"
      data-admin-worker-filter={largeFilter.workerActive ? "active" : "idle"}
    >
      <AdminDashboardToolbar
        title="Пользователи"
        subtitle="Сводка пользователей, балансов и статусов."
        breadcrumb="Админ-панель / Пользователи"
        refresh={(
          <AdminRefreshPicker
            label="Обновление"
            onRefresh={props.onRefresh}
            refreshLabel="Обновить пользователей"
            value="manual"
          />
        )}
        updatedAt={props.updatedAt || "Результаты поиска"}
        freshness={(
          <AdminFreshnessBadge
            freshness={freshness}
            label={freshnessLabel(props)}
            updatedAt={props.updatedAt || "Текущие данные"}
          />
        )}
        filters={(
          <AdminFilterBar
            groups={[
              {
                key: "users-segment",
                label: "Сегмент",
                value: segment,
                queryKey: "users_segment",
                querySync: "safe_display_only",
                options: [
                  { key: "all", label: "Все" },
                  { key: "active", label: "Активные" },
                  { key: "inactive", label: "Неактивные" },
                  { key: "vip", label: "VIP" },
                  { key: "wallets", label: "Кошельки TON" },
                ],
                onChange: (value) => setSegment(value as UserSegment),
              },
            ]}
            onReset={() => setSegment("all")}
            resetLabel="Сбросить"
          />
        )}
      />

      <AdminDashboardGrid>
        <AdminKpiCard
          label="Пользователи"
          value={String(users.length)}
          meta={`сегмент: ${segmentLabel(segment)}`}
          hint="Текущий результат поиска."
          tone="neutral"
        />
        <AdminKpiCard
          label="Активные"
          value={String(activeCount)}
          meta={`${activePercent}%`}
          hint="Расчёт по результатам поиска."
          tone="success"
        />
        <AdminKpiCard
          label="VIP"
          value={String(vipCount)}
          meta="статус пользователя"
          hint="Отображение статуса без изменения VIP."
          tone="info"
        />
        <AdminKpiCard
          label="Кошельки TON"
          value={String(walletCount)}
          meta={`${walletPercent}%`}
          hint="Количество привязанных кошельков."
          tone="warning"
        />
      </AdminDashboardGrid>

      <div className="efhc-admin-users-dashboard-grid">
        <AdminPanelChrome
          title="Распределение пользователей"
          subtitle="Распределение пользователей по текущему состоянию."
          status={props.error ? "error" : users.length ? "success" : "empty"}
          tone="info"
          source="Пользователи"
          updatedAt={props.updatedAt || "Результаты поиска"}
        >
          <AdminMiniBarChart
            ariaLabel="Распределение пользователей по статусам"
            dataKind="derived"
            points={statusPoints}
            source="Расчёт по текущему списку пользователей"
            unit="пользователи"
          />
          <div className="efhc-admin-users-dashboard-status-grid">
            {statusPoints.map((point) => (
              <span key={point.id}>
                <b>{point.label}</b>
                <strong>{point.value.toLocaleString("ru-RU")}</strong>
              </span>
            ))}
          </div>
        </AdminPanelChrome>

        <AdminPanelChrome
          title="Балансы пользователей"
          subtitle="Основной и бонусный балансы, kWh и сведения выбранного пользователя."
          status={users.length ? "success" : "stale"}
          tone="success"
          source="Результаты поиска и выбранный пользователь"
          updatedAt={props.updatedAt || "Текущие данные"}
        >
          <div className="efhc-admin-users-dashboard-balance-grid">
            <span>
              <b>Основной баланс</b>
              <strong>{formatD8ToHuman(usersMainTotal)}</strong>
            </span>
            <span>
              <b>Бонусный баланс</b>
              <strong>{formatD8ToHuman(usersBonusTotal)}</strong>
            </span>
            <span>
              <b>Общий баланс EFHC</b>
              <strong>{formatD8ToHuman(usersTotalBalance)}</strong>
            </span>
            <span>
              <b>Доступно kWh</b>
              <strong>{format8(availableKwh)}</strong>
            </span>
            <span>
              <b>Сгенерировано kWh</b>
              <strong>{format8(generatedKwh)}</strong>
            </span>
            <span>
              <b>Баланс выбранного пользователя</b>
              <strong>{formatD8ToHuman(selectedBalance)}</strong>
            </span>
          </div>
        </AdminPanelChrome>

        <AdminPanelChrome
          title="Активность пользователей"
          subtitle="Основные показатели выбранных пользователей."
          status={users.length ? "success" : "stale"}
          tone="warning"
          source="Расчётное значение"
          updatedAt={props.updatedAt || "Текущие данные"}
        >
          <AdminProgressBar
            label="Доля активных"
            value={activePercent}
            max={100}
            dataKind="derived"
            source="Доля активных пользователей"
          />
          <AdminProgressBar
            label="Доля с кошельками"
            value={walletPercent}
            max={100}
            dataKind="derived"
            source="Доля пользователей с кошельками"
          />
          <AdminHeatStrip
            ariaLabel="Состояние пользователей"
            dataKind="derived"
            points={[
              { id: "search", label: "Показано", value: users.length, tone: "info" },
              { id: "active", label: "Активные", value: activeCount, tone: "success" },
              { id: "inactive", label: "Неактивные", value: inactiveCount, tone: "warning" },
              { id: "selected", label: "Выбран пользователь", value: props.selected ? 1 : 0, tone: "neutral" },
            ]}
            source="Расчёт по текущему списку"
          />
        </AdminPanelChrome>

        <AdminPanelChrome
          title="Детали пользователя"
          subtitle="Быстрые действия для выбранного пользователя."
          status="success"
          tone="neutral"
          source="Пользователи"
        >
          <AdminFlowMapCard
            title="Действия пользователя"
            nodes={[
              {
                label: "Найдено",
                value: String(filteredUsers.length),
                hint: "Пользователи в текущем списке",
              },
              {
                label: "Выбран",
                value: userDisplayName(props.selected),
                hint: "Имя пользователя",
              },
              {
                label: "Банк",
                value: "Финансовые действия",
                hint: "Финансовые действия требуют подтверждения",
              },
              {
                label: "История",
                value: "Доступна",
                hint: "Основные сведения пользователя",
              },
            ]}
          />
          <div className="efhc-admin-users-dashboard-boundary">
            <AdminStatusBadge label="Просмотр данных" tone="success" />
            <AdminStatusBadge label="Основные данные" tone="warning" />
            <AdminStatusBadge label="Основные сведения" tone="warning" />
            <AdminStatusBadge label="Просмотр без изменения данных" tone="success" />
            <AdminStatusBadge label="Основной идентификатор — Global ID" tone="neutral" />
          </div>
        </AdminPanelChrome>
      </div>
    </section>
  );
}
