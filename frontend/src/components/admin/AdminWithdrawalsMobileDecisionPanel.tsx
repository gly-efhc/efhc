import React, { useMemo } from "react";
import { AdminCompactOperationList } from "./AdminCompactOperationList";
import {
  AdminActionTable,
  AdminChartCard,
  AdminConfirmationBlock,
  AdminEmptyState,
  AdminFilterBar,
  AdminFlowMapCard,
  AdminKpiCard,
  AdminSectionHeader,
  AdminStatusBadge,
} from "./AdminDashboardUiKit";
import type { AdminWithdrawOutcomePreviewResponse } from "../../lib/api/generated/adminSeams";
import { formatD8ToHuman } from "../../lib/format";
import {
  adminWithdrawOutcomeLabel,
  adminWithdrawStatusLabel,
} from "../../lib/humanLabels";
import type { DbId } from "../../types/db-id";

type WithdrawalLike = {
  id: DbId;
  global_id: string;
  amount_efhc: string;
  status: string;
  created_at: string;
  external_address: string | null;
  is_vip: boolean;
  payout_asset?: string | null;
  tonconnect_transport_kind?: string | null;
};

type Props = {
  items: WithdrawalLike[];
  selected: WithdrawalLike | null;
  selectedId: DbId | null;
  status: string;
  vipOnly: boolean;
  loading: boolean;
  repairBusy: boolean;
  repairNote?: string | null;
  previewMode: string;
  previewLoading: boolean;
  preview?: AdminWithdrawOutcomePreviewResponse | null;
  onStatusChange: (value: string) => void;
  onVipOnlyChange: (value: boolean) => void;
  onSelect: (id: DbId) => void;
  onRefresh: () => void;
  onRepair: () => void;
  onPreviewModeChange: (value: string) => void;
};

function countByStatus(items: WithdrawalLike[], status: string): number {
  return items.filter((item) => item.status === status).length;
}

function toneForStatus(status: string) {
  if (status === "PAID") return "success" as const;
  if (status === "PENDING") return "warning" as const;
  if (status === "REJECTED" || status === "CANCELED") {
    return "neutral" as const;
  }
  return "primary" as const;
}

function shortAddress(value: string | null): string {
  if (!value) return "адрес не задан";
  if (value.length <= 18) return value;
  return `${value.slice(0, 8)}…${value.slice(-8)}`;
}

function statusHint(status: string): string {
  if (status === "PENDING") return "ожидает действия оператора";
  if (status === "PAID") return "выплата завершена";
  if (status === "REJECTED") return "заявка отклонена";
  if (status === "CANCELED") return "заявка отменена";
  if (status === "ERROR") return "требует проверки";
  return "операторское состояние";
}

export function AdminWithdrawalsMobileDecisionPanel(props: Props) {
  const pending = countByStatus(props.items, "PENDING");
  const paid = countByStatus(props.items, "PAID");
  const rejected = countByStatus(props.items, "REJECTED");
  const canceled = countByStatus(props.items, "CANCELED");
  const error = countByStatus(props.items, "ERROR");

  const visibleDeck = useMemo(() => props.items.slice(0, 8), [props.items]);

  const selectedAmount = props.selected
    ? `${formatD8ToHuman(props.selected.amount_efhc)} EFHCm`
    : "—";

  return (
    <section
      className="efhc-admin-withdraw-mobile"
      data-admin-sandbox-source="ui-main:data-table mobile drawer pattern; section-cards; chart-area-interactive; MaterialM dashboard cards"
    >
      <AdminSectionHeader
        eyebrow="Выплаты пользователям"
        title="Очередь заявок на выплату"
        subtitle={
          "Каждая карточка — одна заявка пользователя: проверьте сумму и кошелёк, " +
          "затем выполните выплату или завершите заявку безопасным решением."
        }
        actions={
          <button
            type="button"
            className="efhc-admin-live-dashboard_live"
            onClick={props.onRefresh}
            disabled={props.loading}
          >
            {props.loading ? "Обновляется" : "Обновить данные"}
          </button>
        }
      />

      <AdminFilterBar
        groups={[
          {
            label: "Статус",
            value: props.status,
            options: [
              { key: "PENDING", label: `Ожидает ${pending}` },
              { key: "PAID", label: `Выплачено ${paid}` },
              { key: "REJECTED", label: `Отклонено и возвращено ${rejected}` },
              { key: "CANCELED", label: `Отменено ${canceled}` },
              { key: "ERROR", label: `Ошибка ${error}` },
            ],
            onChange: props.onStatusChange,
          },
          {
            label: "Слой",
            value: props.vipOnly ? "vip" : "all",
            options: [
              { key: "all", label: "Все" },
              { key: "vip", label: "VIP" },
            ],
            onChange: (value) => props.onVipOnlyChange(value === "vip"),
          },
          {
            label: "Что увидит пользователь",
            value: props.previewMode,
            options: [
              { key: "auto", label: "Авто" },
              { key: "success", label: "Успех" },
              { key: "reject", label: "Отклонение" },
            ],
            onChange: props.onPreviewModeChange,
          },
        ]}
      />

      <div className="efhc-admin-withdraw-mobile_kpis">
        <AdminKpiCard
          instanceId="withdrawals-summary-total"
          eamFamily="EAM-ADMIN-015"
          visualPrimitive="ADMIN_SUMMARY_KPI"
          label="Всего в текущем фильтре"
          value={props.items.length}
          meta="текущий список"
          tone="primary"
        />
        <AdminKpiCard
          instanceId="withdrawals-summary-pending"
          eamFamily="EAM-ADMIN-015"
          visualPrimitive="ADMIN_SUMMARY_KPI"
          label="Ожидает решения"
          value={pending}
          meta="нужно решение"
          tone="warning"
        />
        <AdminKpiCard
          instanceId="withdrawals-summary-paid"
          eamFamily="EAM-ADMIN-015"
          visualPrimitive="ADMIN_SUMMARY_KPI"
          label="Выплачено"
          value={paid}
          meta="завершено"
          tone="success"
        />
        <AdminKpiCard
          instanceId="withdrawals-summary-rejected"
          eamFamily="EAM-ADMIN-015"
          visualPrimitive="ADMIN_SUMMARY_KPI"
          label="Отклонено и возвращено / отменено"
          value={rejected + canceled}
          meta="завершено без выплаты"
          tone="neutral"
        />
      </div>

      <AdminFlowMapCard
        title="Порядок решения по заявке"
        nodes={[
          {
            label: "1. Заявка",
            value: props.selected ? `#${props.selected.id}` : "нет",
            hint: props.selected
              ? `ID EFHC ${props.selected.global_id}`
              : "выберите заявку",
            active: Boolean(props.selected),
          },
          {
            label: "2. Удержание",
            value: selectedAmount,
            hint: "EFHC удержан до результата",
            active: Boolean(props.selected),
          },
          {
            label: "3. Выплата",
            value: props.selected?.payout_asset || "EFHCm",
            hint:
              props.selected?.tonconnect_transport_kind ||
              "выплата через подключённый способ",
            active:
              props.selected?.status === "PENDING" ||
              props.selected?.status === "ERROR",
          },
          {
            label: "4. Результат",
            value: props.selected
                ? adminWithdrawStatusLabel(props.selected.status)
                : "—",
            hint: props.selected
              ? statusHint(props.selected.status)
              : "нет выбранной заявки",
            active: Boolean(props.selected),
          },
        ]}
      />

      <div className="efhc-admin-withdraw-mobile_grid">
        <AdminChartCard
          title="Заявки, ожидающие решения"
          subtitle="Карточки адаптированы под палец и экран телефона"
          meta={<AdminStatusBadge label="удобно на телефоне" tone="primary" />}
        >
          {visibleDeck.length ? (
            <AdminCompactOperationList
              rows={visibleDeck.map((item) => ({
                id: item.id,
                operation: `#${item.id} · ${adminWithdrawStatusLabel(item.status)}`,
                amount: `${formatD8ToHuman(item.amount_efhc)} EFHCm`,
                subject: `Global ID ${item.global_id}`,
                time: item.created_at || "—",
                onClick: () => props.onSelect(item.id),
                active: props.selectedId === item.id,
                ariaLabel: `Открыть заявку ${item.id}`,
              }))}
            />
          ) : (
            <AdminEmptyState
              title="Нет заявок в выбранном слое"
              text="Смените статус или отключите VIP-фильтр."
            />
          )}
        </AdminChartCard>

        <AdminActionTable
          title="Выбранная заявка"
          rows={[
            {
              label: "Номер",
              value: props.selected ? `#${props.selected.id}` : "—",
              hint: "Номер заявки",
            },
            {
              label: "Статус",
              value: props.selected
                ? adminWithdrawStatusLabel(props.selected.status)
                : "—",
              hint: props.selected
                ? statusHint(props.selected.status)
                : "нет выбора",
            },
            {
              label: "Сумма",
              value: selectedAmount,
              hint: "только основной EFHC доступен для вывода",
            },
            {
              label: "Кошелёк",
              value: shortAddress(props.selected?.external_address || null),
              hint: "не редактируется вручную",
            },
            {
              label: "Что увидит пользователь",
              value: props.previewLoading
                ? "загрузка"
                : adminWithdrawOutcomeLabel(
                    props.preview?.bundle.outcome_kind,
                  ),
              hint: "результат после решения по заявке",
            },
          ]}
        />
      </div>

      <AdminConfirmationBlock
        title="Завершённые заявки защищены от повторного изменения"
        text={
          "Выплачено, отклонено и отменено являются финальными " +
          "зонами контроля. Операторская интерактивность помогает " +
          "выбирать и проверять заявку, но не меняет экономику вывода " +
          "и не обходит подтверждение."
        }
        confirmed
      />

      <div className="efhc-admin-withdraw-mobile_actions">
        <button
          type="button"
          onClick={props.onRefresh}
          disabled={props.loading}
        >
          {props.loading ? "Обновление…" : "Обновить данные"}
        </button>
        <button
          type="button"
          onClick={props.onRepair}
          disabled={props.repairBusy || props.loading}
        >
          {props.repairBusy ? "Проверка…" : "Проверить и восстановить состояние"}
        </button>
      </div>

      {props.repairNote ? (
        <AdminConfirmationBlock
          title="Последняя проверка согласованности"
          text={props.repairNote}
          confirmed
        />
      ) : null}
    </section>
  );
}
