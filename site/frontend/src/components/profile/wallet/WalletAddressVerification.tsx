import React, { useContext, useEffect, useRef, useState } from "react";
import { useT } from "../../../hooks/useT";
import { LayoutContext } from "../../Layout";

type Props = { address: string };

type CopyState = "idle" | "copied" | "failed";

export function WalletAddressVerification({ address }: Props) {
  const t = useT();
  const ctx = useContext(LayoutContext);
  const [copyState, setCopyState] = useState<CopyState>("idle");
  const resetTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => {
    if (resetTimerRef.current !== null) {
      clearTimeout(resetTimerRef.current);
    }
  }, []);

  function scheduleIdleReset() {
    if (resetTimerRef.current !== null) {
      clearTimeout(resetTimerRef.current);
    }
    resetTimerRef.current = setTimeout(() => {
      setCopyState("idle");
      resetTimerRef.current = null;
    }, 1400);
  }

  async function copyAddress() {
    try {
      if (!navigator.clipboard?.writeText) {
        throw new Error("clipboard_unavailable");
      }
      await navigator.clipboard.writeText(address);
      setCopyState("copied");
      scheduleIdleReset();
      ctx.toast(t("wallet.address_copied"), "success");
    } catch {
      setCopyState("failed");
      scheduleIdleReset();
      ctx.toast(t("wallet.copy_address_failed"), "error");
    }
  }

  const liveMessage = copyState === "copied"
    ? t("wallet.address_copied")
    : copyState === "failed"
      ? t("wallet.copy_address_failed")
      : "";

  return (
    <div className="efhc-wallet-address-zone">
      <button
        type="button"
        className="efhc-wallet-address-control standalone-wallet-address"
        data-wallet-address-copy-control="true"
        data-wallet-copy-keyboard="native-button"
        data-wallet-full-address="true"
        data-copy-state={copyState}
        aria-label={`${t("wallet.copy_address")}: ${address}`}
        title={t("wallet.copy_address")}
        onClick={() => void copyAddress()}
      >
        <code>{address}</code>
        <span
          className="efhc-wallet-copy-feedback standalone-wallet-copy-feedback"
          data-visible={copyState === "copied" ? "true" : "false"}
          aria-hidden={copyState === "copied" ? undefined : true}
        >
          {t("wallet.copied")}
        </span>
      </button>
      <span
        className="sr-only"
        role="status"
        aria-live="polite"
        aria-atomic="true"
      >
        {liveMessage}
      </span>
    </div>
  );
}
