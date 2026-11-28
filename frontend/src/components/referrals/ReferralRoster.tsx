import React, { useContext, useMemo } from "react";

import { LayoutContext } from "../Layout";
import { Button } from "../ui/Button";
import { EmptyState } from "../ui/EmptyState";
import { Skeleton } from "../ui/Skeleton";
import { StatusIndicator } from "../StatusIndicator";
import { useT } from "../../hooks/useT";
import { hapticSelection, hapticSoft } from "../../lib/telegram";
import { useReferralList } from "../../queries/useReferrals";
import { useInterfaceCustomization } from "../../hooks/useInterfaceCustomization";
import { resolveHeaderThemeComposition } from "../../lib/headerThemeComposition";
import {
  sortReferralItemsNewestFirst,
  type ReferralTab,
} from "../../services/referrals.service";

type Props = {
  tab: ReferralTab;
};

export function ReferralRoster(props: Props) {
  const t = useT();
  const ctx = useContext(LayoutContext);
  const listQ = useReferralList(props.tab);
  const customization = useInterfaceCustomization();
  const statusColor = resolveHeaderThemeComposition(
    customization.effective.HS,
  ).statuses;

  const items = useMemo(() => {
    const loaded = (listQ.data?.pages || []).flatMap(
      (page) => page.items || [],
    );
    return sortReferralItemsNewestFirst(loaded);
  }, [listQ.data]);

  const refresh = () => {
    hapticSelection(ctx.settings.haptics_enabled);
    void listQ.refetch();
  };

  const onLoadMore = async () => {
    hapticSelection(ctx.settings.haptics_enabled);
    await listQ.fetchNextPage();
    hapticSoft(ctx.settings.haptics_enabled);
  };

  const loading = listQ.isFetching && items.length === 0;
  const emptyTitle =
    props.tab === "active"
      ? t("referrals.empty_active")
      : t("referrals.empty_inactive");
  const emptyDetail =
    props.tab === "active"
      ? t("referrals.empty_active_detail")
      : t("referrals.empty_inactive_detail");

  return (
    <div
      className="grid gap-2"
      data-referrals-active-inactive-boundary="1296"
      data-referrals-inline-list={props.tab}
    >
      {items.map((item) => (
        <div
          key={item.username || item.joined_at || item.child_global_id}
          className="efhc-list-row"
          data-referral-row="username-only"
        >
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold">
              {item.username
                ? `@${item.username}`
                : t("referrals.user_hidden_fallback")}
            </div>
            <div className="text-xs efhc-text-muted2">
              {item.total_generated_kwh
                ? `${item.total_generated_kwh} kWh`
                : ""}
              {typeof item.panels_count === "number"
                ? ` • ${t("referrals.panels_count_label")}: ` +
                  `${item.panels_count}`
                : ""}
            </div>
          </div>
          <span
            className="efhc-status-indicator-context efhc-referral-activ-indicator"
            data-sc={statusColor}
          >
            <StatusIndicator
              kind="activ"
              active={item.is_active}
              label={t("profile.activ_badge")}
            />
          </span>
        </div>
      ))}

      {loading ? (
        <div className="grid gap-2">
          <Skeleton className="h-16" />
          <Skeleton className="h-16" />
        </div>
      ) : null}

      {items.length === 0 && !listQ.isFetching ? (
        <EmptyState
          title={emptyTitle}
          detail={emptyDetail}
          actionLabel={t("common.refresh")}
          onAction={refresh}
        />
      ) : null}

      {listQ.isError ? (
        <EmptyState
          title={t("common.error")}
          detail={t("referrals.load_error")}
          actionLabel={t("common.refresh")}
          onAction={refresh}
        />
      ) : null}

      <div className="mt-2 flex flex-wrap items-center gap-2">
        {listQ.hasNextPage ? (
          <Button
            data-referrals-load-more="true"
            disabled={listQ.isFetching}
            onClick={() => void onLoadMore()}
          >
            {listQ.isFetching ? t("common.loading") : t("common.load_more")}
          </Button>
        ) : (
          <span className="text-xs efhc-text-muted2">
            {t("common.end")}
          </span>
        )}
        <Button
          variant="secondary"
          disabled={listQ.isFetching}
          onClick={refresh}
        >
          {t("common.refresh")}
        </Button>
      </div>
    </div>
  );
}
