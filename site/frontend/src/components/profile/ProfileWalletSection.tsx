import React, { useMemo } from "react";
import type {
  WalletConnectionPhase,
} from "../../lib/wallet-provider";
import { useT } from "../../hooks/useT";
import { TelegramInfoBlock } from "../ui/telegram/TelegramInfoBlock";
import { Button } from "../ui/Button";
import {
  WalletListItem,
  type WalletListItemModel,
} from "./wallet/WalletListItem";
import { WalletPrimaryCard } from "./wallet/WalletPrimaryCard";
import type { DbId } from "../../types/db-id";
import { sameTonAddress } from "../../lib/wallet-provider/primaryWalletRouting";

type Props = {
  wallets: WalletListItemModel[];
  walletsLoading: boolean;
  walletsError: string | null;
  walletHint?: string | null;
  sessionConnected: boolean;
  sessionWalletAddress?: string | null;
  sessionRestoring: boolean;
  tonProofAccepted: boolean;
  connectionPhase: WalletConnectionPhase;
  availableWallets?: unknown[];
  onConnect: () => void;
  onDisconnectSession: () => void;
  onMakePrimary: (id: DbId) => void;
  onRemove: (id: DbId) => void;
  hapticsEnabled: boolean;
};

export function ProfileWalletSection(props: Props) {
  const t = useT();
  const serverBoundWallets = useMemo(
    () => props.wallets
      .filter((wallet) => wallet.is_active && wallet.proof_verified === true)
      .slice()
      .sort((left, right) => Number(right.is_primary) - Number(left.is_primary)),
    [props.wallets],
  );
  const serverPrimaryWallet = useMemo(
    () => serverBoundWallets.find((wallet) => wallet.is_primary) || null,
    [serverBoundWallets],
  );
  const additionalBoundWallets = useMemo(
    () => serverBoundWallets.filter((wallet) => wallet.id !== serverPrimaryWallet?.id),
    [serverBoundWallets, serverPrimaryWallet?.id],
  );
  const liveSessionWallet = useMemo(
    () => props.sessionConnected && props.sessionWalletAddress
      ? serverBoundWallets.find((wallet) => (
          sameTonAddress(wallet.wallet_address, props.sessionWalletAddress)
        )) || null
      : null,
    [props.sessionConnected, props.sessionWalletAddress, serverBoundWallets],
  );
  const liveSessionWalletId = liveSessionWallet?.id ?? null;

  return (
    <div
      className="efhc-wallet-trust-section space-y-3"
      data-public-visual-trust="profile-wallet-history-faq"
      data-public-surface="wallet"
      data-wallet-list-only="1305"
    >
      {props.walletsError ? (
        <TelegramInfoBlock
          title={t("wallet.error_title")}
          data-wallet-error-microcopy="safe-1306"
        >
          {t("wallet.error_body")}
        </TelegramInfoBlock>
      ) : null}

      <div className="space-y-2">
        <div
          className="efhc-wallet-section-heading text-xs font-semibold uppercase tracking-wide text-[color:var(--tg-hint)]"
          data-wallet-section-heading="linked"
        >
          {t("wallet.linked_wallets")}
        </div>
        <Button
          variant="secondary"
          className="w-full efhc-wallet-connect-cta"
          data-wallet-provider-action="connect"
          data-linked-wallets={serverBoundWallets.length > 0 ? "present" : "empty"}
          disabled={props.sessionRestoring || props.connectionPhase === "connecting" || props.connectionPhase === "verifying"}
          onClick={props.onConnect}
        >
          {props.sessionRestoring || props.connectionPhase === "connecting" || props.connectionPhase === "verifying"
            ? t("wallet.connection_waiting")
            : t("wallet.connect_button")}
        </Button>
        <span className="sr-only" role="status" aria-live="polite">
          {props.walletHint || ""}
        </span>
        {props.walletsLoading ? (
          <TelegramInfoBlock title={t("wallet.loading_wallets_title")}>
            {t("wallet.loading_wallets_body")}
          </TelegramInfoBlock>
        ) : null}
        {!props.walletsLoading && !props.walletsError && serverBoundWallets.length === 0 ? (
          <TelegramInfoBlock title={t("wallet.empty_title")}>
            {t("wallet.no_active_linked")}
          </TelegramInfoBlock>
        ) : null}
        <WalletPrimaryCard
          wallet={serverPrimaryWallet}
          sessionOwned={Boolean(serverPrimaryWallet && serverPrimaryWallet.id === liveSessionWalletId)}
          onRemove={props.onRemove}
          hapticsEnabled={props.hapticsEnabled}
        />
        {additionalBoundWallets.map((wallet) => (
          <WalletListItem
            key={wallet.id}
            wallet={wallet}
            sessionOwned={wallet.id === liveSessionWalletId}
            onMakePrimary={props.onMakePrimary}
            onRemove={props.onRemove}
            hapticsEnabled={props.hapticsEnabled}
            />
        ))}
      </div>
    </div>
  );
}
