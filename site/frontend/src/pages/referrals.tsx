import React, { useContext, useMemo } from "react";
import { useRouter } from "next/router";

import { LayoutContext } from "../components/Layout";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { EmptyState } from "../components/ui/EmptyState";
import {
  GameHero,
  GamePageShell,
  GameStat,
  GameStatsGrid,
} from "../components/ui/GameShell";
import { BonusEarningsStrip } from "../components/ui/BonusEarningsStrip";
import { useT } from "../hooks/useT";
import { useInterfaceVariantSurface } from "../hooks/useInterfaceVariantSurface";
import { useInterfaceCustomization } from "../hooks/useInterfaceCustomization";
import type { SyncSnapshot } from "../hooks/useSnapshot";
import { formatD8ToHuman } from "../lib/format";
import { publicApiErrorMessage } from "../lib/publicError";
import {
  hapticSelection,
  hapticSoft,
  openTelegramLink,
} from "../lib/telegram";
import { useReferralStats } from "../queries/useReferrals";

const SHARE_TARGETS = [
  ["telegram", "Telegram"],
  ["whatsapp", "WhatsApp"],
  ["viber", "Viber"],
  ["facebook", "Facebook"],
  ["x", "X"],
] as const;

function buildShareUrl(kind: string, link: string, text: string): string {
  const encodedLink = encodeURIComponent(link);
  const encodedText = encodeURIComponent(text);
  if (kind === "telegram") {
    return `https://t.me/share/url?url=${encodedLink}&text=${encodedText}`;
  }
  if (kind === "whatsapp") {
    return `https://wa.me/?text=${encodeURIComponent(`${text} ${link}`)}`;
  }
  if (kind === "viber") {
    return `viber://forward?text=${encodeURIComponent(`${text} ${link}`)}`;
  }
  if (kind === "facebook") {
    return `https://www.facebook.com/sharer/sharer.php?u=${encodedLink}`;
  }
  return `https://x.com/intent/tweet?url=${encodedLink}&text=${encodedText}`;
}

async function copyText(value: string): Promise<void> {
  if (typeof navigator === "undefined") return;
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }
  const input = document.createElement("textarea");
  input.value = value;
  input.style.position = "fixed";
  input.style.opacity = "0";
  document.body.appendChild(input);
  input.select();
  document.execCommand("copy");
  input.remove();
}

export default function ReferralsPage(props: {
  snap: SyncSnapshot | null;
}) {
  const t = useT();
  const router = useRouter();
  const ctx = useContext(LayoutContext);
  const customization = useInterfaceCustomization();
  const referralsSurface = useInterfaceVariantSurface<HTMLDivElement>("RG");
  const referralProgressSurface = useInterfaceVariantSurface<HTMLDivElement>(
    "RP",
    { dotsPlacement: "above" },
  );
  const statsQ = useReferralStats();

  const stats = statsQ.data;
  const referralLink = stats?.referral_link?.trim() || "";
  const progress = useMemo(() => {
    const raw = Number(stats?.progress ?? 0);
    return Math.max(0, Math.min(1, raw));
  }, [stats?.progress]);
  const progressPct = `${(progress * 100).toFixed(2)}%`;
  const achievementProgressPct = `${Math.max(0, Math.min(100, (
    ((stats?.level ?? 0) + ((stats?.level ?? 0) >= 5 ? 0 : progress)) / 5
  ) * 100)).toFixed(2)}%`;
  const canShare = Boolean(referralLink);
  const shareText = t("referrals.share_invite_text").replace(
    "{{link}}",
    referralLink,
  );

  const onCopy = async () => {
    if (!referralLink) return;
    await copyText(referralLink);
    hapticSoft(ctx.settings.haptics_enabled);
    ctx.toast(t("referrals.link_copied"), "success");
  };

  const onShare = (kind: string) => {
    if (!referralLink) return;
    hapticSoft(ctx.settings.haptics_enabled);
    const shareUrl = buildShareUrl(kind, referralLink, shareText);
    if (kind === "viber" && typeof window !== "undefined") {
      window.location.href = shareUrl;
      return;
    }
    openTelegramLink(shareUrl);
  };

  const refresh = () => {
    hapticSelection(ctx.settings.haptics_enabled);
    void statsQ.refetch();
  };

  return (
    <GamePageShell
      className="efhc-referrals-shell"
      ref={referralsSurface.ref}
      data-rg={referralsSurface.variant}
      data-global-theme-id={customization.globalThemeId}
      {...referralsSurface.handlers}
      data-public-visual-beauty="tasks-referrals-ranks"
      data-public-surface="referrals"
      data-referrals-runtime="react-query-linkage-1558"
      data-referrals-reference="true"
    >
      <GameHero
        kicker={t("referrals.partner_system")}
        title={t("referrals.title")}
        detail={t("referrals.standalone_detail")}
      >
        <GameStatsGrid compact>
          <GameStat
            label={t("referrals.active")}
            value={stats?.active_referrals ?? 0}
          />
          <GameStat
            label={t("referrals.inactive")}
            value={stats?.inactive_referrals ?? 0}
          />
          <GameStat
            label={t("referrals.total")}
            value={stats?.total_referrals ?? 0}
          />
        </GameStatsGrid>
        <BonusEarningsStrip
          earnedLabel={t("common.earned_all_time")}
          earnedValue={formatD8ToHuman(stats?.referrals_bonus_total ?? "0")}
          remainingLabel={t("common.bonus_remaining")}
          remainingValue={formatD8ToHuman(stats?.bonus_balance ?? "0")}
          asset={stats?.bonus_asset ?? "EFHCb"}
          loading={statsQ.isLoading}
        />
      </GameHero>

      {statsQ.isError ? (
        <EmptyState
          title={t("referrals.load_error")}
          detail={publicApiErrorMessage(statsQ.error, t)}
          actionLabel={t("common.refresh")}
          onAction={refresh}
        />
      ) : null}

      <Card
        title={t("referrals.invite_user_title")}
        className="efhc-referrals-invite-card"
        data-referrals-invite-boundary="deep-link-share-1558"
        data-referrals-invite-canon="1295"
      >
        <div className="text-sm efhc-text-muted2">
          {t("referrals.invite_user_detail")}
        </div>
        <div
          className="efhc-referrals-link-card mt-3 rounded-2xl border efhc-pill-border p-3"
          data-referral-link-main="true"
        >
          <div className="break-all text-sm" data-referral-link-value="true">
            {referralLink || t("referrals.browser_link_pending")}
          </div>
        </div>
        <div className="mt-3">
          <Button
            aria-label={t("referrals.copy_link")}
            data-referral-action="copy-link"
            disabled={!canShare}
            onClick={() => void onCopy()}
            className="w-full"
          >
            {t("referrals.copy_link")}
          </Button>
        </div>
        <div
          className="efhc-referrals-share-grid mt-2"
          data-referral-share-grid="social"
        >
          {SHARE_TARGETS.map(([kind, label]) => (
            <Button
              key={kind}
              aria-label={`${t("referrals.share_link")}: ${label}`}
              data-referral-action="share-link"
              data-referral-share-kind={kind}
              variant={kind === "telegram" ? "primary" : "secondary"}
              disabled={!canShare}
              onClick={() => onShare(kind)}
            >
              <span className="efhc-referrals-share-button_label">
                <img
                  src={`${router.basePath}/brands/${kind}.svg`}
                  alt=""
                  aria-hidden="true"
                  className="efhc-referrals-share-button_logo"
                />
              </span>
            </Button>
          ))}
        </div>
      </Card>

      <Card
        ref={referralProgressSurface.ref}
        {...referralProgressSurface.handlers}
        data-pb={referralProgressSurface.variant}
        data-referrals-progress-levels="1297"
        data-referrals-achievements="visible"
        data-referrals-progress-selection-scope="whole-levels-card"
      >
        <div className="efhc-referral-level-heading">
          <h2 className="efhc-referral-card-title">{t("referrals.achievement_levels_title")}</h2>
          <span className="efhc-referral-level-pill"><span data-i18n-fixed-token="Lvl">Lvl</span> {stats?.level ?? 0}</span>
        </div>
        {(
          <div className="grid gap-3">
            <div
              className="efhc-energy-progress-track"
              data-pb={referralProgressSurface.variant}
              data-referrals-progress-bar="true"
              data-referrals-progress-variant={referralProgressSurface.variant}
              data-progress-library="shared-progress-24"
              data-progress-selection-scope="referrals-independent"
            >
              <div
                aria-label={t("referrals.level_title")}
                className="efhc-energy-progress-fill"
                data-has-progress={progress > 0 ? "true" : "false"}
                style={{ width: progressPct }}
              />
            </div>
            <div className="text-sm efhc-text-muted2">
              {stats?.next_level === null
                ? t("referrals.max_level")
                : `${t("referrals.to_next")}: Lvl ${stats?.next_level ?? "—"} · ${stats?.refs_to_next ?? 0} ${t("referrals.required_active_short")}`}
            </div>
            <div
              className="efhc-referral-achievement-rail"
              data-referrals-level-scale="visual-lvl-1-5"
            >
              <div className="efhc-referral-achievement-track" aria-hidden="true">
                <span style={{ width: achievementProgressPct }} />
              </div>
              <div className="efhc-referral-achievement-nodes">
                {(stats?.level_steps ?? [1, 2, 3, 4, 5].map(level => ({level, required_active: 0}))).map((step) => {
                  const reached = (stats?.level ?? 0) >= step.level;
                  const next = stats?.next_level === step.level;
                  return (
                    <div
                      key={step.level}
                      className="efhc-referral-achievement-node"
                      data-referral-level-step={step.level}
                      data-referral-level-state={
                        reached ? "reached" : next ? "next" : "pending"
                      }
                    >
                      <span className="efhc-referral-achievement-dot">
                        {reached ? "✓" : step.level}
                      </span>
                      <strong><span data-i18n-fixed-token="Lvl">Lvl</span> {step.level}</strong>
                      <small>{new Intl.NumberFormat(ctx.lang).format(step.required_active)}</small>
                    </div>
                  );
                })}
              </div>
              <div className="efhc-referral-achievement-caption">
                {t("referrals.required_active_long")}
              </div>
            </div>
          </div>
        )}
      </Card>


      <Button
        type="button"
        className="w-full efhc-referrals-my-entry"
        variant="secondary"
        data-referrals-my-entrypoint="canonical"
        onClick={() => void router.push("/referrals/my")}
      >
        {t("referrals.my_referrals")}
      </Button>

    </GamePageShell>
  );
}
