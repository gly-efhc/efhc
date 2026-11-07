import React, {
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Card } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { Skeleton } from "../../components/ui/Skeleton";
import { EmptyState } from "../../components/ui/EmptyState";
import { GamePageShell } from "../../components/ui/GameShell";
import { LayoutContext } from "../../components/Layout";
import { publicApiErrorMessage } from "../../lib/publicError";
import { shouldRequestNextPanelPage, type PanelPaginationTrigger } from "../../reconstruction/panelPaginationGate";
import { usePanelsList } from "../../queries/usePanels";
import { useT } from "../../hooks/useT";
import type { SyncSnapshot } from "../../hooks/useSnapshot";
import { format8 } from "../../lib/format";
import { confirmedPanelRateD8, projectPanelGeneratedD8 } from "../../lib/panelDisplayProjection";
import { hapticSelection } from "../../lib/telegram";
import { useInterfaceVariantSurface } from
  "../../hooks/useInterfaceVariantSurface";

function pad2(v: number): string {
  return v < 10 ? `0${v}` : String(v);
}

function formatUtcMinute(iso: string | null | undefined): string {
  if (!iso) return "—";
  const ms = Date.parse(iso);
  if (Number.isNaN(ms)) return "—";
  const d = new Date(ms);
  const dd = pad2(d.getUTCDate());
  const mm = pad2(d.getUTCMonth() + 1);
  const yy = String(d.getUTCFullYear());
  const hh = pad2(d.getUTCHours());
  const mi = pad2(d.getUTCMinutes());
  const ss = pad2(d.getUTCSeconds());
  // v866 standalone formats Russian UTC dates with the comma and seconds.
  return `${dd}.${mm}.${yy}, ${hh}:${mi}:${ss} UTC`;
}

const SECONDS_PER_DAY = 86400;
const SECONDS_PER_HOUR = 3600;
const SECONDS_PER_MINUTE = 60;

function formatRemaining(
  remainingSeconds: number | null,
  t: (key: string) => string,
): string {
  if (remainingSeconds === null) return "—";
  const s = Math.floor(remainingSeconds);
  if (s <= 0) return t("panels.countdown_expired");
  const days = Math.floor(s / SECONDS_PER_DAY);
  const afterDays = s % SECONDS_PER_DAY;
  const hours = Math.floor(afterDays / SECONDS_PER_HOUR);
  const afterHours = afterDays % SECONDS_PER_HOUR;
  const mins = Math.floor(afterHours / SECONDS_PER_MINUTE);
  const secs = afterHours % SECONDS_PER_MINUTE;
  return [
    `${days}${t("common.day_short")}`,
    `${hours}${t("common.hour_short")}`,
    `${mins}${t("common.min_short")}`,
    `${secs}${t("common.sec_short")}`,
  ].join(" ");
}

export default function PanelsPortfolioPage(props: {
  snap: SyncSnapshot | null;
}) {
  const t = useT();
  const { settings } = useContext(LayoutContext);
  const tabsSurface = useInterfaceVariantSurface<HTMLDivElement>("PT");
  const cardsSurface = useInterfaceVariantSurface<HTMLDivElement>("PC");
  const [tab, setTab] = useState<"active" | "archive">("active");
  const [sortDirection, setSortDirection] = useState<"oldest" | "newest">(
    "oldest",
  );
  const [tick, setTick] = useState(0);
  const [nowUtcMs, setNowUtcMs] = useState<number | null>(null);
  const [elapsedClientMs, setElapsedClientMs] = useState(0);
  const listQuery = usePanelsList(tab, sortDirection);

  const items = useMemo(
    () => listQuery.data?.pages.flatMap((page) => page.items) ?? [],
    [listQuery.data],
  );
  const orderedItems = useMemo(() => {
    const valueOf = (item: (typeof items)[number]) => {
      const iso = item.activated_at ?? item.created_at ?? "";
      const parsed = Date.parse(iso);
      return Number.isNaN(parsed) ? 0 : parsed;
    };
    return [...items].sort((left, right) => {
      const delta = valueOf(left) - valueOf(right);
      if (delta !== 0) {
        return sortDirection === "oldest" ? delta : -delta;
      }
      const leftId = Number(left.id) || 0;
      const rightId = Number(right.id) || 0;
      return sortDirection === "oldest"
        ? leftId - rightId
        : rightId - leftId;
    });
  }, [items, sortDirection]);

  const loading = listQuery.isLoading || listQuery.isFetchingNextPage;
  const err = listQuery.error
    ? publicApiErrorMessage(listQuery.error, t, "panels.load_error")
    : null;
  const canLoadMore = Boolean(listQuery.hasNextPage);
  const listServerNowIso =
    listQuery.data?.pages.at(-1)?.server_now_utc ?? null;
  const serverNowIso = listServerNowIso ?? props.snap?.meta?.server_now_iso ?? null;
  const countdownSource = "panel-list-server-now-plus-client-stopwatch";
  // A VIP owner may have a different effective rate for every active panel.
  // The exact server snapshot, never the unadjusted base rate, owns that truth.
  const confirmedPerPanelRateD8 = useMemo(() => confirmedPanelRateD8(
    props.snap?.meta.gen_per_sec_effective ?? null,
    props.snap?.panels.active_count ?? null,
  ), [props.snap?.meta.gen_per_sec_effective, props.snap?.panels.active_count]);
  const [anchorServerMs, setAnchorServerMs] = useState<number | null>(null);
  const [anchorClientMs, setAnchorClientMs] = useState<number | null>(null);
  const panelListViewportRef = useRef<HTMLDivElement | null>(null);
  const pendingScrollAnchorRef = useRef<{
    tab: "active" | "archive";
    itemCount: number;
    scrollTop: number;
    visibleId: string | null;
    topOffset: number;
  } | null>(null);
  // Guard against repeated scroll events advancing more than one 20-row
  // page. A new page needs a NEW bottom approach after a meaningful scroll;
  // merely re-rendering or restoring the visible panel cannot trigger it.
  const lastPageTriggerRef = useRef<PanelPaginationTrigger | null>(null);
  const inFlightPageTriggerRef = useRef<PanelPaginationTrigger | null>(null);
  const resetPageTrigger = () => {
    lastPageTriggerRef.current = null;
    inFlightPageTriggerRef.current = null;
    pendingScrollAnchorRef.current = null;
  };

  useEffect(() => {
    if (!serverNowIso) {
      setAnchorServerMs(null);
      setAnchorClientMs(null);
      return;
    }
    const ms = Date.parse(serverNowIso);
    if (Number.isNaN(ms)) {
      setAnchorServerMs(null);
      setAnchorClientMs(null);
      return;
    }
    setAnchorServerMs(ms);
    setAnchorClientMs(performance.now());
  }, [serverNowIso]);

  useEffect(() => {
    if (anchorServerMs === null || anchorClientMs === null) {
      setNowUtcMs(null);
      setElapsedClientMs(0);
      return undefined;
    }
    const updateNow = () => {
      const elapsed = Math.max(0, performance.now() - anchorClientMs);
      setNowUtcMs(anchorServerMs + elapsed);
      setElapsedClientMs(elapsed);
      setTick((value) => value + 1);
    };
    updateNow();
    // One shared local clock animates PNL D8 display values and countdowns.
    const id = globalThis.setInterval(updateNow, 333);
    return () => globalThis.clearInterval(id);
  }, [anchorServerMs, anchorClientMs]);

  const loadNextPanelsAtScrollEnd = () => {
    const node = panelListViewportRef.current;
    if (!node || !shouldRequestNextPanelPage({
      tab,
      direction: sortDirection,
      itemCount: items.length,
      scrollTop: node.scrollTop,
      clientHeight: node.clientHeight,
      scrollHeight: node.scrollHeight,
      lastTrigger: lastPageTriggerRef.current,
      inFlight: inFlightPageTriggerRef.current !== null,
      loading,
      canLoadMore,
    })) return;
    const request: PanelPaginationTrigger = {
      tab, direction: sortDirection,
      itemCount: items.length, scrollTop: node.scrollTop,
    };
    // The refs must be locked BEFORE fetchNextPage: an immediately repeated
    // scroll event can otherwise fetch the third batch in the same gesture.
    lastPageTriggerRef.current = request;
    inFlightPageTriggerRef.current = request;
    // Preserve the visible card, never add *all new content height* to
    // scrollTop: with normal append that old approach skipped whole cards.
    const viewportTop = node.getBoundingClientRect().top;
    const visible = Array.from(
      node.querySelectorAll<HTMLElement>("[data-panel-identity]"),
    ).find((element) => element.getBoundingClientRect().bottom > viewportTop);
    pendingScrollAnchorRef.current = {
      tab,
      itemCount: items.length,
      scrollTop: node.scrollTop,
      visibleId: visible?.dataset.panelIdentity ?? null,
      topOffset: visible
        ? visible.getBoundingClientRect().top - viewportTop
        : 0,
    };
    void listQuery.fetchNextPage().then(
      () => {
        if (inFlightPageTriggerRef.current === request) {
          inFlightPageTriggerRef.current = null;
        }
      },
      () => {
        if (inFlightPageTriggerRef.current === request) {
          inFlightPageTriggerRef.current = null;
          // A failed request may be retried by another bottom scroll.
          lastPageTriggerRef.current = null;
        }
      },
    );
  };

  useLayoutEffect(() => {
    const anchor = pendingScrollAnchorRef.current;
    const node = panelListViewportRef.current;
    if (!anchor || !node) return;
    if (anchor.tab !== tab) {
      pendingScrollAnchorRef.current = null;
      return;
    }
    if (items.length <= anchor.itemCount) return;
    const visible = Array.from(
      node.querySelectorAll<HTMLElement>("[data-panel-identity]"),
    ).find((element) => element.dataset.panelIdentity === anchor.visibleId);
    if (visible) {
      node.scrollTop +=
        visible.getBoundingClientRect().top -
        node.getBoundingClientRect().top -
        anchor.topOffset;
    } else {
      node.scrollTop = anchor.scrollTop;
    }
    pendingScrollAnchorRef.current = null;
  }, [items.length, tab]);

  useEffect(() => {
    const anchor = pendingScrollAnchorRef.current;
    if (
      anchor &&
      !listQuery.isFetchingNextPage &&
      items.length <= anchor.itemCount
    ) {
      pendingScrollAnchorRef.current = null;
    }
  }, [items.length, listQuery.isFetchingNextPage]);

  return (
    <GamePageShell
      id="panelsPortfolioPage"
      className="efhc-panels-shell efhc-panels-portfolio-shell"
      data-panels-layout="portfolio-page"
      data-panels-list-mode="segmented"
      data-panels-portfolio-route="/panels/portfolio"
      data-panels-scroll-boundary="shared-user-layout"
    >
      <h1 className="efhc-subpage-centered-title">{t("panels.my_panels")}</h1>
      <Card
        className="efhc-panels-list-card"
        data-panels-section="list"
        data-panels-tab={tab}
        data-pt={tabsSurface.variant}
        data-panel-countdown-source={countdownSource}
      >
        <div
          ref={tabsSurface.ref}
          {...tabsSurface.handlers}
          className="efhc-segmented efhc-panels-tabs mb-3"
          data-pt={tabsSurface.variant}
          data-panels-tabs="active-archive"
          data-panels-tabs-sticky="true"
        >
          <Button
            variant={tab === "active" ? "primary" : "secondary"}
            data-panels-tab-button="active"
            data-active={tab === "active" ? "true" : "false"}
            aria-label={t("panels.tab_active_aria")}
            onClick={() => {
              hapticSelection(settings.haptics_enabled);
              resetPageTrigger();
              const node = panelListViewportRef.current;
              if (node) node.scrollTop = 0;
              setTab("active");
            }}
          >
            {t("panels.tab_active")}
          </Button>
          <Button
            variant={tab === "archive" ? "primary" : "secondary"}
            data-panels-tab-button="archive"
            data-active={tab === "archive" ? "true" : "false"}
            aria-label={t("panels.tab_archive_aria")}
            onClick={() => {
              hapticSelection(settings.haptics_enabled);
              resetPageTrigger();
              const node = panelListViewportRef.current;
              if (node) node.scrollTop = 0;
              setTab("archive");
            }}
          >
            {t("panels.tab_archive")}
          </Button>
        </div>

        <div className="efhc-panels-hint-row mb-3">
          <div className="text-xs efhc-text-muted2">
            {tab === "active"
              ? t("panels.tab_hint_active")
              : t("panels.tab_hint_archive")}
          </div>
          <button
            type="button"
            className="efhc-panels-sort-direction"
            data-panels-sort-direction={sortDirection}
            aria-label={t(
              sortDirection === "oldest"
                ? "panels.sort_oldest_first"
                : "panels.sort_newest_first",
            )}
            title={t(
              sortDirection === "oldest"
                ? "panels.sort_oldest_first"
                : "panels.sort_newest_first",
            )}
            onClick={() => {
              hapticSelection(settings.haptics_enabled);
              resetPageTrigger();
              setSortDirection((current) =>
                current === "oldest" ? "newest" : "oldest",
              );
              const node = panelListViewportRef.current;
              if (node) node.scrollTop = 0;
            }}
          >
            <span aria-hidden="true">
              {sortDirection === "oldest" ? "↑" : "↓"}
            </span>
          </button>
        </div>

        <div
          ref={(node) => {
            cardsSurface.ref.current = node;
            panelListViewportRef.current = node;
          }}
          {...cardsSurface.handlers}
          className="efhc-compact-list-limit grid gap-2 efhc-panels-card-surface"
          data-pc={cardsSurface.variant}
          data-panels-list={tab}
          data-panels-scroll-mode="canonical-window"
          data-panels-batch-size="20"
          data-panels-order={
            sortDirection === "oldest" ? "oldest-first" : "newest-first"
          }
          onScroll={loadNextPanelsAtScrollEnd}
        >
          {orderedItems.map((p) => {
            const activatedIso = p.activated_at ?? p.created_at ?? null;
            const expiresIso = p.expires_at ?? p.archived_at ?? null;
            const expiresMs = expiresIso ? Date.parse(expiresIso) : null;
            const rem =
              tab === "active" &&
              p.is_active &&
              nowUtcMs !== null &&
              expiresMs !== null &&
              !Number.isNaN(expiresMs)
                ? (expiresMs - nowUtcMs) / 1_000
                : p.remaining_seconds ?? null;

            return (
              <div
                key={p.id}
                className="efhc-panel-tile"
                data-panel-identity={p.public_id ?? undefined}
                data-panel-card={tab}
                data-panel-countdown-contract="1282"
              >
                <div
                  className="efhc-panel-tile_head"
                  data-panel-card-field="panel-id"
                >
                  <div className="min-w-0">
                    <div className="truncate font-semibold tabular-nums">
                      {/^PNL-(?!00000000$)[0-9]{8}$/.test(p.public_id) ? p.public_id : "Ошибка целостности PNL"}
                    </div>
                    <div className="text-xs efhc-text-muted2">
                      {t("panels.panel_id")}
                    </div>
                  </div>
                  <span
                    className="efhc-panel-activ-status"
                    data-status="activ"
                    data-active={p.is_active ? "true" : "false"}
                    data-i18n-fixed-token="Activ"
                    aria-label={`Activ ${p.is_active ? "ON" : "OFF"}`}
                  >
                    Activ
                  </span>
                </div>

                <div
                  className="efhc-panel-tile_dates"
                  data-panel-card-field="date-range"
                >
                  <div data-panel-card-field="activated-at">
                    <div className="text-xs efhc-text-muted2">
                      {t("panels.activated_at")}
                    </div>
                    <div className="font-semibold tabular-nums">
                      {formatUtcMinute(activatedIso)}
                    </div>
                  </div>
                  <div data-panel-card-field="deactivated-at">
                    <div className="text-xs efhc-text-muted2">
                      {t("panels.deactivated_at")}
                    </div>
                    <div className="font-semibold tabular-nums">
                      {formatUtcMinute(expiresIso)}
                    </div>
                  </div>
                </div>

                <div
                  className="efhc-panel-tile_stats"
                  data-panel-card-contract="date-countdown"
                >
                  <div data-panel-card-field="generated-kwh">
                    <div className="text-xs efhc-text-muted2">
                      {t("panels.generated_kwh")}
                    </div>
                    <div className="font-semibold tabular-nums">
                      {projectPanelGeneratedD8(
                        { ...p, base_gen_per_sec: confirmedPerPanelRateD8 ?? (props.snap?.profile && !props.snap.profile.is_vip ? p.base_gen_per_sec : "0.00000000") },
                        serverNowIso, elapsedClientMs,
                      )}
                    </div>
                  </div>
                  <div
                    data-panel-card-field="remaining-countdown"
                    data-panel-countdown-live="client-stopwatch"
                    data-panel-countdown-tick={tick}
                    aria-live="polite"
                  >
                    <div className="text-xs efhc-text-muted2">
                      {t("panels.remaining")}
                    </div>
                    <div className="efhc-panel-countdown-live font-semibold tabular-nums">
                      {tab === "active" && p.is_active
                        ? formatRemaining(rem, t)
                        : formatRemaining(0, t)}
                    </div>
                  </div>
                </div>
              </div>
            );
          })}

          {loading && items.length === 0 ? (
            <div className="grid gap-2">
              <Skeleton className="h-24" />
              <Skeleton className="h-24" />
            </div>
          ) : null}

          {items.length === 0 && !loading ? (
            <EmptyState
              title={err ? t("common.error") : t("common.empty")}
              detail={
                err
                  ? t("panels.load_error")
                  : tab === "active"
                    ? t("panels.active_empty_detail")
                    : t("panels.archive_empty_detail")
              }
              actionLabel={t("common.refresh")}
              onAction={() => {
                hapticSelection(settings.haptics_enabled);
                void listQuery.refetch();
              }}
            />
          ) : null}

          <div className="mt-2 flex items-center gap-2">
            {loading && items.length > 0 ? (
              <span className="text-xs efhc-text-muted2">
                {t("common.loading")}
              </span>
            ) : !canLoadMore ? (
              <span className="text-xs efhc-text-muted2">
                {t("common.end")}
              </span>
            ) : null}
          </div>
        </div>
      </Card>
    </GamePageShell>
  );
}
