import React, { useState } from "react";
import { useT } from "../../hooks/useT";
import { useShopLauncher, useShopLauncherTruth } from "../../queries/useShopLauncher";
import {
  TelegramActionCard,
} from "../../components/ui/telegram/TelegramActionCard";
import {
  TelegramBadgeGroup,
} from "../../components/ui/telegram/TelegramBadgeGroup";
import {
  TelegramHeroSection,
} from "../../components/ui/telegram/TelegramHeroSection";
import {
  TelegramInfoBlock,
} from "../../components/ui/telegram/TelegramInfoBlock";
import {
  TelegramEmptyState,
} from "../../components/ui/telegram/TelegramEmptyState";
import {
  TelegramStatusBadge,
} from "../../components/ui/telegram/TelegramStatusBadge";


export default function ShopEntryPage() {
  const t = useT();
  const shopLauncher = useShopLauncher();
  const shopTruth = useShopLauncherTruth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function openShop() {
    setBusy(true);
    setError("");
    try {
      await shopLauncher.mutateAsync();
    } catch {
      setError(t("portal.shop_entry.open_failed_clean_detail"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4" data-shop-launcher-truth={shopTruth.data ? "loaded" : shopTruth.isError ? "error" : "pending"}>
      <TelegramHeroSection
        eyebrow={t("portal.shop_entry.eyebrow")}
        title={t("portal.shop_entry.title")}
        subtitle={t("portal.shop_entry.subtitle")}
        badges={
          <TelegramBadgeGroup>
            <TelegramStatusBadge
              label={t("portal.shop_entry.card_access_value")}
              tone="connected"
            />
            <TelegramStatusBadge
              label={t("portal.shop_entry.card_mode_value")}
              tone="primary"
            />
            <TelegramStatusBadge
              label={t("portal.shop_entry.card_truth_value")}
              tone="neutral"
            />
          </TelegramBadgeGroup>
        }
      />

      <div className="grid gap-3 md:grid-cols-3">
        <TelegramInfoBlock
          title={t("portal.shop_entry.card_access")}
          description={t("portal.shop_entry.card_access_value")}
        />
        <TelegramInfoBlock
          title={t("portal.shop_entry.card_mode")}
          description={t("portal.shop_entry.card_mode_value")}
        />
        <TelegramInfoBlock
          title={t("portal.shop_entry.card_truth")}
          description={t("portal.shop_entry.card_truth_value")}
        />
      </div>

      <TelegramActionCard
        title={t("portal.shop_entry.action_title")}
        description={t("portal.shop_entry.action_description")}
        primaryLabel={
          busy
            ? t("portal.shop_entry.opening")
            : t("portal.shop_entry.open_action")
        }
        onPrimary={() => {
          if (!busy) {
            void openShop();
          }
        }}
        emphasis
        disabled={busy}
      />

      <TelegramInfoBlock
        title={t("portal.shop_entry.flow_title")}
        description={t("portal.shop_entry.flow_description")}
      >
        <div className="mt-3 space-y-2">
          <TelegramStatusBadge
            label={t("portal.shop_entry.flow_step_access")}
            tone="connected"
          />
          <TelegramStatusBadge
            label={t("portal.shop_entry.flow_step_shop")}
            tone="primary"
          />
          <TelegramStatusBadge
            label={t("portal.shop_entry.flow_step_intent")}
            tone="neutral"
          />
        </div>
      </TelegramInfoBlock>

      {error ? (
        <TelegramEmptyState
          title={t("portal.shop_entry.open_failed_title")}
          detail={
            error || t("portal.shop_entry.open_failed_clean_detail")
          }
          actionLabel={t("common.refresh")}
          onAction={() => {
            if (!busy) {
              void openShop();
            }
          }}
        />
      ) : null}
    </div>
  );
}
