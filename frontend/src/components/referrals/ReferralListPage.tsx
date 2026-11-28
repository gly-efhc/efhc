import React, { useContext, useMemo } from "react";
import { useRouter } from "next/router";
import { useInterfaceVariantSurface } from "../../hooks/useInterfaceVariantSurface";
import { Card } from "../ui/Card";
import { Button } from "../ui/Button";
import { Badge } from "../ui/Badge";
import { Skeleton } from "../ui/Skeleton";
import { EmptyState } from "../ui/EmptyState";
import { StatusIndicator } from "../StatusIndicator";
import { useT } from "../../hooks/useT";
import { useInterfaceCustomization } from "../../hooks/useInterfaceCustomization";
import { resolveHeaderThemeComposition } from "../../lib/headerThemeComposition";
import {
  useReferralList,
  useReferralStats,
} from "../../queries/useReferrals";
import { sortReferralItemsNewestFirst } from "../../services/referrals.service";
import { LayoutContext } from "../Layout";
import {
  hapticSelection,
  hapticSoft,
  isTelegramMiniApp,
} from "../../lib/telegram";

type Props = {
  tab: "active" | "inactive";
};

export function ReferralListPage(props: Props) {
  const browserMode = !isTelegramMiniApp();
  const t = useT();
  const router = useRouter();
  const ctx = useContext(LayoutContext);
  const customization = useInterfaceCustomization();
  const statusColor = resolveHeaderThemeComposition(
    customization.effective.HS,
  ).statuses;
  const referralsSurface = useInterfaceVariantSurface<HTMLDivElement>(
    "RG",
    { dotsPlacement: "above" },
  );


  const statsQ = useReferralStats();
  const listQ = useReferralList(props.tab);

  const items = useMemo(() => {
    const loaded = (listQ.data?.pages || []).flatMap(
      (page) => page.items || [],
    );
    return sortReferralItemsNewestFirst(loaded);
  }, [listQ.data]);

  const title =
    props.tab === "active"
      ? t("referrals.active_page")
      : t("referrals.inactive_page");
  const activeCount = statsQ.data?.active_referrals ?? 0;
  const inactiveCount = statsQ.data?.inactive_referrals ?? 0;
  const totalCount = statsQ.data?.total_referrals ?? 0;
  const currentCount = props.tab === "active" ? activeCount : inactiveCount;
  const loading = listQ.isFetching && items.length === 0;

  const refreshAll = () => {
    hapticSelection(ctx.settings.haptics_enabled);
    ctx.toast(t("common.refresh"), "info");
    void statsQ.refetch();
    void listQ.refetch();
  };

  const openTab = (nextTab: "active" | "inactive") => {
    if (nextTab === props.tab) return;
    hapticSelection(ctx.settings.haptics_enabled);
    void router.push(
      nextTab === "active" ? "/referrals/active" : "/referrals/inactive",
    );
  };

  const onLoadMore = async () => {
    hapticSelection(ctx.settings.haptics_enabled);
    await listQ.fetchNextPage();
    hapticSoft(ctx.settings.haptics_enabled);
  };

  const emptyDetail =
    props.tab === "active"
      ? t("referrals.empty_active_detail")
      : t("referrals.empty_inactive_detail");

  return (
    <div
      ref={referralsSurface.ref}
      {...referralsSurface.handlers}
      className="grid gap-4 efhc-referrals-shell"
      data-rg={referralsSurface.variant}
      data-referrals-subpage={props.tab}
    >
      <section className="efhc-subpage-hero p-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-2xl font-bold">{title}</div>
            <div className="mt-1 text-sm efhc-text-muted2">
              {props.tab === "active"
                ? t("referrals.active_page_hint")
                : t("referrals.inactive_page_hint")}
            </div>
          </div>
          <Badge>
            {t("referrals.total_count_short")}: {currentCount}
          </Badge>
        </div>
      </section>

      <div className="efhc-segmented efhc-referrals-tabs efhc-referrals-segment-surface" data-referrals-segments="active-inactive">
        <Button variant={props.tab === "active" ? "primary" : "secondary"} onClick={() => openTab("active")}>
          {t("referrals.active")} ({activeCount})
        </Button>
        <Button variant={props.tab === "inactive" ? "primary" : "secondary"} onClick={() => openTab("inactive")}>
          {t("referrals.inactive")} ({inactiveCount})
        </Button>
      </div>

      <Card
        title={title}
        data-referrals-active-inactive-boundary="1296"
      >
        <div className="grid gap-2">
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
              title={
                props.tab === "active"
                  ? t("referrals.empty_active")
                  : t("referrals.empty_inactive")
              }
              detail={emptyDetail}
              actionLabel={
                browserMode ? t("referrals.open_profile") : t("common.refresh")
              }
              onAction={browserMode ? () => router.push("/") : refreshAll}
            />
          ) : null}

          {listQ.isError ? (
            <EmptyState
              title={t("common.error")}
              detail={t("referrals.load_error")}
              actionLabel={
                browserMode ? t("referrals.open_profile") : t("common.refresh")
              }
              onAction={browserMode ? () => router.push("/") : refreshAll}
            />
          ) : null}

          <div className="flex flex-wrap items-center gap-2 mt-2">
            {listQ.hasNextPage ? (
              <Button
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
              onClick={refreshAll}
            >
              {t("common.refresh")}
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
}
