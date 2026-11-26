import React, { useEffect, useState } from "react";
import { useAuthSessionController } from "../../auth/AuthSessionProvider";
import { getAuthAuthorizationHeader } from "../../lib/auth-session";
import { demoRawRequest } from "../../demo/transport";
import { isDemoBackendMode } from "../../demo/session";
import { useT } from "../../hooks/useT";
import styles from "./wallet-cards.module.css";
import { WalletCardAction } from "./wallet/WalletCardAction";

type Card = { slot: number; display_address: string; is_primary: boolean };

function parseCards(payload: unknown, owner: string): Card[] {
  const rows = (payload as { cards?: unknown })?.cards;
  if (!Array.isArray(rows) || rows.length !== 3) return [];
  return rows.every((row, index) => row && row.slot === index + 1
    && row.display_address === `GENESIS-TEST-${Number(owner)}-${index + 1}`
    && row.is_primary === (index === 0)) ? rows : [];
}

function GenesisWalletLayout() {
  const t = useT();
  const session = useAuthSessionController();
  const owner = session.status === "authenticated" ? session.context?.global_id ?? "" : "";
  const authorization = owner ? getAuthAuthorizationHeader() : null;
  const [result, setResult] = useState<{ owner: string; authorization: string; cards: Card[] } | null>(null);
  useEffect(() => {
    if (!/^000000(?:3[0-9]{3}|4000)$/.test(owner) || Number(owner) < 3001 || !authorization) return;
    const controller = new AbortController();
    void demoRawRequest("/staging/wallet-layout", "GET", {
      signal: controller.signal, headers: { Authorization: authorization },
    }).then(async (response) => (
      response.ok && response.headers.get("X-EFHC-Data-Source") === "neon-test"
        ? parseCards(await response.json(), owner) : []
    )).then(cards => {
      if (!controller.signal.aborted && getAuthAuthorizationHeader() === authorization) {
        setResult({ owner, authorization, cards });
      }
    }).catch(() => undefined);
    return () => controller.abort();
  }, [owner, authorization]);

  const cards = result?.owner === owner && result.authorization === authorization ? result.cards : [];
  if (!cards.length) return null;
  return (
    <section aria-label="Genesis TEST" data-genesis-wallet-layout="true">
      <div className="source-card-title">Genesis TEST</div>
      <div className={`standalone-wallet-list ${styles.boundCards}`}>
        {cards.map(card => (
          <div className="efhc-wallet-entry" key={card.slot} data-genesis-wallet-slot={card.slot}>
            <div className="efhc-wallet-address-zone">
              <span className="efhc-wallet-address-control"><code>{card.display_address}</code></span>
            </div>
            {card.is_primary ? (
              <div className="standalone-wallet-actions">
                <WalletCardAction sizeLabel={t("wallet.primary_badge")} status="wallet-primary-badge">
                  {t("wallet.primary_badge")}
                </WalletCardAction>
              </div>
            ) : null}
          </div>
        ))}
      </div>
    </section>
  );
}

export function TestWalletLayout() {
  return isDemoBackendMode() ? <GenesisWalletLayout /> : null;
}
