import React, { useContext, useMemo } from "react";
import { useRouter } from "next/router";
import { useAuthOwnerGlobalId } from "../auth/AuthSessionProvider";
import { TelegramEmptyState } from "../components/ui/telegram/TelegramEmptyState";
import { Button } from "../components/ui/Button";
import {
  GameHero,
  GameNotice,
  GamePageShell,
  GameStat,
  GameStatsGrid,
} from "../components/ui/GameShell";
import { publicApiErrorMessage } from "../lib/publicError";
import { newIdempotencyKey } from "../lib/idempotency";
import type { SyncSnapshot } from "../hooks/useSnapshot";
import { LayoutContext } from "../components/Layout";
import { useT } from "../hooks/useT";
import { hapticError, hapticSuccess } from "../lib/telegram";
import { cmp8, format8, formatD8ToHuman } from "../lib/format";
import { ExchangePanel } from "../components/ExchangePanel";
import {
  useExchangeConvert,
  useExchangePreview,
} from "../queries/useExchange";
import { useInterfaceCustomization } from
  "../hooks/useInterfaceCustomization";
import { useInterfaceVariantSurface } from
  "../hooks/useInterfaceVariantSurface";

export default function ExchangePage(props: {
  tg_id: number | null;
  snap: SyncSnapshot | null;
}) {
  const { confirm, toast, settings, openProfile } = useContext(LayoutContext);
  const router = useRouter();
  const customization = useInterfaceCustomization();
  const heroSurface = useInterfaceVariantSurface<HTMLElement>("XH");
  const statsSurface = useInterfaceVariantSurface<HTMLDivElement>("XS", { registerDots: false, interactive: false });
  const t = useT();
  const globalId = useAuthOwnerGlobalId();
  const tg_id = props.tg_id;
  const previewQuery = useExchangePreview();
  const exchangeMutation = useExchangeConvert();

  const snapshotAvailable = format8(
    props.snap?.profile?.available_kwh || "0",
  );
  const preview = previewQuery.data ?? null;
  const availableKwh = preview?.available_kwh || snapshotAvailable;
  const maxExchangeableKwh =
    preview?.max_exchangeable_kwh || availableKwh;

  const mainBalance = format8(
    props.snap?.profile?.main_balance || "0",
  );

  const canExchange = useMemo(
    () => cmp8(maxExchangeableKwh, "0.00000000") > 0,
    [maxExchangeableKwh],
  );

  const previewError = previewQuery.error
    ? publicApiErrorMessage(previewQuery.error, t)
    : "";

  const doPartialExchange = async (amountKwh: string) => {
    if (customization.mutationBlocked) return;
    if (!globalId) {
      toast(t("browser.auth_needed"), "info");
      return;
    }
    if (!canExchange) return;
    const amount = format8(amountKwh);
    if (cmp8(amount, "0.00000000") <= 0) return;
    if (cmp8(amount, maxExchangeableKwh) > 0) return;
    const ok = await confirm(
      "convert",
      t("exchange.confirm_exchange_title"),
      t("exchange.confirm_exchange_detail"),
    );
    if (!ok) return;
    try {
      const result = await exchangeMutation.mutateAsync({
        amountKwh: amount,
        idempotencyKey: newIdempotencyKey(),
      });
      hapticSuccess(settings.haptics_enabled);
      toast(result.detail || t("exchange.exchange_success"), "success");
    } catch (error: unknown) {
      hapticError(settings.haptics_enabled);
      toast(
        publicApiErrorMessage(error, t, "exchange.exchange_failed"),
        "error",
      );
    }
  };

  return (
    <GamePageShell
      className="efhc-exchange-shell"
      data-exchange-route-contract="current-user-no-tg-path"
      data-exchange-contract-proof="current-user"
      data-exchange-runtime-proof="react-query-transaction"
    >
      <GameHero
        ref={heroSurface.ref}
        {...heroSurface.handlers}
        className="efhc-exchange-hero"
        data-xh={heroSurface.variant}
        kicker={t("exchange.energy_exchange_kicker")}
        title={t("exchange.title")}
        detail={t("exchange.one_way_energy_detail")}
      >
        <div
          ref={statsSurface.ref}
          {...statsSurface.handlers}
          className="efhc-exchange-stats-surface"
          data-xs={statsSurface.variant}
        >
          <GameStatsGrid>
            <GameStat
              label={t("exchange.dashboard_available")}
              value={format8(availableKwh)}
            />
            <GameStat label={t("exchange.rate")} value="1 kWh = 1 EFHCm" />
            <GameStat
              label={t("history.balance_main_asset")}
              value={formatD8ToHuman(mainBalance)}
            />
          </GameStatsGrid>
        </div>
      </GameHero>

      <div className="efhc-exchange-body-variant">
      {previewQuery.isLoading ? (
        <GameNotice
          title={t("common.loading")}
          detail={t("exchange.interactive_loading")}
        />
      ) : null}

      <ExchangePanel
        maxKwh={maxExchangeableKwh}
        onExchange={doPartialExchange}
        pending={exchangeMutation.isPending}
      />

      {previewError ? (
        <GameNotice
          title={t("exchange.preview_unavailable_title")}
          detail={t("exchange.preview_unavailable_detail")}
        />
      ) : null}

      {!previewQuery.isLoading && !previewError && !canExchange ? (
        <TelegramEmptyState
          title={t("exchange.exchange_unavailable_title")}
          detail={t("exchange.exchange_unavailable_detail")}
        />
      ) : null}

      <div
        className="efhc-exchange-history-boundary"
        data-exchange-history-boundary="light-link-only"
      >
        <span className="efhc-exchange-history-hint">
          {t("exchange.history_profile_note")}
        </span>
        <button
          type="button"
          className="efhc-exchange-history-link"
          data-exchange-history-link="account-history"
          data-exchange-history-link-light="true"
          onClick={() => openProfile("history")}
        >
          {t("exchange.open_history")}
        </button>
      </div>
      <Button
        type="button"
        className="w-full efhc-exchange-withdraw-button efhc-theme03-cta"
        variant="secondary"
        data-exchange-withdraw-entrypoint="restored-canonical"
        data-exchange-withdraw-width="exchange-action"
        onClick={() => void router.push("/withdraw")}
      >
        {t("exchange.withdraw_title")} EFHCm
      </Button>
      </div>
    </GamePageShell>
  );
}
