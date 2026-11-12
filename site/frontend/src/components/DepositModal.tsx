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
import { GENESIS_JSON_RPC_ENDPOINT } from "../lib/ton/testnet-guard";
import { describeDirectDepositFailure, type DirectDepositFailureStage } from "../lib/ton/direct-deposit-errors";
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
  const [resumeAfterPrimaryConnect, setResumeAfterPrimaryConnect] = useState(false);
  const [pendingInitialSessionAddress, setPendingInitialSessionAddress] = useState("");
  const [pendingSawDisconnect, setPendingSawDisconnect] = useState(false);
  const [transactionPhase, setTransactionPhase] = useState<
    WalletTransactionPhase
  >("idle");
  const [error, setError] = useState<string | null>(null);
  const [preparing, setPreparing] = useState(false);
  const depositInFlightRef = useRef(false);
  const openDeposit = useDirectDepositOpen();
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
    setOpenedAt(null);
    setWalletOpened(false);
    setResumeAfterPrimaryConnect(false);
    setPendingInitialSessionAddress("");
    setPendingSawDisconnect(false);
    setTransactionPhase("idle");
    setPreparing(false);
    setError(null);
    openDeposit.reset();
  }, [props.open]);

  const performDirectEfhcDeposit = useCallback(async () => {
    if (!globalId || !amountValid || !walletAddress || !primarySessionReady || depositInFlightRef.current) {
      return;
    }
    depositInFlightRef.current = true;
    setError(null);
    setPreparing(true);
    setTransactionPhase("idle");
    const startedAt = new Date().toISOString();
    let stage: DirectDepositFailureStage = "metadata";
    try {
      const { buildEfhcDirectDepositTx } = await import(
        "../lib/ton/efhc-deposit-transfer"
      );
      const out = await openDeposit.mutateAsync();
      // The mainnet/testnet RPC endpoint must always follow the chosen
      // TON chain. A runtime override cannot silently break the guard.
      stage = "jetton_wallet";
      const tx = await buildEfhcDirectDepositTx({
        endpoint: GENESIS_JSON_RPC_ENDPOINT,
        senderOwnerAddress: walletAddress,
        receiverOwnerAddress: out.receiver_owner_address,
        jettonMasterAddress: out.jetton_master_address,
        amountEfhc: creditAmount || amount,
        payloadText: out.forward_payload_text,
        feeMessageTonAmount: out.fee_message_ton_amount,
        forwardTonAmount: out.forward_ton_amount,
      });
      stage = "wallet_send";
      setPreparing(false);
      setTransactionPhase("signing");
      await sendTransaction(tx);
      setTransactionPhase("signed");
      setOpenedAt(startedAt);
      setWalletOpened(true);
    } catch (caught) {
      if (isUserRejected(caught)) {
        setTransactionPhase("rejected");
        setError(t("wallet.transaction_rejected"));
        return;
      }
      setTransactionPhase("error");
      setError(`${t("wallet.transaction_failed")} [${describeDirectDepositFailure(caught, stage)}]`);
    } finally {
      depositInFlightRef.current = false;
      setPreparing(false);
    }
  }, [
    amountValid,
    creditAmount,
    globalId,
    isUserRejected,
    openDeposit,
    primarySessionReady,
    sendTransaction,
    t,
    walletAddress,
  ]);

  async function sendDirectEfhcDeposit() {
    if (!globalId || !amountValid) {
      setError(t("deposit.amount_invalid"));
      return;
    }
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
          await performDirectEfhcDeposit();
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
      setError(`${t("wallet.connection_failed")} [${describeDirectDepositFailure(caught, "wallet_connection")}]`);
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
      void performDirectEfhcDeposit();
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
    performDirectEfhcDeposit,
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
                  data-direct-deposit-amount="efhc-jetton"
                  placeholder={t("deposit.amount_placeholder")}
                  aria-invalid={!amountValid}
                  onChange={(event) => {
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
