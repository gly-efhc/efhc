import { publicRuntimeValue } from "../lib/public-runtime";
import type { TonConnectTx } from "../lib/ton/tx";
import { createDirectDepositReview, type DirectDepositReview } from "../lib/ton/direct-deposit-review";
import React, { useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { useAuthOwnerGlobalId } from "../auth/AuthSessionProvider";
import { useT } from "../hooks/useT";
import { useWalletsMe } from "../hooks/useWalletsMe";
import {
  useWalletProvider,
  type WalletTransactionPhase,
} from "../lib/wallet-provider";
import {
  primaryLinkedWallet,
  routePrimaryWalletExecution,
  sameTonAddress,
  type PrimaryWalletExecutionReason,
} from "../lib/wallet-provider/primaryWalletRouting";
import { queryKeys } from "../queries/queryKeys";
import {
  useDirectDepositOpen,
  useDirectDepositStatus,
} from "../queries/useDirectDeposit";
import { LayoutContext } from "./Layout";
import { InterfaceCustomizationContext } from "./interface-settings/InterfaceCustomizationProvider";
import { Button } from "./ui/Button";
import { Modal } from "./ui/Modal";
import { TelegramEmptyState } from "./ui/telegram/TelegramEmptyState";

function normalizedEfhcAmount(value: string): string | null {
  const normalized = value.trim().replace(",", ".");
  if (!/^\d+(?:\.\d{0,8})?$/.test(normalized) || !/[1-9]/.test(normalized)) return null;
  const [wholeRaw, fractionRaw = ""] = normalized.split(".");
  const whole = wholeRaw.replace(/^0+(?=\d)/, "") || "0";
  const fraction = fractionRaw.replace(/0+$/, "");
  return fraction ? `${whole}.${fraction}` : whole;
}

function validEfhcAmount(value: string): boolean {
  return normalizedEfhcAmount(value) !== null;
}

// Only show finite, non-sensitive failure codes. Wallet/private RPC error
// objects may contain URLs, tokens, addresses or signed payloads.
const DIRECT_DEPOSIT_FAILURE_CODES = new Set([
  "JETTON_WALLET_LOOKUP_UNAVAILABLE",
  "EFHC_JETTON_BALANCE_NOT_FOUND",
  "EFHC_JETTON_MASTER_UNVERIFIED",
  "EFHC_JETTON_MASTER_MISMATCH",
  "EFHC_JETTON_WALLET_INVALID",
  "TON_MAINNET_RPC_REQUIRED",
  "TON_MAINNET_TRANSACTION_REQUIRED",
  "TON_MAINNET_WALLET_REQUIRED",
  "TONCONNECT_TRANSACTION_RESPONSE_INVALID",
  "DIRECT_DEPOSIT_REVIEW_INVALID",
  "INVALID_TON_ATTACHMENT",
]);

function directDepositFailureCode(error: unknown): string | null {
  const message = error instanceof Error ? error.message : "";
  if (DIRECT_DEPOSIT_FAILURE_CODES.has(message)) return message;
  if (/failed to fetch|networkerror|load failed/i.test(message)) {
    return "NETWORK_UNAVAILABLE";
  }
  return null;
}

type PreparedDirectDeposit = {
  tx: TonConnectTx;
  senderAddress: string;
  ownerGlobalId: string;
  amount: string;
  review: DirectDepositReview;
};

export function DepositModal(props: {
  open: boolean;
  onClose: () => void;
}) {
  const t = useT();
  const globalId = useAuthOwnerGlobalId();
  const queryClient = useQueryClient();
  const { openWalletConnect } = useContext(LayoutContext);
  const { colorThemeId } = useContext(InterfaceCustomizationContext);
  const {
    address: walletAddress,
    listWallets,
    connect: connectWallet,
    disconnect: disconnectWallet,
    sendTransaction,
    isUserRejected,
  } = useWalletProvider();
  const walletsMe = useWalletsMe();
  const [amount, setAmount] = useState("100");
  const [openedAt, setOpenedAt] = useState<string | null>(null);
  const [walletOpened, setWalletOpened] = useState(false);
  const [preparing, setPreparing] = useState(false);
  const [preparedDeposit, setPreparedDeposit] = useState<PreparedDirectDeposit | null>(null);
  const preparationRevision = useRef(0);
  const sendInProgress = useRef(false);
  const [resumeAfterPrimaryConnect, setResumeAfterPrimaryConnect] = useState(false);
  const [pendingInitialSessionAddress, setPendingInitialSessionAddress] = useState("");
  const [pendingSawDisconnect, setPendingSawDisconnect] = useState(false);
  const [transactionPhase, setTransactionPhase] = useState<
    WalletTransactionPhase
  >("idle");
  const [error, setError] = useState<string | null>(null);
  const openDeposit = useDirectDepositOpen();
  const openDepositMetadata = openDeposit.mutateAsync;
  const statusQ = useDirectDepositStatus(openedAt);

  const amountValid = useMemo(() => validEfhcAmount(amount), [amount]);
  const creditAmount = useMemo(() => normalizedEfhcAmount(amount), [amount]);
  const primaryWallet = useMemo(
    () => primaryLinkedWallet(walletsMe.data?.wallets),
    [walletsMe.data?.wallets],
  );
  const primarySessionReady = Boolean(
    primaryWallet
    && sameTonAddress(walletAddress, primaryWallet.wallet_address),
  );
  const confirmed = statusQ.data?.state === "confirmed";

  useEffect(() => {
    if (!confirmed) return;
    void Promise.all([
      queryClient.invalidateQueries({
        queryKey: queryKeys.snapshot.current(globalId),
      }),
      queryClient.invalidateQueries({
        queryKey: queryKeys.profile.balanceHistory(globalId),
      }),
    ]);
  }, [confirmed, globalId, queryClient]);

  useEffect(() => {
    if (props.open) return;
    preparationRevision.current += 1;
    setPreparing(false);
    setPreparedDeposit(null);
    setOpenedAt(null);
    setWalletOpened(false);
    setResumeAfterPrimaryConnect(false);
    setPendingInitialSessionAddress("");
    setPendingSawDisconnect(false);
    setTransactionPhase("idle");
    setError(null);
    openDeposit.reset();
  }, [props.open]);

  useEffect(() => {
    // Never reuse a transaction prepared for a different connected owner.
    preparationRevision.current += 1;
    setPreparedDeposit(null);
    setPreparing(false);
  }, [globalId, primarySessionReady, walletAddress]);

  const prepareDirectEfhcDeposit = useCallback(async () => {
    if (!globalId || !amountValid || !walletAddress || !primarySessionReady) {
      return;
    }
    const revision = ++preparationRevision.current;
    setError(null);
    setPreparedDeposit(null);
    setTransactionPhase("idle");
    setPreparing(true);
    try {
      const { buildEfhcDirectDepositTx } = await import(
        "../lib/ton/efhc-deposit-transfer"
      );
      const out = await openDepositMetadata();
      const endpoint = publicRuntimeValue("NEXT_PUBLIC_TON_RPC_ENDPOINT")
        || "https://toncenter.com/api/v2/jsonRPC";
      const tx = await buildEfhcDirectDepositTx({
        endpoint,
        senderOwnerAddress: walletAddress,
        receiverOwnerAddress: out.receiver_owner_address,
        jettonMasterAddress: out.jetton_master_address,
        amountEfhc: creditAmount || amount,
        payloadText: out.forward_payload_text,
        feeMessageTonAmount: out.fee_message_ton_amount,
        forwardTonAmount: out.forward_ton_amount,
      });
      const review = createDirectDepositReview({
        tx,
        metadata: out,
        walletAddress,
        amountEfhc: creditAmount || amount,
      });
      if (preparationRevision.current === revision) {
        setPreparedDeposit({
          tx,
          review,
          senderAddress: walletAddress,
          ownerGlobalId: String(globalId),
          amount: creditAmount || amount,
        });
      }
    } catch (caught) {
      if (preparationRevision.current !== revision) return;
      if (isUserRejected(caught)) {
        setTransactionPhase("rejected");
        setError(t("wallet.transaction_rejected"));
        return;
      }
      setTransactionPhase("error");
      const diagnostic = directDepositFailureCode(caught);
      setError(diagnostic
        ? `${t("wallet.transaction_failed")} (${diagnostic})`
        : `${t("wallet.transaction_failed")} (DEPOSIT_PREPARATION_FAILED)`);
    } finally {
      if (preparationRevision.current === revision) setPreparing(false);
    }
  }, [
    amount,
    amountValid,
    creditAmount,
    globalId,
    isUserRejected,
    openDepositMetadata,
    primarySessionReady,
    t,
    walletAddress,
  ]);

  // Prepare the unsigned request after amount changes; only the owner's
  // explicit Transfer click can open TonConnect and request a signature.
  useEffect(() => {
    if (!props.open || !globalId || !amountValid || !walletAddress
      || !primarySessionReady || walletOpened || preparing || preparedDeposit
      || transactionPhase !== "idle") return;
    const timer = window.setTimeout(() => {
      void prepareDirectEfhcDeposit();
    }, 400);
    return () => window.clearTimeout(timer);
  }, [
    amountValid,
    globalId,
    prepareDirectEfhcDeposit,
    preparedDeposit,
    preparing,
    primarySessionReady,
    props.open,
    transactionPhase,
    walletAddress,
    walletOpened,
  ]);

  // Refresh an unsigned expired payload, never retry a wallet submission.
  useEffect(() => {
    if (!props.open || !preparedDeposit || walletOpened || transactionPhase === "signing") return;
    const millisUntilRefresh = preparedDeposit.tx.validUntil * 1000 - Date.now() - 35_000;
    const timer = window.setTimeout(() => {
      preparationRevision.current += 1;
      setPreparedDeposit(null);
      setTransactionPhase("idle");
    }, Math.max(0, millisUntilRefresh));
    return () => window.clearTimeout(timer);
  }, [preparedDeposit, props.open, transactionPhase, walletOpened]);

  const sendPreparedDirectDeposit = useCallback((ready: PreparedDirectDeposit) => {
    // The wallet must receive sendTransaction directly in the user click
    // gesture. Metadata and Jetton-wallet RPC work have already completed.
    if (sendInProgress.current) return;
    const validUntil = ready.tx.validUntil;
    if (!primarySessionReady || !sameTonAddress(ready.senderAddress, walletAddress)
      || ready.ownerGlobalId !== String(globalId)
      || ready.amount !== (creditAmount || amount)
      || !Number.isSafeInteger(validUntil)
      || validUntil <= Math.floor(Date.now() / 1000) + 30) {
      setPreparedDeposit(null);
      setError(t("deposit.direct_open_failed"));
      return;
    }
    sendInProgress.current = true;
    setError(null);
    setTransactionPhase("signing");
    const startedAt = new Date().toISOString();
    // This call must occur before the first await following the click.
    void sendTransaction(ready.tx).then(() => {
      setPreparedDeposit(null);
      setTransactionPhase("signed");
      setOpenedAt(startedAt);
      setWalletOpened(true);
    }).catch((caught: unknown) => {
      setPreparedDeposit(null);
      if (isUserRejected(caught)) {
        setTransactionPhase("rejected");
        setError(t("wallet.transaction_rejected"));
        return;
      }
      setTransactionPhase("error");
      const diagnostic = directDepositFailureCode(caught) || "TONCONNECT_SEND_FAILED";
      setError(`${t("wallet.transaction_failed")} (${diagnostic})`);
    }).finally(() => {
      sendInProgress.current = false;
    });
  }, [amount, creditAmount, globalId, isUserRejected, primarySessionReady, sendTransaction, t, walletAddress]);

  async function sendDirectEfhcDeposit() {
    if (!globalId || !amountValid) {
      setError(t("deposit.amount_invalid"));
      return;
    }
    if (preparedDeposit) {
      sendPreparedDirectDeposit(preparedDeposit);
      return;
    }
    if (preparing || sendInProgress.current) return;
    setError(null);
    try {
      await routePrimaryWalletExecution({
        wallets: walletsMe.data?.wallets,
        currentSessionAddress: walletAddress,
        listWallets,
        connectWallet,
        disconnectWallet,
        markPending: () => {
          setResumeAfterPrimaryConnect(true);
          setPendingInitialSessionAddress(walletAddress);
          setPendingSawDisconnect(!String(walletAddress || "").trim());
        },
        openChooser: async (reason: PrimaryWalletExecutionReason) => {
          if (reason === "primary_transport_unavailable") {
            setError(t("wallet.primary_transport_fallback"));
          }
          openWalletConnect(reason === "no_primary" ? "binding" : "execution_fallback");
        },
        execute: async () => {
          setResumeAfterPrimaryConnect(false);
          await prepareDirectEfhcDeposit();
        },
      });
    } catch (caught) {
      setResumeAfterPrimaryConnect(false);
      if (isUserRejected(caught)) {
        setTransactionPhase("rejected");
        setError(t("wallet.transaction_rejected"));
        return;
      }
      setTransactionPhase("error");
      setError(t("wallet.connection_failed"));
    }
  }

  useEffect(() => {
    if (!resumeAfterPrimaryConnect || walletOpened) return;
    if (!walletAddress) {
      setPendingSawDisconnect(true);
      return;
    }
    if (primarySessionReady) {
      setResumeAfterPrimaryConnect(false);
      setPendingInitialSessionAddress("");
      setPendingSawDisconnect(false);
      void prepareDirectEfhcDeposit();
      return;
    }
    if (
      primaryWallet
      && (pendingSawDisconnect || !pendingInitialSessionAddress)
    ) {
      setResumeAfterPrimaryConnect(false);
      setTransactionPhase("error");
      setError(t("wallet.primary_mismatch"));
    }
  }, [
    prepareDirectEfhcDeposit,
    pendingInitialSessionAddress,
    pendingSawDisconnect,
    primarySessionReady,
    primaryWallet,
    resumeAfterPrimaryConnect,
    t,
    walletAddress,
    walletOpened,
  ]);

  return (
    <Modal
      open={props.open}
      onClose={props.onClose}
      closeDisabled={preparing || openDeposit.isPending || transactionPhase === "signing"}
      title={t("deposit.direct_title")}
      portalColorThemeId={colorThemeId}
    >
      <div
        className="efhc-direct-deposit"
        data-direct-deposit-runtime="efhc-jetton-wallet-reconciliation"
        data-direct-deposit-kind="efhc-jetton-to-efhcm"
        data-direct-deposit-label="direct"
        data-direct-deposit-entry="header-plus-primary-wallet-execution-router-v242"
      >
        {!walletOpened ? (
          <>
            <label className="efhc-direct-deposit_exchange-title">
              <span>{t("deposit.amount_label")}</span>
              <div className="efhc-direct-deposit_amount-control">
                <input
                  type="text"
                  inputMode="decimal"
                  autoComplete="off"
                  value={amount}
                  disabled={transactionPhase === "signing"}
                  data-direct-deposit-amount="efhc-jetton"
                  placeholder={t("deposit.amount_placeholder")}
                  aria-invalid={!amountValid}
                  onChange={(event) => {
                    preparationRevision.current += 1;
                    setPreparedDeposit(null);
                    setPreparing(false);
                    setTransactionPhase("idle");
                    setAmount(event.target.value);
                    setError(null);
                  }}
                />
                <strong>EFHC</strong>
              </div>
            </label>
            <div className="efhc-direct-deposit_summary" data-direct-deposit-summary="exchange-like">
              <div>
                <small>{t("exchange.receive_label")}:</small>
                <strong data-direct-deposit-credit-preview="true">
                  {creditAmount ? `${creditAmount} EFHCm` : "—"}
                </strong>
              </div>
            </div>
          </>
        ) : null}

        {preparedDeposit && !walletOpened ? (
          <section
            className="efhc-direct-deposit_review"
            aria-label={t("deposit.review_title")}
            data-direct-deposit-review="ready"
          >
            <h3>{t("deposit.review_title")}</h3>
            <div className="efhc-direct-deposit_review-rows">
              <div>
                <span>{t("deposit.review_send")}</span>
                <strong data-direct-deposit-review-send="efhc">
                  {preparedDeposit.review.amountEfhc} EFHC
                </strong>
              </div>
              <div>
                <span>{t("deposit.review_receive")}</span>
                <strong data-direct-deposit-review-credit="efhcm">
                  {preparedDeposit.review.amountEfhc} EFHCm
                </strong>
              </div>
              <div>
                <span>{t("deposit.review_recipient")}</span>
                <code data-direct-deposit-review-recipient="owner">
                  {preparedDeposit.review.receiverAddress}
                </code>
              </div>
              <div>
                <span>{t("deposit.review_ton_attached")}</span>
                <strong data-direct-deposit-review-attached="ton">
                  {preparedDeposit.review.attachedTon} TON
                </strong>
              </div>
              <div>
                <span>{t("deposit.review_network_fee")}</span>
                <strong data-direct-deposit-review-fee="pending">
                  {t("deposit.review_fee_pending")}
                </strong>
              </div>
            </div>
            <p className="efhc-direct-deposit_review-note">
              {t("deposit.review_fee_explanation")}
            </p>
            <details className="efhc-direct-deposit_review-details">
              <summary>{t("deposit.review_details")}</summary>
              <dl>
                <dt>{t("deposit.review_network")}</dt>
                <dd>{preparedDeposit.review.network}</dd>
                <dt>{t("deposit.review_sender")}</dt>
                <dd><code>{preparedDeposit.review.walletAddress}</code></dd>
                <dt>{t("deposit.review_execution")}</dt>
                <dd><code>{preparedDeposit.review.executionContractAddress}</code></dd>
                <dt>{t("deposit.review_master")}</dt>
                <dd><code>{preparedDeposit.review.jettonMasterAddress}</code></dd>
                <dt>{t("deposit.review_forward_ton")}</dt>
                <dd>{preparedDeposit.review.forwardedTon} TON</dd>
                <dt>{t("deposit.review_memo")}</dt>
                <dd><code>{preparedDeposit.review.memo}</code></dd>
              </dl>
            </details>
            <p className="efhc-direct-deposit_review-expiry" data-direct-deposit-review-expiry="unix">
              {t("deposit.review_valid_until")}{" "}
              <time dateTime={new Date(preparedDeposit.review.expiresAt * 1000).toISOString()}>
                {new Date(preparedDeposit.review.expiresAt * 1000).toLocaleTimeString()}
              </time>
            </p>
          </section>
        ) : null}

        {transactionPhase === "signing" ? (
          <div
            className="efhc-tonconnect-transaction is-signing"
            role="status"
            aria-live="polite"
            data-tonconnect-transaction="signing"
            data-wallet-transaction="signing"
          >
            <span aria-hidden="true">↻</span>
            <div>
              <strong>{t("wallet.transaction_signing")}</strong>
            </div>
          </div>
        ) : null}

        {transactionPhase === "rejected" ? (
          <div
            className="efhc-tonconnect-transaction is-rejected"
            role="status"
            aria-live="polite"
            data-tonconnect-transaction="rejected"
            data-wallet-transaction="rejected"
          >
            <span aria-hidden="true">×</span>
            <div>
              <strong>{t("wallet.transaction_rejected")}</strong>
            </div>
          </div>
        ) : null}

        {error ? (
          <TelegramEmptyState
            title={t("deposit.direct_error_title")}
            detail={error}
          />
        ) : null}

        {walletOpened && !confirmed ? (
          <div
            className="efhc-direct-deposit_status is-checking"
            role="status"
            aria-live="polite"
            data-direct-deposit-status="checking"
          >
            <span className="efhc-direct-deposit_status-icon">↻</span>
            <div>
              <strong>{t("deposit.status_checking_title")}</strong>
            </div>
          </div>
        ) : null}

        {confirmed ? (
          <div
            className="efhc-direct-deposit_status is-confirmed"
            role="status"
            aria-live="polite"
            data-direct-deposit-status="confirmed"
          >
            <span className="efhc-direct-deposit_status-icon">✓</span>
            <div>
              <strong>
                {t("deposit.status_confirmed_title")}
                {statusQ.data?.amount_efhc
                  ? ` · ${statusQ.data.amount_efhc} EFHCm`
                  : ""}
              </strong>
            </div>
          </div>
        ) : null}

        <div className="efhc-direct-deposit_actions">
          {!walletOpened ? (
            <Button
              variant="primary"
              disabled={
                preparing
                || openDeposit.isPending
                || transactionPhase === "signing"
                || !globalId
                || !amountValid
                || (primarySessionReady && !preparedDeposit && transactionPhase !== "error" && transactionPhase !== "rejected")
              }
              data-direct-deposit-action="send-efhc-jetton"
              onClick={() => void sendDirectEfhcDeposit()}
            >
              {transactionPhase === "signing"
                ? t("wallet.transaction_signing")
                : preparing || openDeposit.isPending
                  ? t("deposit.opening")
                : t("deposit.direct_send_efhc")}
            </Button>
          ) : !confirmed ? (
            <Button
              variant="primary"
              disabled={statusQ.isFetching}
              data-direct-deposit-action="check-status"
              onClick={() => void statusQ.refetch()}
            >
              {statusQ.isFetching
                ? t("common.loading")
                : t("deposit.status_retry")}
            </Button>
          ) : null}
          <Button variant="secondary" data-direct-deposit-action="cancel" onClick={props.onClose} disabled={preparing || openDeposit.isPending || transactionPhase === "signing"}>
            {confirmed ? t("common.close") : t("common.cancel")}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

/* Direct deposit = EFHC jetton -> EFHCm only. */
