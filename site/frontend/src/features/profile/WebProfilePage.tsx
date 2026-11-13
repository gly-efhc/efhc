import React, {
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { useRouter } from "next/router";

import { useInterfaceVariantSurface } from "../../hooks/useInterfaceVariantSurface";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import {
  GameSection,
  GameStat,
  GameStatsGrid,
} from "../../components/ui/GameShell";
import { LayoutContext } from "../../components/Layout";
import { ProfileModal } from "../../components/ProfileModal";
import { ProfileSettingsDialog } from "../../components/profile/ProfileSettingsDialog";
import { AccountProviders } from "./AccountProviders";
import type { Lang } from "../../lib/i18n";
import { getUserLevel } from "../../lib/skins";
import { formatD8ToHuman, sumScaledDown } from "../../lib/format";
import { publicApiErrorMessage } from "../../lib/publicError";
import { type ProfileHistoryItem } from "../../services/profile.service";
import type { UserSettings } from "../../lib/settings";
import type { PanelsSummary } from "../../types/panels";
import { useWalletsMe } from "../../hooks/useWalletsMe";
import { useAuthOwnerGlobalId, useAuthSessionController } from "../../auth/AuthSessionProvider";
import { isDemoGuestSession } from "../../demo/session";
import {
  useProfileHistoryExport,
  useProfileWalletActions,
  useUnifiedProfileHistory,
} from "../../queries/useProfile";
import { ProfileWalletSection } from
  "../../components/profile/ProfileWalletSection";
import { ProfileHistorySection } from
  "../../components/profile/ProfileHistorySection";
import { ProfileAvatarVisual } from
  "../../components/profile/ProfileAvatarVisual";
import { CompactLanguagePicker } from
  "../../components/profile/CompactLanguagePicker";
import {
  balanceHistoryReasonLabel,
} from "../../lib/humanLabels";
import { LegalPolicyView } from
  "../../components/profile/LegalPolicyView";
import type { LegalPolicyKind } from
  "../../data/legalPolicies";
import { navigateBackWithinApp, navigateHomeWithinApp } from
  "../../lib/appBackNavigation";

const SETTINGS_GEAR_INNER_PATH =
  "M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z";

const SETTINGS_GEAR_OUTER_PATH = [
  "M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06",
  "a2 2 0 1 1-2.83 2.83l-.06-.06A1.65 1.65 0 0 0 15 19.4",
  "a1.65 1.65 0 0 0-1 .6V20a2 2 0 1 1-4 0v-.09",
  "a1.65 1.65 0 0 0-1-.6 1.65 1.65 0 0 0-1.82.33",
  "l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.6 15",
  "a1.65 1.65 0 0 0-.6-1H4a2 2 0 1 1 0-4h.09",
  "a1.65 1.65 0 0 0 .6-1 1.65 1.65 0 0 0-.33-1.82",
  "l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.6",
  "h.01a1.65 1.65 0 0 0 1-.6V4a2 2 0 1 1 4 0v.09",
  "a1.65 1.65 0 0 0 1 .6 1.65 1.65 0 0 0 1.82-.33",
  "l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9",
  "v.01a1.65 1.65 0 0 0 .6 1H20a2 2 0 1 1 0 4h-.09",
  "a1.65 1.65 0 0 0-.51 1Z",
].join("");

type ProfileSnap = {
  active_payment?: {
    flow_truth?: {
      product_state?: string | null;
      canonical_center?: string | null;
    } | null;
  } | null;
  latest_withdraw_status?: string | null;
  latest_withdraw_outcome?: {
    outcome_kind?: string | null;
  } | null;
  profile?: {
    username?: string | null;
    is_vip?: boolean;
    has_activ?: boolean;
    main_balance?: string;
    bonus_balance?: string;
    total_generated_kwh?: string;
    available_kwh?: string;
    exchanged_kwh_total?: string;
  };
  panels?: PanelsSummary | null;
};



type Props = {
  snap: ProfileSnap | null;
  settings: UserSettings;
  setSettings: (settings: UserSettings) => void;
};

type Tab = "profile" | "wallet" | "history" | "faq" | "providers";

function readAmount(value: string | undefined): string {
  return formatD8ToHuman(value || "0");
}



function addD8ToHuman(
  a: string | undefined,
  b: string | undefined,
): string {
  try {
    return formatD8ToHuman(sumScaledDown(a || "0", b || "0", 8));
  } catch {
    return "0";
  }
}


// History reason i18n compatibility anchors:
// history.reason.exchange_kwh
// history.reason.panel_purchase
// history.reason.admin_credit
// history.reason.admin_debit
// history.reason.withdraw
// history.reason.shop_purchase
// history.reason.unknown
function reasonLabel(
  reason: string,
  t: (key: string) => string,
): string {
  return balanceHistoryReasonLabel(reason, t);
}

function goHome(router: ReturnType<typeof useRouter>) {
  void navigateHomeWithinApp(router);
}

function goBack(router: ReturnType<typeof useRouter>) {
  navigateBackWithinApp(router);
}




function TabButton(props: {
  active: boolean;
  label: string;
  trustSurface: Tab;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={
        "efhc-profile-tab " +
        (props.active ? "efhc-profile-tab--active" : "")
      }
      data-profile-tab={props.trustSurface}
      data-active={props.active ? "true" : "false"}
      aria-selected={props.active}
      data-profile-trust-tab={props.trustSurface}
      onClick={props.onClick}
    >
      {props.label}
    </button>
  );
}

export default function WebProfilePage(props: Props) {
  const globalId = useAuthOwnerGlobalId();
  const auth = useAuthSessionController();
  const router = useRouter();
  const ctx = useContext(LayoutContext);
  const profileSurface = useInterfaceVariantSurface<HTMLDivElement>(
    "PM",
    { dotsPlacement: "below" },
  );
  const t = ctx.t;
  const walletsQ = useWalletsMe();
  const hasSignedAccount = auth.status === "authenticated" && Boolean(auth.context)
    && !isDemoGuestSession() && !/guest|visual/i.test(auth.context?.provider || "");
  const walletActions = useProfileWalletActions();
  const [historyFilter, setHistoryFilter] = useState("all");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [extendedProfileOpen, setExtendedProfileOpen] = useState(false);
  const historyExport = useProfileHistoryExport();
  const historyExporting = historyExport.isPending;
  const section = String(router.query.section || "profile");
  const activeTab: Tab =
    section === "wallet" || section === "history" ||
    section === "providers"
      ? section as Tab
      : "profile";
  const legalParam = String(router.query.legal || "");
  const routedLegalKind: LegalPolicyKind | null =
    legalParam === "terms" || legalParam === "privacy"
      ? legalParam
      : null;
  const [proofLegalKind, setProofLegalKind] =
    useState<LegalPolicyKind | null>(null);

  useEffect(() => {
    if (section === "faq") {
      void router.replace("/faq");
    }
  }, [router, section]);

  useEffect(() => {
    if (process.env.NEXT_PUBLIC_EFHC_E2E_LEGAL_PROOF !== "1") {
      return;
    }
    const proofWindow = window as Window & {
      __EFHC_LEGAL_PROOF_KIND__?: string;
    };
    const value = proofWindow.__EFHC_LEGAL_PROOF_KIND__;
    if (value === "terms" || value === "privacy") {
      setProofLegalKind(value);
    }
  }, []);

  const legalKind = routedLegalKind || proofLegalKind;

  const unifiedHistoryQ = useUnifiedProfileHistory(
    activeTab === "history",
  );

  const profile = props.snap?.profile || {};
  const username = profile.username || t("profile.guest_user");
  const accountsEntryTitle = t(hasSignedAccount
    ? "profile.linked_accounts_action" : "profile.sign_in_action");
  const level = useMemo(
    () => getUserLevel(profile.total_generated_kwh || "0"),
    [profile.total_generated_kwh],
  );
  const total = readAmount(profile.total_generated_kwh);
  const main = readAmount(profile.main_balance);
  const bonus = readAmount(profile.bonus_balance);
  const totalBalance = addD8ToHuman(
    profile.main_balance,
    profile.bonus_balance,
  );
  const isVip = Boolean(ctx.isVip || profile.is_vip);
  const isActive = Boolean(profile.has_activ);
  const wallets = walletsQ.data?.wallets || [];
  const historyItems = useMemo<ProfileHistoryItem[]>(
    () => unifiedHistoryQ.data?.pages.flatMap((page) => page.items) || [],
    [unifiedHistoryQ.data],
  );
  const walletsError = walletsQ.error
    ? publicApiErrorMessage(walletsQ.error, t, "profile.error_wallet")
    : null;
  const setTab = (tab: Tab) => {
    const query = tab === "profile" ? undefined : { section: tab };
    void router.replace(
      { pathname: "/web-profile", query },
      undefined,
      { shallow: true },
    );
  };

  const updateLang = (lang: Lang) => {
    props.setSettings({ ...props.settings, lang });
  };

  // Единый history stream сохраняет уже загруженные данные во время refetch.
  const historyLoading =
    unifiedHistoryQ.isLoading && historyItems.length === 0;
  const historyCursor = unifiedHistoryQ.hasNextPage
    ? unifiedHistoryQ.data?.pages.at(-1)?.next_cursor || null
    : null;
  const historyError = unifiedHistoryQ.error
    ? publicApiErrorMessage(
      unifiedHistoryQ.error,
      t,
      "profile.error_history",
    )
    : null;

  const refreshHistory = () => {
    void unifiedHistoryQ.refetch();
  };

  const loadMoreHistory = () => {
    if (
      unifiedHistoryQ.hasNextPage
      && !unifiedHistoryQ.isFetchingNextPage
    ) {
      void unifiedHistoryQ.fetchNextPage();
    }
  };

  const exportHistory = async (format: "csv" | "xlsx") => {
    if (historyExporting) return;
    try {
      await historyExport.mutateAsync(format);
      ctx.toast(t("history.export_success"), "success");
    } catch {
      ctx.toast(t("history.export_error"), "error");
    }
  };

  if (legalKind) {
    return (
      <LegalPolicyView
        kind={legalKind}
        lang={props.settings.lang}
      />
    );
  }

  if (activeTab === "providers") {
    return (
      <div className="efhc-profile-page efhc-profile-modal-theme efhc-profile-provider-page"
        data-profile-content="providers" data-provider-route="account-providers"
        data-public-no-raw-payload="true"
      >
        <div className="source-profile-topbar efhc-profile-topbar">
          <button className="source-button secondary" type="button"
            onClick={() => setTab("profile")} data-app-navigation="back-to-profile">
            {t("profile.back")}
          </button>
          <strong>{accountsEntryTitle}</strong>
        </div>
        <AccountProviders />
      </div>
    );
  }

  return (
    <div
      className="efhc-profile-page efhc-profile-modal-theme"
      id="profilePage"
      ref={profileSurface.ref}
      data-wg="WG-01"
      data-pm={profileSurface.variant}
      {...profileSurface.handlers}
      data-public-visual-trust="profile-wallet-history-faq"
      data-profile-active-tab={activeTab}
      data-public-surface="web-profile"
      data-public-no-admin-diagnostics="true"
      data-public-no-raw-payload="true"
    >
      <div className="efhc-profile-topbar">
        <button type="button" data-app-navigation="back" onClick={() => goBack(router)}>
          ← {t("profile.back")}
        </button>
        <strong>{t("profile.page_title")}</strong>
        <div className="efhc-profile-topbar_actions">
          {ctx.canRenderAdminPage || ctx.isAdmin ? (
            <button
              type="button"
              onClick={() => void router.push("/admin")}
            >
              {t("nav.admin")}
            </button>
          ) : null}
          <button type="button" data-app-navigation="exit-profile" onClick={() => goHome(router)}>
            {t("profile.exit")}
          </button>
        </div>
      </div>

      <section
        className="efhc-profile-hero"
        data-profile-hero-layout="three-line"
        data-profile-hero-size="vertical-fit"
      >
        <button
          type="button"
          className="efhc-profile-avatar efhc-profile-avatar-button"
          onClick={() => setExtendedProfileOpen(true)}
          aria-label={t("profile.edit_profile_photo")}
          title={t("profile.edit_profile_photo")}
          data-profile-avatar-entry="settings"
        >
          <ProfileAvatarVisual
            settings={props.settings}
            telegramAvatarUrl={ctx.telegramAvatarUrl}
            size={26}
            alt={username}
          />
        </button>
        <span className="sr-only" data-i18n-v125-runtime="profile-avatar-source-note">
          {t("profile.avatar_source_note")}
        </span>
        <div className="efhc-profile-identity">
          <div className="efhc-profile-name-row">
            <div className="efhc-profile-name">{username}</div>
            {ctx.isAdmin ? (
              <span className="efhc-profile-admin-marker">
                {t("profile.admin_badge")}
              </span>
            ) : null}
          </div>
          <div
            className="efhc-profile-global-id"
            data-profile-global-id={globalId || "unavailable"}
          >
            <span>Global ID -</span>
            <strong>{globalId || "—"}</strong>
          </div>
          <div
            className="efhc-profile-third-row"
            data-profile-status-model="equal-lvl-vip-activ"
          >
            <span className="efhc-profile-status efhc-profile-status--level">
              <span data-i18n-fixed-token="Lvl">Lvl</span> {level}
            </span>
            <span
              className={
                "efhc-profile-status " +
                (isVip
                  ? "efhc-profile-status--on"
                  : "efhc-profile-status--off")
              }
              data-profile-vip-status={isVip ? "active" : "inactive"}
            >
              {t("profile.vip_badge")}
            </span>
            <span
              className={
                "efhc-profile-status " +
                (isActive
                  ? "efhc-profile-status--on"
                  : "efhc-profile-status--off")
              }
              data-profile-active-status={
                isActive ? "active" : "inactive"
              }
            >
              {t("profile.active_badge")}
            </span>
          </div>
        </div>
      </section>

      <div
        className="efhc-profile-tabs source-profile-tabs"
        data-profile-primary-navigation="profile-wallet-history-faq"
      >
        <TabButton
          active={activeTab === "profile"}
          label={t("profile.section_profile_tab")}
          trustSurface="profile"
          onClick={() => setTab("profile")}
        />
        <TabButton
          active={activeTab === "wallet"}
          label={t("wallet.title")}
          trustSurface="wallet"
          onClick={() => setTab("wallet")}
        />
        <TabButton
          active={activeTab === "history"}
          label={t("profile.section_history_tab")}
          trustSurface="history"
          onClick={() => setTab("history")}
        />
        <TabButton
          active={false}
          label={t("faq.title")}
          trustSurface="faq"
          onClick={() => void router.push("/faq")}
        />
      </div>

      {activeTab === "wallet" ? (
        <section
          className="grid gap-3"
          data-wallet-list-boundary="wallet-list-only-1305"
          data-wallet-error-microcopy="safe-1306"
          data-profile-content="wallet"
        >
            <ProfileWalletSection
              wallets={wallets}
              walletsLoading={walletsQ.isLoading}
              walletsError={walletsError}
              walletHint={ctx.walletHint}
              sessionConnected={ctx.walletSessionConnected}
              sessionWalletAddress={ctx.walletSessionAddress}
              sessionRestoring={ctx.walletSessionRestoring}
              tonProofAccepted={ctx.walletProofAccepted}
              connectionPhase={ctx.walletConnectionPhase}
              availableWallets={ctx.availableWallets}
              onConnect={ctx.openWalletConnect}
              onDisconnectSession={ctx.disconnectWalletSession}
              onMakePrimary={(id) => {
                void walletActions.mutateAsync({
                  kind: "make-primary",
                  walletId: id,
                }).catch(() => {
                  ctx.toast(t("common.action_not_available_now"), "error");
                });
              }}
              onRemove={(id) => {
                void walletActions.mutateAsync({
                  kind: "remove",
                  walletId: id,
                }).catch(() => {
                  ctx.toast(t("common.action_not_available_now"), "error");
                });
              }}
              hapticsEnabled={props.settings.haptics_enabled}
            />
        </section>
      ) : null}

      {activeTab === "history" ? (
        <section className="grid gap-3" data-profile-content="history">
            <ProfileHistorySection
              totalBalance={totalBalance}
              mainBalance={main}
              bonusBalance={bonus}
              items={historyItems}
              loading={historyLoading}
              error={historyError}
              nextCursor={historyCursor}
              activeFilter={historyFilter}
              onFilterChange={setHistoryFilter}
              onRefresh={refreshHistory}
              onLoadMore={loadMoreHistory}
              onExportCsv={() => void exportHistory("csv")}
              onExportXlsx={() => void exportHistory("xlsx")}
              withdrawHref="/withdraw"
              exporting={historyExporting}
              reasonLabel={(reason) => reasonLabel(reason, t)}
            />
        </section>
      ) : null}

      {activeTab === "profile" ? (
        <section className="grid gap-3" data-profile-content="profile">
          <GameSection data-profile-main-data="1303">
            <GameStatsGrid>
              <GameStat
                label={t("profile.username_label")}
                value={username}
              />
              <GameStat
                label={t("profile.total_generated")}
                value={total}
                note="kWh"
              />
            </GameStatsGrid>
          </GameSection>
          <Card className="efhc-profile-action-card p-4">
            <div className="efhc-profile-card-heading">
              <div className="min-w-0">
                <div className="text-lg font-extrabold">
                  {t("profile.interface_title")}
                </div>
                <p className="mt-1 text-sm efhc-text-muted2">
                  {t("profile.interface_account_note")}
                </p>
              </div>
              <button
                type="button"
                className="efhc-profile-settings-button"
                aria-label={t("profile.settings_title")}
                title={t("profile.settings_title")}
                onClick={() => setSettingsOpen(true)}
                data-profile-settings-entry="profile-modal"
              >
                <svg
                  aria-hidden="true"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d={SETTINGS_GEAR_INNER_PATH} />
                  <path d={SETTINGS_GEAR_OUTER_PATH} />
                </svg>
              </button>
            </div>
            <div className="mt-4 grid gap-3">
              <CompactLanguagePicker
                value={props.settings.lang}
                label={t("profile.language")}
                showLabel={false}
                getLabel={(lang) => t(`profile.lang.${lang}`)}
                onChange={updateLang}
              />
            </div>
          </Card>
          <Button
            type="button"
            variant="secondary"
            className="w-full source-button wide secondary efhc-profile-provider-entry"
            data-provider-entry="profile-footer"
            data-account-authenticated={hasSignedAccount ? "true" : "false"}
            onClick={() => setTab("providers")}
          >
            {accountsEntryTitle}
          </Button>
        </section>
      ) : null}

      <ProfileSettingsDialog
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        settings={props.settings}
        setSettings={props.setSettings}
      />
      <ProfileModal
        open={extendedProfileOpen}
        onClose={() => setExtendedProfileOpen(false)}
        settings={props.settings}
        setSettings={props.setSettings}
        telegramName={username}
        telegramAvatarUrl={ctx.telegramAvatarUrl}
        isVip={isVip}
        hasActiv={isActive}
        isAdmin={ctx.isAdmin}
        onOpenAdmin={() => void router.push("/admin")}
        initialSection={null}
        walletHint={ctx.walletHint}
        onOpenWalletConnect={ctx.openWalletConnect}
        onOpenDepositLauncher={ctx.openDeposit}
        onDisconnectWalletSession={ctx.disconnectWalletSession}
        tonSessionConnected={ctx.walletSessionConnected}
        tonSessionRestoring={ctx.walletSessionRestoring}
        tonProofAccepted={ctx.walletProofAccepted}
        availableWallets={ctx.availableWallets}
        mainBalance={main}
        bonusBalance={bonus}
      />
    </div>
  );
}
