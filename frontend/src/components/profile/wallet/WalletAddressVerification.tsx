import React, { useContext, useEffect, useRef, useState } from "react";
import { useT } from "../../../hooks/useT";
import { LayoutContext } from "../../Layout";
import { Address } from "@ton/core/dist/address/Address";
import { GENESIS_WALLET_CHAIN, isGenesisTestRuntime, TON_TESTNET_CHAIN } from "../../../lib/ton/testnet-guard";

type Props = { address: string; projectTest?: boolean };

type CopyState = "idle" | "copied" | "failed";

export function publicWalletAddress(address: string, projectTest: boolean, testnet: boolean): string | null {
  try {
    const parsed = Address.parse(address);
    if (!projectTest && !Address.isRaw(address)) {
      const friendly = Address.parseFriendly(address);
      if (friendly.isTestOnly || !testnet) return address;
    }
    return parsed.toString({ bounceable: false, urlSafe: true, testOnly: projectTest || testnet });
  } catch {
    return null;
  }
}

export function WalletAddressVerification({ address, projectTest = false }: Props) {
  const publicAddress = publicWalletAddress(
    address, projectTest, isGenesisTestRuntime() && GENESIS_WALLET_CHAIN === TON_TESTNET_CHAIN,
  );
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
      if (!publicAddress || !navigator.clipboard?.writeText) {
        throw new Error("clipboard_unavailable");
      }
      await navigator.clipboard.writeText(publicAddress);
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
        aria-label={`${t("wallet.copy_address")}: ${publicAddress ?? ""}`}
        disabled={!publicAddress}
        title={t("wallet.copy_address")}
        onClick={() => void copyAddress()}
      >
        <code>{publicAddress ?? "—"}</code>
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
