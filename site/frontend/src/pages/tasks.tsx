import React, { useContext, useMemo, useState } from "react";

import { useAuthOwnerGlobalId } from "../auth/AuthSessionProvider";
import { LayoutContext } from "../components/Layout";
import { Badge } from "../components/ui/Badge";
import { BonusEarningsStrip } from "../components/ui/BonusEarningsStrip";
import { Button } from "../components/ui/Button";
import { EmptyState } from "../components/ui/EmptyState";
import { GameHero, GameNotice, GamePageShell } from "../components/ui/GameShell";
import { Modal } from "../components/ui/Modal";
import { Skeleton } from "../components/ui/Skeleton";
import { useInterfaceCustomization } from "../hooks/useInterfaceCustomization";
import { useInterfaceVariantSurface } from "../hooks/useInterfaceVariantSurface";
import { useT } from "../hooks/useT";
import type { SyncSnapshot } from "../hooks/useSnapshot";
import { AdManager, adManagerErrorCode } from "../lib/ads/AdManager";
import { isSystemAdPlacementCode } from "../lib/ads/systemPlacements";
import type { AdRunPhase } from "../lib/ads/types";
import { formatD8ToHuman } from "../lib/format";
import { taskTemplateByKind, taskTemplateForRecord, taskTemplateTarget } from "../lib/tasks/templates";
import { newIdempotencyKey } from "../lib/idempotency";
import { publicApiErrorMessage } from "../lib/publicError";
import {
  hapticError,
  hapticMedium,
  hapticSelection,
  hapticSuccess,
  openTelegramLink,
} from "../lib/telegram";
import {
  useClaimTask,
  useMyTasks,
  useRefreshTaskState,
  useTaskEarnings,
  useTasksCatalog,
} from "../queries/useTasks";
import type { MyTaskItem, TaskCatalogItem } from "../services/tasks.service";

const READY_AD_STATUSES = new Set(["available", "not_started", "ready"]);

function isAdTask(item: TaskCatalogItem): boolean {
  return item.kind === "ads" || item.kind === "watch_ad";
}

function isCompletedStatus(status: string | null | undefined): boolean {
  return ["completed", "claimed", "approved", "auto_paid"].includes(String(status || "").toLowerCase());
}


export default function TasksPage(props: { snap: SyncSnapshot | null }) {
  const t = useT();
  const globalId = useAuthOwnerGlobalId();
  const ctx = useContext(LayoutContext);
  const customization = useInterfaceCustomization();
  const tasksSurface = useInterfaceVariantSurface<HTMLDivElement>("TG", { dotsPlacement: "below" });
  const { lang } = ctx;

  const [busyCode, setBusyCode] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [adOpen, setAdOpen] = useState(false);
  const [adTaskCode, setAdTaskCode] = useState<string | null>(null);
  const [adPhase, setAdPhase] = useState<AdRunPhase | null>(null);
  const [dailyLimitedCodes, setDailyLimitedCodes] = useState<Set<string>>(() => new Set());
  const catalogQuery = useTasksCatalog();
  const myTasksQuery = useMyTasks();
  const earningsQuery = useTaskEarnings();
  const claimMutation = useClaimTask();
  const refreshTaskState = useRefreshTaskState();

  const catalog = catalogQuery.data || [];
  const statesByTaskId = useMemo(
    () => new Map((myTasksQuery.data || []).map((item) => [item.task_id, item])),
    [myTasksQuery.data],
  );
  const loading = catalogQuery.isFetching || (Boolean(globalId) && myTasksQuery.isFetching);
  const hasError = Boolean(catalogQuery.error || (globalId && myTasksQuery.error));
  const templateOf = (item: TaskCatalogItem) =>
    taskTemplateForRecord(item.kind, item.meta || null) || taskTemplateByKind(item.kind);

  const titleOf = (item: TaskCatalogItem): string => {
    const template = templateOf(item);
    return template ? t(template.titleKey) : item.title;
  };

  const targetOf = (item: TaskCatalogItem): string => {
    const template = templateOf(item);
    return template ? taskTemplateTarget(item.meta || null).trim() : "";
  };

  const normalizedStatus = (state: MyTaskItem | undefined, item: TaskCatalogItem): string => {
    if (dailyLimitedCodes.has(item.code)) return "daily_limit";
    if (!globalId) return "unavailable";
    if (state?.status) return state.status;
    return isAdTask(item) ? "available" : "not_started";
  };

  const canUse = (item: TaskCatalogItem, state: MyTaskItem | undefined): boolean => {
    if (!globalId || customization.mutationBlocked) return false;
    if (dailyLimitedCodes.has(item.code)) return false;
    if (isAdTask(item)) return READY_AD_STATUSES.has(String(state?.status || "not_started"));
    // The target URL is owner-visible only through the Execute button. Opening a
    // target never fakes completion: reward claim still requires backend can_claim.
    return Boolean(state?.can_claim || targetOf(item));
  };


  const buttonLabel = (item: TaskCatalogItem): string => {
    if (busyCode === item.code) return t("common.loading");
    return t("tasks.action_execute");
  };


  const claim = async (item: TaskCatalogItem): Promise<void> => {
    if (!globalId || customization.mutationBlocked) return;
    hapticMedium(ctx.settings.haptics_enabled);
    setBusyCode(item.code);
    setMessage(null);
    try {
      await claimMutation.mutateAsync({ taskId: item.id, idempotencyKey: newIdempotencyKey() });
      const text = t("tasks.claim_ok");
      hapticSuccess(ctx.settings.haptics_enabled);
      setMessage(text);
      ctx.toast(text, "success");
    } catch (error: unknown) {
      const text = publicApiErrorMessage(error, t);
      hapticError(ctx.settings.haptics_enabled);
      setMessage(text);
    } finally {
      setBusyCode(null);
    }
  };

  const executeTask = async (item: TaskCatalogItem, state: MyTaskItem | undefined): Promise<void> => {
    if (isAdTask(item)) {
      await watchAd(item);
      return;
    }
    if (state?.can_claim) {
      await claim(item);
      return;
    }
    const target = targetOf(item);
    if (!target) return;
    hapticMedium(ctx.settings.haptics_enabled);
    openTelegramLink(target);
  };

  const watchAd = async (item: TaskCatalogItem): Promise<void> => {
    if (!globalId || customization.mutationBlocked) return;
    setAdTaskCode(item.code);
    setAdOpen(true);
    setMessage(null);
    setAdPhase("loading");
    hapticMedium(ctx.settings.haptics_enabled);
    setBusyCode(item.code);
    try {
      const result = await AdManager.runRewardedAd({ taskCode: item.code, appLanguage: lang, onPhase: setAdPhase });
      if (result.session.rewarded) {
        setDailyLimitedCodes((current) => {
          const next = new Set(current);
          next.delete(item.code);
          return next;
        });
        await refreshTaskState();
        const bonus = formatD8ToHuman(result.rewardEfhcb);
        const text = t("tasks.ad_bonus_ok").replace("{{bonus}}", bonus);
        hapticSuccess(ctx.settings.haptics_enabled);
        setMessage(text);
        ctx.toast(text, "success");
      } else {
        const text = t("tasks.ad_verification_pending");
        setMessage(text);
        ctx.toast(text, "info");
      }
    } catch (error: unknown) {
      const code = adManagerErrorCode(error);
      if (code === "DAILY_LIMIT_REACHED") {
        setDailyLimitedCodes((current) => new Set(current).add(item.code));
        await refreshTaskState();
      }
      const key = code === "NO_FILL"
        ? "tasks.ad_no_fill"
        : code === "DAILY_LIMIT_REACHED"
          ? "tasks.ad_daily_limit"
          : code === "USER_SKIPPED"
            ? "tasks.ad_skipped"
            : "tasks.ad_failed";
      const text = t(key);
      hapticError(ctx.settings.haptics_enabled);
      setMessage(text);
      ctx.toast(text, "error");
    } finally {
      setBusyCode(null);
    }
  };

  const adPhaseLabel = (): string => {
    if (adPhase === "loading") return t("tasks.ad_state_loading");
    if (adPhase === "viewing") return t("tasks.ad_state_viewing");
    if (adPhase === "verifying") return t("tasks.ad_state_verifying");
    if (adPhase === "rewarded") return t("tasks.ad_state_rewarded");
    if (adPhase === "no_fill") return t("tasks.ad_no_fill");
    if (adPhase === "daily_limit") return t("tasks.come_tomorrow");
    if (adPhase === "failed") return t("tasks.ad_failed");
    return t("tasks.ad_state_loading");
  };

  const visibleCatalog = catalog.filter((item) => {
    if (isSystemAdPlacementCode(item.code)) return false;
    if (isAdTask(item)) return true;
    const state = statesByTaskId.get(item.id);
    return Boolean(state?.can_claim) || !isCompletedStatus(state?.status);
  });

  const refresh = (): void => {
    hapticSelection(ctx.settings.haptics_enabled);
    void catalogQuery.refetch();
    void myTasksQuery.refetch();
    void earningsQuery.refetch();
  };

  return (
    <GamePageShell
      className="efhc-tasks-shell"
      ref={tasksSurface.ref}
      data-tg={tasksSurface.variant}
      {...tasksSurface.handlers}
      data-public-surface="tasks"
      data-tasks-runtime="templates-v162"
      data-tasks-page-runtime="react-server-data"
      data-tg-selection={tasksSurface.selection}
      data-tasks-public-history="forbidden"
      data-eam-family="EAM-TASKS-001"
    >
      <GameHero kicker={t("tasks.standalone_kicker")} title={t("tasks.title")} detail={t("tasks.standalone_detail")}>
        <BonusEarningsStrip
          earnedLabel={t("common.earned_all_time")}
          earnedValue={formatD8ToHuman(earningsQuery.data?.total_bonus_earned ?? "0")}
          remainingLabel={t("common.bonus_remaining")}
          remainingValue={formatD8ToHuman(props.snap?.profile?.bonus_balance ?? "0")}
          asset={earningsQuery.data?.bonus_asset ?? "EFHCb"}
          loading={earningsQuery.isLoading}
        />
      </GameHero>

      {message ? <GameNotice title={t("common.status")} detail={message} /> : null}
      {hasError && !loading ? (
        <EmptyState title={t("tasks.error_title")} detail={t("tasks.empty_detail")} actionLabel={t("common.refresh")} onAction={refresh} />
      ) : null}

      <div className="efhc-tasks-grid efhc-compact-list-limit" data-tasks-list-card-layout="compact">
        {loading && !visibleCatalog.length ? (
          <div className="grid gap-2"><Skeleton className="h-24" /><Skeleton className="h-24" /><Skeleton className="h-24" /></div>
        ) : !visibleCatalog.length ? (
          <EmptyState title={t("tasks.empty_title")} detail={t("tasks.empty_detail")} actionLabel={t("common.refresh")} onAction={refresh} />
        ) : visibleCatalog.map((item) => {
          const state = statesByTaskId.get(item.id);
          const status = normalizedStatus(state, item);
          const enabled = canUse(item, state);
          const adTask = isAdTask(item);
          return (
            <article
              key={item.code}
              className={`efhc-task-card ${enabled ? "is-ready" : "is-locked"} ${adTask ? "is-ad" : "is-claim"}`}
              data-task-card="earning"
              data-task-code={item.code}
              data-task-status={status}
            >
              <div className="efhc-task-card_top">
                <div className="efhc-task-card_text">
                  <h2 className="efhc-task-card_title">{titleOf(item)}</h2>
                </div>
                <div className="efhc-task-card_reward" data-task-reward="bonus-efhcb">
                  <span className="efhc-task-card_reward-asset">EFHCb</span>
                  <Badge><span className="efhc-task-reward-value">{formatD8ToHuman(item.bonus_efhc)}</span></Badge>
                </div>
              </div>
              <div className="efhc-task-card_bottom" data-task-action-row="primary">
                <Button
                  disabled={!enabled || busyCode === item.code}
                  aria-label={buttonLabel(item)}
                  data-task-action={adTask ? "watch-ad" : "claim-bonus"}
                  onClick={() => void executeTask(item, state)}
                >
                  {buttonLabel(item)}
                </Button>
              </div>
            </article>
          );
        })}
      </div>

      <Modal
        open={adOpen}
        onClose={() => { if (busyCode === adTaskCode) return; setAdOpen(false); }}
        closeDisabled={busyCode === adTaskCode}
        title={t("tasks.ad_modal_title")}
      >
        <div className="efhc-ad-countdown" data-ad-countdown="state">
          {adPhaseLabel()}
        </div>
        <div className="mt-4">
          <Button disabled={busyCode === adTaskCode} onClick={() => setAdOpen(false)} className="w-full">{t("common.close")}</Button>
        </div>
      </Modal>
    </GamePageShell>
  );
}
