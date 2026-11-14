import React, { useContext, useMemo } from "react";
import { useT } from "../../hooks/useT";
import { LayoutContext } from "../Layout";
import { Button } from "../ui/Button";
import { BalanceSummaryCard } from "./history/BalanceSummaryCard";
import { BalanceHistoryEmptyState } from "./history/BalanceHistoryEmptyState";
import {
  HistoryOperationFeed,
  type HistoryOperationModel,
} from "./history/HistoryOperationFeed";
import { useInterfaceVariantSurface } from "../../hooks/useInterfaceVariantSurface";
import {
  balanceTypeLabel,
  historyOperationKindLabel,
  historySourceLabel,
  historyStatusLabel,
} from "../../lib/humanLabels";
import type { ProfileHistoryItem } from "../../services/profile.service";

export type HistoryFilter =
  | "all"
  | "purchases"
  | "exchange"
  | "withdraw"
  | "bonuses"
  | "panels";

type Props = {
  totalBalance: string;
  mainBalance: string;
  bonusBalance: string;
  items: ProfileHistoryItem[];
  loading: boolean;
  error: string | null;
  nextCursor: string | null;
  activeFilter: string;
  onFilterChange: (filter: HistoryFilter) => void;
  onRefresh: () => void;
  onLoadMore: () => void;
  onExportCsv?: () => void;
  onExportXlsx?: () => void;
  withdrawHref?: string;
  exporting?: boolean;
  reasonLabel: (reason: string) => string;
};

const FILTERS: HistoryFilter[] = [
  "all",
  "purchases",
  "exchange",
  "withdraw",
  "bonuses",
  "panels",
];

export function normalizeHistoryFilter(value: string): HistoryFilter {
  return FILTERS.includes(value as HistoryFilter)
    ? (value as HistoryFilter)
    : "all";
}

function filterLabelKey(filter: HistoryFilter): string {
  return `history.filter_${filter}`;
}

function pageHintKey(filter: HistoryFilter): string {
  return `history.page_${filter}_hint`;
}

function categoryForItem(item: ProfileHistoryItem): HistoryFilter | "other" {
  const reason = String(item.reason || "").toLowerCase();
  if (item.kind === "exchange" || reason.includes("exchange")) return "exchange";
  if (item.source === "withdraw_request" || reason.includes("withdraw")) return "withdraw";
  if (reason.includes("panel")) return "panels";
  if (
    item.balance_type === "bonus"
    || reason.includes("bonus")
    || reason.includes("referral")
    || reason.includes("task")
    || reason.includes("ad_")
  ) return "bonuses";
  if (
    item.source === "shop_order"
    || item.source === "payment_intent"
    || reason.includes("shop")
    || reason.includes("payment")
    || reason.includes("deposit")
    || reason.includes("purchase")
  ) return "purchases";
  return "other";
}

function statusKind(status: string | null): HistoryOperationModel["statusKind"] {
  const value = String(status || "completed").toLowerCase();
  if (["paid", "confirmed", "completed", "done", "success", "approved", "paid_auto"].includes(value)) return "done";
  if (["rejected", "failed", "error", "canceled", "cancelled", "expired"].includes(value)) return "failed";
  if (["pending", "processing", "confirming", "network_processing", "retrying", "external_detected", "paid_pending_manual"].includes(value)) return "pending";
  return "neutral";
}

function dateTimeDetail(value: string, locale: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString(locale, {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function ProfileHistorySection(props: Props) {
  const t = useT();
  const { lang } = useContext(LayoutContext);
  const historySurface = useInterfaceVariantSurface<HTMLDivElement>("HI", {
    dotsPlacement: "below",
  });
  const variant = historySurface.variant;
  const activeFilter = normalizeHistoryFilter(props.activeFilter);

  const operations = useMemo<HistoryOperationModel[]>(() => (
    props.items
      .filter((item) => activeFilter === "all" || categoryForItem(item) === activeFilter)
      .map((item) => {
        const status = historyStatusLabel(item.status || "completed", t);
        const reason = item.reason || item.kind;
        const sourceLabel = historySourceLabel(item.source, t);
        const kindLabel = historyOperationKindLabel(item.kind, t);
        const title = item.source === "withdraw_request"
          ? t("history.reason.withdraw")
          : props.reasonLabel(reason);
        const amount = item.amount_efhc || item.amount_asset || "0";
        const asset = item.asset || (item.balance_type === "bonus" ? "EFHCb" : "EFHCm");
        const direction = item.direction === "credit" || item.direction === "debit"
          ? item.direction
          : "neutral";
        const details = [
          { label: t("history.detail_operation_id"), value: `#${item.id}` },
          { label: t("history.detail_date"), value: dateTimeDetail(item.occurred_at, lang) },
          { label: t("history.detail_status"), value: status },
          { label: t("history.detail_type"), value: kindLabel },
        ];
        if (item.balance_type) {
          details.push({
            label: t("history.detail_balance"),
            value: balanceTypeLabel(item.balance_type, t),
          });
        }
        return {
          key: `${item.source}:${item.id}`,
          title,
          subtitle: `${sourceLabel} · ${status}`,
          createdAt: item.occurred_at,
          amount,
          asset,
          tone: direction,
          status,
          statusKind: statusKind(item.status),
          details,
        };
      })
  ), [activeFilter, lang, props.items, props.reasonLabel, t]);

  const showReadError = Boolean(props.error) && !props.loading && props.items.length === 0;
  const showFilterEmpty = !props.error && !props.loading && props.items.length > 0 && operations.length === 0;

  const balances = (
    <div
      className="efhc-history-balance-stack"
      data-history-balances="total-main-bonus"
      data-history-block="balances"
    >
      <BalanceSummaryCard title={t("history.balance_total_asset")} value={props.totalBalance} tone="neutral" asset="EFHC" />
      <BalanceSummaryCard title={t("history.balance_main_asset")} value={props.mainBalance} tone="main" asset="EFHCm" />
      <BalanceSummaryCard title={t("history.balance_bonus_asset")} value={props.bonusBalance} tone="bonus" asset="EFHCb" />
    </div>
  );

  return (
    <div
      ref={historySurface.ref}
      {...historySurface.handlers}
      className="efhc-history-financial-section efhc-history-bank-module efhc-history-trust-section space-y-4"
      data-hi={variant}
      data-hi-family="global-theme"
      data-hi-ux="banking-operation-center"
      data-public-surface="history"
      data-history-layout="banking-operation-center"
      data-history-source="profile-history-unified-keyset-50"
      data-history-online-page-size={50}
      data-history-active-page={activeFilter}
    >
      <div className="efhc-history-balance-header" data-history-fixed-header="balances">
        {balances}
      </div>

      <div className="efhc-history-section-head" data-history-block="head">
        <h2>{t("history.operations_title")}</h2>
        <div className="efhc-history-head-actions">
          {props.onExportCsv ? (
            <Button variant="secondary" onClick={props.onExportCsv} disabled={Boolean(props.exporting)} data-history-export="csv-server-side">
              {props.exporting ? t("history.exporting") : t("history.export_csv")}
            </Button>
          ) : null}
          {props.onExportXlsx ? (
            <Button variant="secondary" onClick={props.onExportXlsx} disabled={Boolean(props.exporting)} data-history-export="xlsx-server-side">
              {t("history.export_xlsx")}
            </Button>
          ) : null}
          <Button variant="secondary" onClick={props.onRefresh}>{t("common.refresh")}</Button>
          {props.withdrawHref ? (
            <Button href={props.withdrawHref} variant="secondary" data-history-withdraw-shortcut="head-grid">
              {t("history.open_withdraw")}
            </Button>
          ) : null}
        </div>
      </div>

      <div className="efhc-history-bank-nav" data-history-block="filters">
        <div className="efhc-history-filter-row" data-history-filters="bank-pages" role="tablist" aria-label={t("history.navigation_label")}>
          {FILTERS.map((filter) => (
            <button
              key={filter}
              type="button"
              role="tab"
              aria-selected={activeFilter === filter}
              className={`efhc-history-filter ${activeFilter === filter ? "efhc-history-filter--active" : ""}`}
              data-history-filter={filter}
              onClick={() => props.onFilterChange(filter)}
            >
              {t(filterLabelKey(filter))}
            </button>
          ))}
        </div>
        <div className="efhc-history-bank-page-hint">{t(pageHintKey(activeFilter))}</div>
      </div>

      {props.error && props.items.length > 0 ? (
        <div className="efhc-history-bank-source-warning" role="status">
          {t("history.partial_data_warning")}
        </div>
      ) : null}

      {activeFilter === "withdraw" ? (
        <div className="efhc-history-bank-page-title">{t("history.withdraw_requests")}</div>
      ) : null}

      {showReadError ? (
        <div data-history-state="read-error">
          <BalanceHistoryEmptyState
            title={t("profile.error_history")}
            body={t("history.load_error")}
            actionLabel={t("common.refresh")}
            onAction={props.onRefresh}
          />
        </div>
      ) : showFilterEmpty ? (
        <div data-history-state="filter-empty">
          <BalanceHistoryEmptyState
            title={`${t(filterLabelKey(activeFilter))}: ${t("history.empty_title")}`}
            body={t(pageHintKey(activeFilter))}
          />
        </div>
      ) : (
        <HistoryOperationFeed
          items={operations}
          loading={props.loading}
          hasMore={Boolean(props.nextCursor)}
          onLoadMore={props.onLoadMore}
          layout={variant === "HI-04" || variant === "HI-07" ? "flat" : "grouped"}
        />
      )}

    </div>
  );
}
