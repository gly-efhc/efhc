import React, { useMemo, useRef, useState } from "react";

import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { EmptyState } from "../components/ui/EmptyState";
import {
  GameHero,
  GamePageShell,
  GameStat,
  GameStatsGrid,
} from "../components/ui/GameShell";
import { Skeleton } from "../components/ui/Skeleton";
import { useT } from "../hooks/useT";
import { useInterfaceVariantSurface } from "../hooks/useInterfaceVariantSurface";
import { rankStyleId } from "../lib/interfaceVariantRegistry";
import type { SyncSnapshot } from "../hooks/useSnapshot";
import { format8 } from "../lib/format";
import { publicApiErrorMessage } from "../lib/publicError";
import { hapticSelection, hapticSoft } from "../lib/telegram";
import {
  useMyRankWithTop,
  useRankContext,
  useRankTopPages,
  useRefreshRanks,
} from "../queries/useRanks";
import { type RankItem } from "../services/ranks.service";

function medalForRank(pos: number): string {
  if (pos === 1) return "1";
  if (pos === 2) return "2";
  if (pos === 3) return "3";
  return String(pos);
}

function displayName(item: RankItem, hiddenLabel: string): string {
  return item.username ? `@${item.username}` : hiddenLabel;
}

function rankIdentity(item: RankItem): string {
  return item.global_id;
}

function rankMetric(item: RankItem): string {
  return `${format8(item.total_generated_kwh)} kWh`;
}

function RankRow(props: {
  item: RankItem;
  hiddenLabel: string;
  mine: boolean;
}) {
  return (
    <article
      className={
        `efhc-rank-card ${props.mine ? "efhc-rank-card--mine" : ""}`
      }
      data-ranks-card="compact-row-32"
      data-ranks-username-only="true"
      data-ranks-me={props.mine ? "true" : "false"}
      data-ranks-identity="global_id"
    >
      <div
        className="efhc-rank-position"
        aria-label={`#${props.item.rank_pos}`}
      >
        {medalForRank(props.item.rank_pos)}
      </div>
      <div className="efhc-rank-username">
        {displayName(props.item, props.hiddenLabel)}
      </div>
      <div className="efhc-rank-generated">
        {rankMetric(props.item)}
      </div>
    </article>
  );
}

export default function RanksPage(props: {
  global_id?: string | null;
  snap: SyncSnapshot | null;
}) {
  const ranksSurface = useInterfaceVariantSurface<HTMLDivElement>(
    "KG",
    { dotsPlacement: "above" },
  );
  const t = useT();
  const rankContextQ = useRankContext();
  const globalId = props.snap?.profile?.global_id ?? props.global_id ?? null;
  const myCardRef = useRef<HTMLDivElement | null>(null);
  const focusedRankRef = useRef<HTMLDivElement | null>(null);
  const [focusMode, setFocusMode] = useState(false);
  const [focusedContext, setFocusedContext] = useState<RankItem[]>([]);
  const [findingMe, setFindingMe] = useState(false);
  const rankQ = useMyRankWithTop(globalId);
  const moreQ = useRankTopPages(
    globalId,
    rankQ.data?.next_cursor,
  );
  const refreshRanks = useRefreshRanks(globalId);

  const fallbackMe: RankItem = {
    global_id: globalId ?? "",
    username: null,
    total_generated_kwh:
      props.snap?.profile?.total_generated_kwh || "0.00000000",
    rank_pos: 0,
    is_vip: Boolean(props.snap?.profile?.is_vip),
  };
  const me = rankQ.data?.me ?? fallbackMe;
  const hiddenLabel = globalId
    ? t("ranks.user_hidden_fallback")
    : t("ranks.browser_user_fallback");

  const rankRows = useMemo(() => {
    const initial = rankQ.data?.top ?? [];
    const additional = (moreQ.data?.pages ?? []).flatMap(
      (page) => page.items,
    );
    const meIdentity = rankIdentity(me);
    return [...initial, ...additional]
      .filter((item) => rankIdentity(item) !== meIdentity)
      .filter(
        (item, index, rows) =>
          rows.findIndex(
            (row) => rankIdentity(row) === rankIdentity(item),
          ) === index,
      )
      .sort((a, b) => a.rank_pos - b.rank_pos);
  }, [me, moreQ.data?.pages, rankQ.data?.top]);

  const leaderboard = rankRows;

  const focusedRows = useMemo(() => {
    if (!focusMode || me.rank_pos <= 0) return [];
    return [...focusedContext, me]
      .filter(
        (item, index, rows) =>
          rows.findIndex(
            (row) => rankIdentity(row) === rankIdentity(item),
          ) === index,
      )
      .sort((a, b) => a.rank_pos - b.rank_pos);
  }, [focusMode, focusedContext, me]);

  const refresh = async () => {
    hapticSelection(true);
    await refreshRanks();
    hapticSoft(true);
  };

  const findMe = async () => {
    hapticSelection(true);
    if (me.rank_pos <= 0) {
      myCardRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }
    setFindingMe(true);
    try {
      const context = await rankContextQ.mutateAsync();
      setFocusedContext(context.items);
      setFocusMode(true);
      requestAnimationFrame(() => {
        focusedRankRef.current?.scrollIntoView({
          behavior: "smooth",
          block: "center",
        });
      });
    } finally {
      setFindingMe(false);
      hapticSoft(true);
    }
  };

  const myMetric = `${format8(me.total_generated_kwh)} kWh`;
  const myMetricLabel = t("ranks.my_energy");

  return (
    <GamePageShell
      className="efhc-ranks-shell"
      ref={ranksSurface.ref}
      data-kg={rankStyleId(ranksSurface.selection)}
      {...ranksSurface.handlers}
      data-public-visual-beauty="tasks-referrals-ranks"
      data-public-surface="ranks"
      data-ranks-proof-pass="v049"
      data-ranks-runtime="react-query-current-energy"
      data-ranks-score="total_generated_kwh"
      data-ranks-tie-policy="dense-rank-global-id"
      data-ranks-referral-leaderboard="removed"
    >
      <GameHero
        data-ranks-hero-summary="responsive-ranks-summary"
        title={t("ranks.title")}
        right={
          <Button
            aria-label={t("common.refresh")}
            variant="secondary"
            data-ranks-refresh-action="shared-secondary"
            disabled={rankQ.isFetching}
            onClick={() => void refresh()}
          >
            {t("common.refresh")}
          </Button>
        }
      >
        <GameStatsGrid>
          <GameStat
            label={t("ranks.me")}
            value={me.rank_pos > 0 ? `#${me.rank_pos}` : "—"}
          />
          <GameStat
            label={myMetricLabel}
            value={<span data-ranks-hero-energy-d8="true">{myMetric}</span>}
          />
        </GameStatsGrid>
      </GameHero>

      <div ref={myCardRef}>
        <Card
          title={t("ranks.me")}
          className="efhc-ranks-me-card"
          data-ranks-my-card="true"
          data-ranks-show-me-boundary="v049"
        >
          {(
            <RankRow
              item={me}
              hiddenLabel={hiddenLabel}
              mine
            />
          )}
        </Card>
      </div>

      {rankQ.isError ? (
        <EmptyState
          intent="error"
          title={t("common.error")}
          detail={publicApiErrorMessage(rankQ.error, t)}
          actionLabel={t("common.refresh")}
          onAction={() => void refresh()}
        />
      ) : null}

      {focusMode ? (
        <div ref={focusedRankRef} data-ranks-focused-context="me-neighbors">
          <Card
            title={t("ranks.find_me")}
            className="grid gap-1 efhc-ranks-focused-card"
          >
            {focusedRows.map((item) => (
              <RankRow
                key={`focus-${item.rank_pos}-${rankIdentity(item)}`}
                item={item}
                hiddenLabel={hiddenLabel}
                mine={rankIdentity(item) === rankIdentity(me)}
              />
            ))}
          </Card>
        </div>
      ) : null}

      <Card
        title={t("ranks.top")}
        className="grid gap-3"
        data-ranks-leaderboard="paged-full"
      >
        <div className="flex items-center justify-end gap-3">
          <Button
            aria-label={t("ranks.find_me")}
            variant="secondary"
            data-ranks-show-me-action="load-and-focus-neighbors"
            data-ranks-active={focusMode ? "true" : "false"}
            disabled={findingMe}
            onClick={() => void findMe()}
          >
            {findingMe ? t("common.loading") : t("ranks.find_me")}
          </Button>
        </div>

        {rankQ.isLoading ? (
          <div className="grid gap-2">
            <Skeleton className="h-8" />
            <Skeleton className="h-8" />
            <Skeleton className="h-8" />
          </div>
        ) : null}

        <div className="grid gap-1" data-ranks-card-layout="compact-row-32">
          {leaderboard.map((item) => (
            <RankRow
              key={`${rankIdentity(item)}-${item.rank_pos}`}
              item={item}
              hiddenLabel={hiddenLabel}
              mine={false}
            />
          ))}
        </div>

        {!rankQ.isLoading && !rankQ.isError && leaderboard.length === 0 ? (
          <EmptyState
            title={t("ranks.leaderboard_empty")}
            detail={t("ranks.empty_detail")}
            actionLabel={t("common.refresh")}
            onAction={() => void refresh()}
          />
        ) : null}

        {moreQ.hasNextPage ? (
          <Button
            data-ranks-load-more="true"
            disabled={moreQ.isFetchingNextPage}
            onClick={() => {
              hapticSelection(true);
              void moreQ.fetchNextPage();
            }}
          >
            {moreQ.isFetchingNextPage
              ? t("common.loading")
              : t("common.load_more")}
          </Button>
        ) : null}
      </Card>
    </GamePageShell>
  );
}
