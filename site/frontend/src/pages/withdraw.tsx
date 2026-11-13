import React, { useContext, useEffect, useMemo, useRef, useState } from "react";
import {useOwnerDraft} from "../hooks/useOwnerDraft";
import { LayoutContext } from "../components/Layout";
import { Button } from "../components/ui/Button";
import { Modal } from "../components/ui/Modal";
import { Card } from "../components/ui/Card";
import { EmptyState } from "../components/ui/EmptyState";
import type { SyncSnapshot } from "../hooks/useSnapshot";
import { useWalletsMe } from "../hooks/useWalletsMe";
import { publicApiErrorMessage } from "../lib/publicError";
import { AdManager, adManagerErrorCode } from "../lib/ads/AdManager";
import { WITHDRAW_REQUIRED_AD_PLACEMENT_CODE } from "../lib/ads/systemPlacements";
import type { AdRunPhase } from "../lib/ads/types";
import { cmp8, format8, formatD8ToHuman } from "../lib/format";
import { newIdempotencyKey } from "../lib/idempotency";
import { hapticMedium, hapticSelection, onTelegramViewportChanged } from "../lib/telegram";
import { useAuthOwnerGlobalId } from "../auth/AuthSessionProvider";
import { useT } from "../hooks/useT";
import { useInterfaceVariantSurface } from "../hooks/useInterfaceVariantSurface";
import { GameHero, GamePageShell } from "../components/ui/GameShell";
import { withdrawStatusLabel } from "../lib/humanLabels";
import {
  useCancelWithdrawRequest,
  useCreateWithdrawRequest,
  useWithdrawalsPage,
} from "../queries/useWithdrawals";
import type { DbId } from "../types/db-id";
import { useProfileHistoryExport } from "../queries/useProfile";

// Guard marker: Latest withdraw outcome

function formatDate(value: string, locale: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString(locale);
}

function maskWallet(addr: string): string {
  if (addr.length < 14) return addr;
  return `${addr.slice(0, 6)}…${addr.slice(-6)}`;
}

function isValidD8(raw: string): boolean {
  const value = raw.trim();
  if (!value) return false;
  if (value.includes("e") || value.includes("E")) return false;
  if (value.includes("-")) return false;
  return /^\d+(\.\d{0,8})?$/.test(value);
}

export default function WithdrawPage(props: {
  snap: SyncSnapshot | null;
}) {
  const t = useT();
  const globalId = useAuthOwnerGlobalId();
  const mainBalance = format8(props.snap?.profile?.main_balance || "0");
  const mainBalanceHuman = formatD8ToHuman(mainBalance);
  const walletsMe = useWalletsMe();
  const { confirm, openWalletConnect, settings, toast, lang } =
    useContext(LayoutContext);
  const withdrawSurface = useInterfaceVariantSurface<HTMLDivElement>("WD", {
    dotsPlacement: "below",
  });
  const [amount, setAmount] = useOwnerDraft("withdraw.amount",mainBalance);
  const amountInputRef = useRef<HTMLInputElement | null>(null);
  const createSurfaceRef = useRef<HTMLDivElement | null>(null);
  const [statusFilter, setStatusFilter] = useState("all");
  const [amountTouched, setAmountTouched] = useState(false);
  const [withdrawAdOpen, setWithdrawAdOpen] = useState(false);
  const [withdrawAdBusy, setWithdrawAdBusy] = useState(false);
  const [withdrawAdPhase, setWithdrawAdPhase] = useState<AdRunPhase | null>(null);
  const historyExport = useProfileHistoryExport();
  const historyExporting = historyExport.isPending;
  const withdrawalsQ = useWithdrawalsPage({ statusFilter: "all" });
  const lastRefreshAtRef = useRef(Date.now());
  const withdrawalsRef = useRef(withdrawalsQ);
  withdrawalsRef.current = withdrawalsQ;
  const items = useMemo(
    () => (withdrawalsQ.data?.pages.flatMap((page) => page.items) || [])
      .filter((item) => statusFilter === "all" || item.status === statusFilter),
    [withdrawalsQ.data, statusFilter],
  );

  useEffect(() => {
    let frameOne = 0;
    let frameTwo = 0;

    const recoverFocusedAmount = () => {
      const input = amountInputRef.current;
      if (!input || document.activeElement !== input) return;

      if (frameOne) window.cancelAnimationFrame(frameOne);
      if (frameTwo) window.cancelAnimationFrame(frameTwo);

      frameOne = window.requestAnimationFrame(() => {
        frameTwo = window.requestAnimationFrame(() => {
          if (document.activeElement !== input) return;

          const main = input.closest<HTMLElement>(".efhc-game-shell_main");
          const action = createSurfaceRef.current?.querySelector<HTMLElement>(
            '[data-withdraw-action="create"]',
          );
          if (!main || !action) return;

          const mainRect = main.getBoundingClientRect();
          const nav = document.querySelector<HTMLElement>(".efhc-game-nav");
          const navTop = nav?.getBoundingClientRect().top ?? mainRect.bottom;
          const visibleTop = mainRect.top + 12;
          const visibleBottom = Math.min(mainRect.bottom, navTop) - 12;
          const inputRect = input.getBoundingClientRect();
          const actionRect = action.getBoundingClientRect();

          let delta = 0;
          if (actionRect.bottom > visibleBottom) {
            delta = actionRect.bottom - visibleBottom;
          }

          const inputTopAfterScroll = inputRect.top - delta;
          if (inputTopAfterScroll < visibleTop) {
            delta -= visibleTop - inputTopAfterScroll;
          }

          if (Math.abs(delta) > 0.5) {
            main.scrollTop += delta;
          }
        });
      });
    };

    const offTelegramViewport = onTelegramViewportChanged(recoverFocusedAmount);
    window.visualViewport?.addEventListener("resize", recoverFocusedAmount);

    return () => {
      offTelegramViewport();
      window.visualViewport?.removeEventListener("resize", recoverFocusedAmount);
      if (frameOne) window.cancelAnimationFrame(frameOne);
      if (frameTwo) window.cancelAnimationFrame(frameTwo);
    };
  }, []);
  useEffect(() => {
    const refreshOnActivity = (event: Event) => {
      if (!globalId || document.visibilityState === "hidden") return;
      if (event.type !== "visibilitychange") {
        const target = event.target;
        if (!(target instanceof Element) || !target.closest('[data-public-surface="withdraw"]')) return;
      }
      const request = withdrawalsRef.current;
      const now = Date.now();
      if (request.isFetching || now - Math.max(lastRefreshAtRef.current, request.dataUpdatedAt) < 10_000) return;
      lastRefreshAtRef.current = now;
      void request.refetch({ cancelRefetch: false });
    };
    document.addEventListener("pointerdown", refreshOnActivity, { passive: true });
    document.addEventListener("keydown", refreshOnActivity);
    document.addEventListener("visibilitychange", refreshOnActivity);
    return () => {
      document.removeEventListener("pointerdown", refreshOnActivity);
      document.removeEventListener("keydown", refreshOnActivity);
      document.removeEventListener("visibilitychange", refreshOnActivity);
    };
  }, [globalId]);

  const createWithdrawMutation = useCreateWithdrawRequest();
  const cancelWithdrawMutation = useCancelWithdrawRequest();
  const loading = withdrawalsQ.isLoading || withdrawalsQ.isFetching;
  const loadMoreError = withdrawalsQ.isFetchNextPageError && withdrawalsQ.error
    ? publicApiErrorMessage(withdrawalsQ.error, t)
    : null;
  const error = withdrawalsQ.error && !withdrawalsQ.isFetchNextPageError
    ? publicApiErrorMessage(withdrawalsQ.error, t)
    : createWithdrawMutation.error
      ? publicApiErrorMessage(createWithdrawMutation.error, t)
      : null;
  const cancelError = cancelWithdrawMutation.error
    ? publicApiErrorMessage(cancelWithdrawMutation.error, t)
    : null;
  const cursor = withdrawalsQ.hasNextPage
    ? withdrawalsQ.data?.pages.at(-1)?.next_cursor || null
    : null;
  const createBusy = createWithdrawMutation.isPending;
  const cancelBusyId = cancelWithdrawMutation.isPending
    ? cancelWithdrawMutation.variables?.requestId || null
    : null;


  const withdrawMinOk = useMemo(
    () => cmp8(mainBalance, "10.00000000") >= 0,
    [mainBalance],
  );
  const amountIssue = useMemo(() => {
    if (!amount.trim()) return "missing";
    if (!isValidD8(amount)) return "invalid";
    const value = format8(amount);
    if (cmp8(value, "10.00000000") < 0) return "minimum";
    if (cmp8(value, mainBalance) > 0) return "balance";
    return null;
  }, [amount, mainBalance]);
  const withdrawAmountOk = amountIssue === null;

  const activeWallets = useMemo(
    () => (walletsMe.data?.wallets || []).filter((wallet) => wallet.is_active),
    [walletsMe.data?.wallets],
  );
  const primaryWallet = useMemo(
    () => activeWallets.find((wallet) => wallet.is_primary) || null,
    [activeWallets],
  );

  const statusLabel = (status: string): string =>
    withdrawStatusLabel(status, t);

  const requestTitle = (id: DbId): string =>
    t("withdraw.request_number").replace("{id}", String(id));

  async function exportWithdrawRequests(format: "csv" | "xlsx") {
    if (historyExporting) return;
    try {
      await historyExport.mutateAsync({ format, category: "withdraw" });
      toast(t("history.export_success"), "success");
    } catch {
      toast(t("history.export_error"), "error");
    }
  }


  function withdrawAdPhaseLabel(): string {
    if (withdrawAdPhase === "loading") return t("tasks.ad_state_loading");
    if (withdrawAdPhase === "viewing") return t("tasks.ad_state_viewing");
    if (withdrawAdPhase === "verifying") return t("tasks.ad_state_verifying");
    if (withdrawAdPhase === "rewarded") return t("withdraw.ad_required_confirmed");
    if (withdrawAdPhase === "no_fill") return t("tasks.ad_no_fill");
    if (withdrawAdPhase === "daily_limit") return t("withdraw.ad_required_failed");
    if (withdrawAdPhase === "failed") return t("withdraw.ad_required_failed");
    return t("tasks.ad_state_loading");
  }

  async function runRequiredWithdrawAd(): Promise<boolean> {
    setWithdrawAdOpen(true);
    setWithdrawAdBusy(true);
    setWithdrawAdPhase("loading");
    try {
      const result = await AdManager.runRewardedAd({
        taskCode: WITHDRAW_REQUIRED_AD_PLACEMENT_CODE,
        appLanguage: lang,
        onPhase: (phase) => {
          setWithdrawAdPhase(phase);
          // The provider owns the actual ad window; do not cover its controls.
          setWithdrawAdOpen(phase !== "viewing");
        },
        requireZeroReward: true,
      });
      if (!result.session.rewarded) {
        setWithdrawAdPhase("failed");
        toast(t("withdraw.ad_required_failed"), "error");
        return false;
      }
      setWithdrawAdPhase("rewarded");
      setWithdrawAdOpen(false);
      return true;
    } catch (caught: unknown) {
      const code = adManagerErrorCode(caught);
      const text = code === "NO_FILL" || code === "NOT_CONFIGURED" || code === "DISABLED" || code === "NOT_SUPPORTED"
        ? t("withdraw.ad_required_unavailable")
        : code === "USER_SKIPPED"
          ? t("withdraw.ad_required_skipped")
          : t("withdraw.ad_required_failed");
      setWithdrawAdPhase(code === "NO_FILL" ? "no_fill" : code === "DAILY_LIMIT_REACHED" ? "daily_limit" : "failed");
      setWithdrawAdOpen(true);
      toast(text, "error");
      return false;
    } finally {
      setWithdrawAdBusy(false);
    }
  }

  async function createWithdraw() {
    if (!globalId) return;
    if (!primaryWallet) {
      openWalletConnect();
      return;
    }
    if (!withdrawAmountOk || !withdrawMinOk) return;
    const ok = await confirm(
      "withdraw",
      t("withdraw.confirm_create_title"),
      t("withdraw.confirm_create_detail"),
    );
    if (!ok) return;

    const adConfirmed = await runRequiredWithdrawAd();
    if (!adConfirmed) return;
    setWithdrawAdOpen(false);

    try {
      await createWithdrawMutation.mutateAsync({
        amount: format8(amount),
        walletId: primaryWallet.id,
        idempotencyKey: newIdempotencyKey(),
      });
      toast(t("withdraw.request_accepted"), "success");
    } catch {
      // The mutation error is rendered through the safe public error helper.
    }
  }

  async function cancelWithdraw(requestId: DbId) {
    const ok = await confirm(
      "withdraw",
      t("withdraw.confirm_cancel_title"),
      t("withdraw.confirm_cancel_detail"),
    );
    if (!ok) return;
    try {
      await cancelWithdrawMutation.mutateAsync({
        requestId,
        idempotencyKey: newIdempotencyKey(),
      });
      toast(t("withdraw.toast_canceled"), "success");
    } catch {
      // The mutation error is rendered through the safe public error helper.
    }
  }



  return (
    <GamePageShell
      ref={withdrawSurface.ref}
      {...withdrawSurface.handlers}
      className="efhc-withdraw-trust-shell efhc-withdraw-shell"
      data-wd={withdrawSurface.variant}
      data-public-visual-trust="hub-browser-shop-withdraw-ads"
      data-public-surface="withdraw"
      data-withdraw-runtime="react-query-create-cancel-history"
      data-withdraw-layout="exchange-family-v278"
      data-withdraw-stats-layout="exchange-list-v282"
    >
      <GameHero
        className="efhc-withdraw-hero"
        kicker={t("withdraw.standalone_kicker")}
        title={t("withdraw.title")}
        detail={t("withdraw.min_hint")}
      >
        <div className="efhc-withdraw-summary-list" data-withdraw-summary-layout="stacked-list-v282">
          <div className="efhc-withdraw-summary-row">
            <span className="efhc-withdraw-summary-label">{t("withdraw.available_to_withdraw")}</span>
            <strong className="efhc-withdraw-summary-value efhc-financial-number">{mainBalanceHuman} EFHCm</strong>
          </div>
          <div className="efhc-withdraw-summary-row">
            <span className="efhc-withdraw-summary-label">{t("wallet.primary_wallet")}</span>
            <strong className="efhc-withdraw-summary-value">
              {primaryWallet ? maskWallet(primaryWallet.wallet_address) : t("withdraw.not_connected")}
            </strong>
          </div>
        </div>
      </GameHero>

      <Card
        title={t("withdraw.new_request")}
        className="efhc-withdraw-create-card efhc-withdraw-action-card efhc-exchange-card-variant"
        data-withdraw-create-dialog="exchange-family-v278"
      >
        <div ref={createSurfaceRef} className="efhc-exchange-panel efhc-withdraw-create-card_body">
          <div className="efhc-exchange-action-surface">
          <div className="efhc-exchange-canonical-row">
            <div>
              <div className="text-xs efhc-text-muted2">
                {t("withdraw.available_to_withdraw")}
              </div>
              <div className="mt-1 font-semibold tabular-nums efhc-financial-number">
                {mainBalanceHuman} EFHCm
              </div>
            </div>
            <Button
              variant="secondary"
              className="efhc-withdraw-max-cta"
              onClick={() => {
                hapticMedium(settings.haptics_enabled);
                setAmount(mainBalance);
                 setAmountTouched(false);
              }}
              disabled={!withdrawMinOk}
            >
              {t("withdraw.max")}
            </Button>
          </div>

          <label className="efhc-exchange-input-group">
            <span className="text-xs efhc-text-muted2">
              {t("withdraw.efhc_amount")}
            </span>
            <input
              ref={amountInputRef}
              value={amount}
              onChange={(e) => { setAmount(e.target.value); setAmountTouched(true); }}
              className="efhc-input mt-2 w-full tabular-nums"
               data-amount-state={amountTouched && amountIssue ? "invalid" : "valid"}
              inputMode="decimal"
              aria-invalid={amountTouched && !withdrawAmountOk}
              aria-describedby={amountTouched && !withdrawAmountOk ? "efhc-withdraw-amount-helper" : undefined}
              data-withdraw-amount-input="efhcm-main-only"
            />
          </label>

          {!primaryWallet ? (
             <Button variant="secondary" className="w-full" onClick={() => openWalletConnect()}>
               {t("withdraw.connect_wallet")}
             </Button>
           ) : null}

          {amountTouched && amountIssue ? (
             <div
               id="efhc-withdraw-amount-helper"
               className="efhc-exchange-helper efhc-exchange-helper--warning"
               role="alert"
             >
               {amountIssue === "balance"
                 ? t("withdraw.amount_exceeds_balance")
                 : amountIssue === "minimum"
                   ? t("withdraw.min_hint")
                   : t("withdraw.amount_invalid_range")}
             </div>
           ) : null}
          {error ? <div className="text-sm text-red-600">{error}</div> : null}

          <Button
            className="mt-3 w-full"
            data-withdraw-action="create"
            data-withdraw-ad-gate="required-zero-reward"
            onClick={() => void createWithdraw()}
            disabled={
              createBusy ||
              withdrawAdBusy ||
              !primaryWallet ||
              !withdrawAmountOk ||
              !withdrawMinOk
            }
          >
            {createBusy || withdrawAdBusy ? t("withdraw.creating") : t("withdraw.create_request")}
          </Button>
          </div>
        </div>
      </Card>

      <Card title={t("withdraw.my_requests")} className="efhc-withdraw-requests-history">
        <div className="space-y-3">
          <div
            className="efhc-history-filter-row efhc-withdraw-request-filters"
            role="tablist"
            aria-label={t("withdraw.filter_label")}
          >
            {[
              ["all", t("withdraw.filter_all")],
              ["PENDING", t("withdraw.status_pending")],
              ["PAID", t("withdraw.status_paid")],
              ["CANCELED", t("withdraw.status_canceled")],
              ["REJECTED", t("withdraw.status_rejected")],
            ].map(([value, label]) => (
              <button
                key={value}
                type="button"
                role="tab"
                aria-selected={statusFilter === value}
                className={`efhc-history-filter ${statusFilter === value ? "efhc-history-filter--active" : ""}`}
                onClick={() => setStatusFilter(value)}
              >
                {label}
              </button>
            ))}
          </div>

          {cancelError ? <div className="text-sm text-red-600">{cancelError}</div> : null}
          {loading && items.length === 0 ? (
            <EmptyState title={t("withdraw.loading_requests")} />
          ) : null}
          {!loading && items.length === 0 ? (
            <EmptyState title={t("withdraw.no_requests_yet")} />
          ) : null}

          <div className="efhc-history-bank-feed" data-withdraw-requests-layout="history-style">
            <div className="efhc-history-bank-operation-list" role="list">
              {items.map((item) => {
                const status = statusLabel(item.status);
                const statusKind = item.status === "PAID"
                  ? "done"
                  : item.status === "PENDING"
                    ? "pending"
                    : "failed";
                return (
                  <details
                    key={item.id}
                    className="efhc-history-bank-operation efhc-withdraw-request-history-item"
                    data-status-kind={statusKind}
                    data-withdraw-request-id={String(item.id)}
                  >
                    <summary className="efhc-history-bank-operation-summary">
                      <span className="efhc-history-bank-operation-icon" aria-hidden="true">−</span>
                      <span className="efhc-history-bank-operation-copy">
                        <strong>{requestTitle(item.id)}</strong>
                        <time dateTime={item.created_at}>{formatDate(item.created_at, lang)}</time>
                        <span>{status}</span>
                      </span>
                      <span className="efhc-history-bank-operation-value">
                        <strong className="efhc-financial-number">−{item.amount}</strong>
                        <small>EFHCm</small>
                        <em data-status-kind={statusKind}>{status}</em>
                      </span>
                    </summary>
                    <div className="efhc-history-bank-operation-details">
                      <div className="efhc-history-bank-operation-details-title">
                        {t("history.details_title")}
                      </div>
                      <div className="efhc-history-bank-operation-detail">
                        <span>{t("withdraw.created_at")}</span>
                        <strong>{formatDate(item.created_at, lang)}</strong>
                      </div>
                      <div className="efhc-history-bank-operation-detail">
                        <span>{t("withdraw.updated_at")}</span>
                        <strong>{formatDate(item.updated_at, lang)}</strong>
                      </div>
                      {item.status === "PENDING" ? (
                        <div className="efhc-withdraw-request-inline-action">
                          <Button
                            variant="secondary"
                            disabled={cancelBusyId === item.id}
                            data-withdraw-action="cancel"
                            data-withdraw-cancel-id={item.id}
                            onClick={() => void cancelWithdraw(item.id)}
                          >
                            {cancelBusyId === item.id
                              ? t("withdraw.canceling")
                              : t("withdraw.cancel_request")}
                          </Button>
                        </div>
                      ) : null}
                    </div>
                  </details>
                );
              })}
            </div>
          </div>

          {loadMoreError ? (
            <div
              className="text-sm text-red-600"
              role="alert"
              data-withdraw-load-more-error="true"
            >
              {loadMoreError}
            </div>
          ) : null}

          <div className="efhc-withdraw-requests-actions">
            {cursor ? (
              <Button
                variant="secondary"
                disabled={withdrawalsQ.isFetchingNextPage}
                aria-busy={withdrawalsQ.isFetchingNextPage}
                onClick={() => void withdrawalsQ.fetchNextPage()}
              >
                {withdrawalsQ.isFetchingNextPage
                  ? t("common.loading")
                  : t("common.load_more")}
              </Button>
            ) : null}
</div>
        </div>
      </Card>

      <Modal
        open={withdrawAdOpen}
        surface="withdraw-ad"
        onClose={() => { if (!withdrawAdBusy) setWithdrawAdOpen(false); }}
        closeDisabled={withdrawAdBusy}
        title={t("tasks.ad_modal_title")}
      >
        <div className="efhc-withdraw-ad-status" data-withdraw-required-ad-modal="ads-module-zero-reward" data-ad-phase={withdrawAdPhase || "loading"}>
          <span className="efhc-withdraw-ad-status-icon" aria-hidden="true">
            {withdrawAdBusy ? "…" : withdrawAdPhase === "rewarded" ? "✓" : "!"}
          </span>
          <p className="efhc-withdraw-ad-status-message" role="status">{withdrawAdPhaseLabel()}</p>
          <Button
            className="w-full"
            disabled={withdrawAdBusy}
            onClick={() => setWithdrawAdOpen(false)}
          >
            {t("common.close")}
          </Button>
        </div>
      </Modal>

      <div className="efhc-withdraw-history-export" data-withdraw-history-export="withdraw-requests-csv-xlsx">
        <div className="efhc-withdraw-history-export-actions">
          <Button
            variant="secondary"
            disabled={historyExporting}
            data-history-export="csv-server-side"
            onClick={() => void exportWithdrawRequests("csv")}
          >
            {historyExporting ? t("history.exporting") : t("history.export_csv")}
          </Button>
          <Button
            variant="secondary"
            disabled={historyExporting}
            data-history-export="xlsx-server-side"
            onClick={() => void exportWithdrawRequests("xlsx")}
          >
            {t("history.export_xlsx")}
          </Button>
        </div>
      </div>
    </GamePageShell>
  );
}
