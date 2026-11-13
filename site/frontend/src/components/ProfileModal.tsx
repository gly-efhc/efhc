// Guard marker: CANCELED: "canceled"
// Guard marker: REJECTED: "rejected"
// Guard marker: PAID: "paid"
// Guard marker: APPROVED: "approved"
// Guard marker: PENDING: "pending"
// Guard marker: History shortcut
// Guard marker: Open Web-Profile
// Guard marker: return `Active payment · ${asset}`;
import Router from "next/router";
import React, { useEffect, useMemo, useRef, useState } from "react";
import { primeBackgroundMusicFromGesture } from "./BackgroundMusicController";
import { Modal } from "./ui/Modal";
import { Button } from "./ui/Button";
import { TelegramSectionRow } from "./ui/telegram/TelegramSectionRow";
import { TelegramStatusBadge } from "./ui/telegram/TelegramStatusBadge";
import type { Lang } from "../lib/i18n";
import type { UserSettings } from "../lib/settings";
import { resetSettings } from "../lib/settings";
import {
  hapticMedium,
  hapticSelection,
} from "../lib/telegram";
import { publicApiErrorMessage } from "../lib/publicError";
import type { HubShopTruthResponse } from "../lib/api/generated/economicUserSeams";
import { useAuthOwnerGlobalId } from "../auth/AuthSessionProvider";
import { useT } from "../hooks/useT";
import { useInterfaceVariantSurface } from "../hooks/useInterfaceVariantSurface";
import {
  nextActionDescription,
  productStateLabel,
  returnPathDescription,
} from "../lib/portal/continuityCopy";
import { useFaqCatalog } from "../hooks/faq/useFaqCatalog";
import { ProfileFaqSection } from "./profile/ProfileFaqSection";
import { ProfileWalletSection } from "./profile/ProfileWalletSection";
import { ProfileHistorySection } from "./profile/ProfileHistorySection";
import { CompactLanguagePicker } from "./profile/CompactLanguagePicker";
import { ProfileAvatarVisual } from "./profile/ProfileAvatarVisual";
import { AvatarPreferenceEditor } from "./profile/AvatarPreferenceEditor";
import {
  deleteWallet,
  makePrimaryWallet,
  type ProfileHistoryItem,
} from "../services/profile.service";
import type { DbId } from "../types/db-id";
import {
  useProfileHistoryExport,
  useProfileWalletSnapshot,
  useProfileWithdrawHistoryPageLoader,
  useUnifiedProfileHistoryPageLoader,
} from "../queries/useProfile";

type WalletItem = {
  id: DbId;
  wallet_address: string;
  wallet_app: string | null;
  is_primary: boolean;
  is_active: boolean;
  created_at: string;
};

type WalletsMeResponse = {
  wallets: WalletItem[];
};

type WithdrawHistoryItem = {
  id: DbId;
  global_id: string;
  amount: string;
  status: string;
  created_at: string;
  updated_at: string;
};

type WithdrawHistoryOut = {
  items: WithdrawHistoryItem[];
  next_cursor: string | null;
};

type Props = {
  open: boolean;
  onClose: () => void;
  settings: UserSettings;
  setSettings: (s: UserSettings) => void;
  telegramName: string;
  telegramAvatarUrl?: string | null;
  isVip: boolean;
  hasActiv: boolean;
  isAdmin: boolean;
  onOpenAdmin: () => void;
  initialSection?: "wallet" | "history" | null;
  walletHint?: string | null;
  onOpenWalletConnect: () => void;
  onOpenDepositLauncher: () => void;
  onDisconnectWalletSession: () => void;
  tonSessionConnected: boolean;
  tonSessionRestoring: boolean;
  tonProofAccepted: boolean;
  availableWallets: {
    name: string;
    appName: string | null;
    imageUrl: string | null;
    aboutUrl: string | null;
    embedded: boolean;
    injected: boolean;
  }[];
  mainBalance: string;
  bonusBalance: string;
};

type ProfileSection = "wallet" | "history" | "faq" | null;

// Quick overlay only. Use it for shortcuts and current status.
// Detailed account, payment, and history views stay in Web-Profile.


// Guard marker: return "no active payment";
function getActivePaymentStateLabel(
  truth: HubShopTruthResponse | null,
): string {
  const stage = truth?.flow_truth?.active_intent?.flow_truth?.product_state;
  const status = truth?.flow_truth?.active_intent?.status;
  if (stage) return productStateLabel(stage);
  if (status) return String(status);
  return "no_active_payment";
}

function getActivePaymentStateTone(
  truth: HubShopTruthResponse | null,
):
  | "primary"
  | "connected"
  | "warning"
  | "neutral"
  | "inactive"
  | "active"
  | "vip" {
  const flow = truth?.flow_truth?.active_intent?.flow_truth;
  if (!flow) return "inactive";
  if (flow.product_state === "terminal_success") return "connected";
  if (
    flow.product_state === "terminal_failed" ||
    flow.product_state === "expired" ||
    flow.lifecycle_stage === "manual_review"
  ) {
    return "warning";
  }
  return "primary";
}

type ToggleKey =
  | "reduce_motion"
  | "show_decimal_detail"
  | "sfx_enabled"
  | "music_enabled"
  | "haptics_enabled"
  | "confirm_actions"
  | "confirm_purchase"
  | "confirm_withdraw"
  | "confirm_convert"
  | "confirm_watch_ad"
  | "toasts_enabled"
  | "important_alerts_only";

function addFixed8(a: string, b: string): string {
  const norm = (value: string): bigint => {
    const s = String(value || "0").trim();
    const neg = s.startsWith("-");
    const raw = neg ? s.slice(1) : s;
    const parts = raw.split(".");
    const whole = parts[0] || "0";
    const frac = (parts[1] || "").padEnd(8, "0").slice(0, 8);
    const val = BigInt(whole) * 100000000n + BigInt(frac || "0");
    return neg ? -val : val;
  };
  const fmt = (value: bigint): string => {
    const neg = value < 0n;
    const abs = neg ? -value : value;
    const whole = abs / 100000000n;
    const frac = String(abs % 100000000n).padStart(8, "0");
    return `${neg ? "-" : ""}${whole.toString()}.${frac}`;
  };
  return fmt(norm(a) + norm(b));
}

function openInternalRoute(path: string): void {
  if (typeof window !== "undefined") {
    void Router.push(path);
  }
}


function latestWithdrawLabel(status: string | null | undefined): string {
  const raw = String(status || "pending").trim().toUpperCase();
  const labels: Record<string, string> = {
    PENDING: "pending",
    APPROVED: "approved",
    PAID: "paid",
    PAID_AUTO: "paid",
    REJECTED: "rejected",
    CANCELED: "canceled",
    CANCELLED: "canceled",
  };
  return labels[raw] || raw.toLowerCase();
}

function latestWithdrawTone(
  status: string | null | undefined,
):
  | "primary"
  | "connected"
  | "warning"
  | "neutral"
  | "inactive"
  | "active"
  | "vip" {
  const raw = String(status || "pending").trim().toUpperCase();
  if (["PAID", "PAID_AUTO", "APPROVED"].includes(raw)) {
    return "connected";
  }
  if (["REJECTED", "CANCELED", "CANCELLED"].includes(raw)) {
    return "warning";
  }
  return "primary";
}

function SectionCard(
  props: React.PropsWithChildren<{ title: string; note?: string }>,
) {
  return (
    <section className="efhc-card p-3.5 space-y-3">
      <div className="space-y-1">
        <div className="text-sm font-semibold">{props.title}</div>
        {props.note ? (
          <div className="text-xs text-[color:var(--tg-hint)]">
            {props.note}
          </div>
        ) : null}
      </div>
      {props.children}
    </section>
  );
}

// Native disclosures keep infrequent settings accessible without a wall of controls.
function SettingsDisclosure(
  props: React.PropsWithChildren<{ title: string; note?: string }>,
) {
  return (
    <details className="efhc-profile-settings-disclosure efhc-card" data-settings-disclosure="true">
      <summary className="efhc-profile-settings-disclosure_summary">
        <span>{props.title}</span>
      </summary>
      <div className="efhc-profile-settings-disclosure_body">
        {props.note ? <p className="text-xs text-[color:var(--tg-hint)]">{props.note}</p> : null}
        {props.children}
      </div>
    </details>
  );
}

function ToggleRow(
  props: {
    title: string;
    desc?: string;
    checked: boolean;
    onToggle: () => void;
  },
) {
  return (
    <button
      type="button"
      onClick={props.onToggle}
      className="efhc-settings-row"
    >
      <div className="efhc-settings-row_copy">
        <div className="efhc-settings-row_title">{props.title}</div>
        {props.desc ? (
          <div className="efhc-settings-row_desc">{props.desc}</div>
        ) : null}
      </div>
      <span
        className={[
          "efhc-switch",
          props.checked ? "efhc-switch--on" : "",
        ].join(" ")}
        aria-hidden="true"
      >
        <span className="efhc-switch_knob" />
      </span>
    </button>
  );
}

function SelectRow(
  props: React.PropsWithChildren<{
    title: string;
    desc?: string;
    value: string;
    onChange: (value: string) => void;
  }>,
) {
  return (
    <div className="efhc-settings-row efhc-settings-row--static">
      <div className="efhc-settings-row_copy">
        <div className="efhc-settings-row_title">{props.title}</div>
        {props.desc ? (
          <div className="efhc-settings-row_desc">{props.desc}</div>
        ) : null}
      </div>
      <select
        value={props.value}
        onChange={(event) => props.onChange(event.target.value)}
        className="efhc-settings-select"
      >
        {props.children}
      </select>
    </div>
  );
}

function NavRow(
  props: {
    title: string;
    desc?: string;
    badge?: string;
    active?: boolean;
    onClick: () => void;
  },
) {
  return (
    <TelegramSectionRow
      title={props.title}
      subtitle={props.desc}
      onClick={props.onClick}
      compact
      rightSlot={
        props.badge ? (
          <TelegramStatusBadge
            label={props.badge}
            tone={props.active ? "primary" : "neutral"}
          />
        ) : undefined
      }
      className={props.active ? "border-[color:var(--tg-button)]/60" : ""}
    />
  );
}

export function ProfileModal(props: Props) {
  const t = useT();
  const profileModalSurface = useInterfaceVariantSurface<HTMLDivElement>("PM", {
    dotsPlacement: "below",
  });
  const globalId = useAuthOwnerGlobalId();
  const modalRoleNote = t("profile.modal_role_note");
  const walletBlockRef = useRef<HTMLDivElement | null>(null);
  const historyBlockRef = useRef<HTMLDivElement | null>(null);
  const faqBlockRef = useRef<HTMLDivElement | null>(null);
  const faqCatalogState = useFaqCatalog(props.settings.lang);
  const faqCatalog = faqCatalogState.catalog;
  const reasonLabel = (reason: string): string => {
    const labels: Record<string, string> = {
      panel_purchase: t("profile.reason.panel_activation"),
      panel_activation: t("profile.reason.panel_activation"),
      exchange_kwh_to_efhc: t(
        "profile.reason.exchange_kwh_to_efhc",
      ),
      referral_bonus: t("profile.reason.referral_bonus"),
      task_bonus: t("profile.reason.task_bonus"),
      ad_bonus: t("profile.reason.ad_bonus"),
      withdraw_hold: t("profile.reason.withdraw_hold"),
      withdraw_refund: t("profile.reason.withdraw_refund"),
      withdraw_payout: t("profile.reason.withdraw_payout"),
      shop_purchase: t("profile.reason.hub_operation"),
    };
    return labels[reason] || reason;
  };

  const [avatarEditorOpen, setAvatarEditorOpen] = useState(false);
  useEffect(() => { if (!props.open) setAvatarEditorOpen(false); }, [props.open]);
  const [activeSection, setActiveSection] = useState<ProfileSection>(
    props.initialSection || null,
  );
  const [wallets, setWallets] = useState<WalletItem[]>([]);
  const [walletsLoading, setWalletsLoading] = useState(false);
  const [walletsError, setWalletsError] = useState<string | null>(null);
  const [historyItems, setHistoryItems] = useState<ProfileHistoryItem[]>([]);
  const [historyFilter, setHistoryFilter] = useState("all");
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [historyCursor, setHistoryCursor] = useState<string | null>(null);
  const historyExport = useProfileHistoryExport();
  const profileWalletSnapshot = useProfileWalletSnapshot();
  const unifiedHistoryPageLoader = useUnifiedProfileHistoryPageLoader();
  const withdrawHistoryPageLoader = useProfileWithdrawHistoryPageLoader();
  const historyExporting = historyExport.isPending;
  const [withdrawItems, setWithdrawItems] = useState<WithdrawHistoryItem[]>([]);
  const [shopTruth, setShopTruth] =
    useState<HubShopTruthResponse | null>(null);
  const [shopTruthLoading, setShopTruthLoading] = useState(false);

  const totalBalance = useMemo(
    () => addFixed8(props.mainBalance, props.bonusBalance),
    [props.mainBalance, props.bonusBalance],
  );
  const connectedWallet = useMemo(
    () => wallets.find((wallet) => wallet.is_active) || null,
    [wallets],
  );
  const latestWithdraw = useMemo(
    () => withdrawItems[0] || null,
    [withdrawItems],
  );

  const activePaymentTitle = useMemo(() => {
    const intent = shopTruth?.flow_truth?.active_intent;
    if (!intent) return t("profile.active_payment_title");
    const asset = String(intent.asset || "payment").toUpperCase();
    return t("profile.active_payment_asset_title").replace(
      "{{asset}}",
      asset,
    );
  }, [shopTruth, t]);

  const activePaymentSubtitle = useMemo(() => {
    const flow = shopTruth?.flow_truth?.active_intent?.flow_truth;
    const intent = shopTruth?.flow_truth?.active_intent;
    if (!intent) {
      return t("profile.active_payment_no_intent_note");
    }
    if (flow?.message_key) {
      return (
        `${t(flow.message_key)} ` +
        returnPathDescription(
          flow.return_path,
          flow.canonical_center,
        )
      );
    }
    return (
      `Intent #${intent.intent_id} · ` +
      nextActionDescription(flow?.next_action || flow?.next_step) +
      ` · ` +
      returnPathDescription(
        flow?.return_path,
        flow?.canonical_center,
      )
    );
  }, [shopTruth, t]);

  useEffect(() => {
    if (!props.open) return;
    setActiveSection(props.initialSection || null);
  }, [props.initialSection, props.open]);

  useEffect(() => {
    if (!props.open || !globalId) return;
    void refreshWallets();
    void refreshHistory();
    void refreshWithdraws();
  }, [globalId, props.open]);

  useEffect(() => {
    const bySection: Record<string, React.RefObject<HTMLDivElement | null>> = {
      wallet: walletBlockRef,
      history: historyBlockRef,
      faq: faqBlockRef,
    };
    const node = activeSection ? bySection[activeSection]?.current : null;
    if (node) {
      node.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [activeSection]);

  function update(patch: Partial<UserSettings>) {
    props.setSettings({ ...props.settings, ...patch });
  }

  function selectLanguage(lang: Lang) {
    hapticSelection(props.settings.haptics_enabled);
    update({ lang });
  }

  function updateToggle(key: ToggleKey, value: boolean) {
    if (key === "music_enabled" && value) primeBackgroundMusicFromGesture();
    hapticSelection(props.settings.haptics_enabled);
    update({ [key]: value } as Partial<UserSettings>);
  }

  function activateSection(section: Exclude<ProfileSection, null>) {
    hapticSelection(props.settings.haptics_enabled);
    setActiveSection(section);
  }

  async function refreshWallets(): Promise<void> {
    setWalletsLoading(true);
    setWalletsError(null);
    try {
      const out = await profileWalletSnapshot.mutateAsync() as WalletsMeResponse;
      setWallets(out.wallets || []);
    } catch (error) {
      setWalletsError(publicApiErrorMessage(error, t, "profile.error_wallet"));
    } finally {
      setWalletsLoading(false);
    }
  }

  async function refreshHistory(cursor?: string | null): Promise<void> {
    if (!cursor && historyItems.length === 0) setHistoryLoading(true);
    setHistoryError(null);
    try {
      const out = await unifiedHistoryPageLoader.mutateAsync(cursor);
      setHistoryItems((prev) =>
        cursor ? [...prev, ...(out.items || [])] : out.items || [],
      );
      setHistoryCursor(out.next_cursor || null);
    } catch (error) {
      setHistoryError(publicApiErrorMessage(error, t, "profile.error_history"));
    } finally {
      setHistoryLoading(false);
    }
  }

  async function exportHistory(format: "csv" | "xlsx"): Promise<void> {
    if (historyExporting) return;
    setHistoryError(null);
    try {
      await historyExport.mutateAsync(format);
    } catch (error) {
      setHistoryError(publicApiErrorMessage(error, t, "history.export_error"));
    }
  }

  function openWithdrawPage(): void {
    if (typeof window === "undefined") return;
    props.onClose();
    void Router.push("/withdraw");
  }


  async function refreshWithdraws(cursor?: string | null): Promise<void> {
    if (!globalId) return;
    try {
      const out = await withdrawHistoryPageLoader.mutateAsync(cursor) as WithdrawHistoryOut;
      setWithdrawItems((prev) =>
        cursor ? [...prev, ...(out.items || [])] : out.items || [],
      );
    } catch {
      if (!cursor) setWithdrawItems([]);
    }
  }

  return (
    <Modal
      open={props.open}
      onClose={props.onClose}
      title={t("profile.modal_title")}
    >
      <div
        ref={profileModalSurface.ref}
        {...profileModalSurface.handlers}
        className="space-y-4 efhc-profile-modal-theme"
        data-pm={profileModalSurface.variant}
      >
        <div className="text-xs text-[color:var(--tg-hint)]">
          {modalRoleNote}
        </div>
        <section
          className="efhc-card p-3.5 space-y-3 efhc-profile-avatar-settings"
          data-profile-avatar-storage="global-id-server-preference"
        >
          <div className="flex items-center gap-3">
            <button type="button" className="efhc-profile-avatar-preview" aria-label={t("profile.edit_profile_photo")} onClick={() => setAvatarEditorOpen(true)} data-profile-avatar-edit-trigger="true">
              <ProfileAvatarVisual
                settings={props.settings}
                telegramAvatarUrl={props.telegramAvatarUrl}
                size={32}
                alt={props.telegramName || t("profile.telegram_user")}
              />
            </button>
            <div className="min-w-0 flex-1 space-y-1">
              <div className="font-semibold">
                {props.telegramName || t("profile.telegram_user")}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <TelegramStatusBadge label={t("profile.telegram_badge")} tone="neutral" />
                {props.hasActiv ? (
                  <TelegramStatusBadge
                    label={t("profile.activ_badge")}
                    tone="active"
                  />
                ) : null}
                {props.isVip ? (
                  <TelegramStatusBadge
                    label={t("profile.vip_badge")}
                    tone="vip"
                  />
                ) : null}
                {props.isAdmin ? (
                  <TelegramStatusBadge label={t("profile.admin_badge")} tone="warning" />
                ) : null}
              </div>
            </div>
          </div>

        </section>

        <SettingsDisclosure
          title={t("profile.quick_overlay_title")}
          note={t("profile.quick_overlay_note")}
        >
          <TelegramSectionRow
            title={t("profile.wallet_shortcut_title")}
            subtitle={
              connectedWallet
                ? t("profile.wallet_shortcut_connected").replace(
                  "{{wallet}}",
                  connectedWallet.is_primary
                    ? t("wallet.primary_wallet")
                    : t("wallet.additional_wallet"),
                )
                : t("profile.wallet_shortcut_unbound")
            }
            compact
            onClick={() => activateSection("wallet")}
            rightSlot={
              <TelegramStatusBadge
                label={connectedWallet
                  ? t("wallet.status_connected")
                  : t("wallet.status_not_connected")}
                tone={connectedWallet ? "connected" : "warning"}
              />
            }
          />
          <TelegramSectionRow
            title={t("profile.top_up_efhc_title")}
            subtitle={
              t("profile.top_up_efhc_note")
            }
            compact
            onClick={props.onOpenDepositLauncher}
            rightSlot={
              <TelegramStatusBadge
                label={t("profile.launcher_badge")}
                tone="primary"
              />
            }
          />
          <TelegramSectionRow
            title={t("profile.open_web_profile_title")}
            subtitle={
              t("profile.account_center_status")
                .replace("{{total}}", totalBalance)
                .replace("{{main}}", props.mainBalance)
                .replace("{{bonus}}", props.bonusBalance)
            }
            compact
            onClick={() => void Router.push("/web-profile")}
            rightSlot={
              <TelegramStatusBadge
                label={t("profile.account_center_badge")}
                tone="primary"
              />
            }
          />
          <TelegramSectionRow
            title={activePaymentTitle}
            subtitle={
              shopTruthLoading
                ? t("profile.checking_top_up_state")
                : activePaymentSubtitle
            }
            compact
            onClick={() => void Router.push("/web-profile")}
            rightSlot={
              <TelegramStatusBadge
                label={getActivePaymentStateLabel(shopTruth) ===
                  "no_active_payment"
                  ? t("profile.no_active_payment")
                  : getActivePaymentStateLabel(shopTruth)}
                tone={getActivePaymentStateTone(shopTruth)}
              />
            }
          />
          <TelegramSectionRow
            title={t("profile.latest_withdraw_title")}
            subtitle={
              latestWithdraw
                ? t("profile.latest_withdraw_request")
                  .replace("{{id}}", String(latestWithdraw.id))
                  .replace("{{amount}}", latestWithdraw.amount)
                : t("profile.latest_withdraw_empty")
            }
            compact
            onClick={openWithdrawPage}
            rightSlot={
              <TelegramStatusBadge
                label={latestWithdrawLabel(latestWithdraw?.status)}
                tone={latestWithdrawTone(latestWithdraw?.status)}
              />
            }
          />
          <TelegramSectionRow
            title={t("profile.history_shortcut_title")}
            subtitle={
              historyItems.length > 0
                ? t("profile.history_shortcut_loaded").replace(
                  "{{count}}",
                  String(historyItems.length),
                )
                : t("profile.history_shortcut_empty")
            }
            compact
            onClick={() => void Router.push("/web-profile")}
            rightSlot={
              <TelegramStatusBadge
                label={t("history.title")}
                tone="neutral"
              />
            }
          />
        </SettingsDisclosure>

        <SettingsDisclosure
          title={t("profile.section_title")}
          note={t("profile.section_note")}
        >
          <NavRow
            title={t("wallet.title")}
            desc={t("profile.wallet_nav_desc")}
            active={activeSection === "wallet"}
            badge={activeSection === "wallet" ? t("profile.open_badge") : undefined}
            onClick={() => activateSection("wallet")}
          />
          <NavRow
            title={t("history.title")}
            desc={t("profile.history_nav_desc")}
            active={activeSection === "history"}
            badge={activeSection === "history" ? t("profile.open_badge") : undefined}
            onClick={() => activateSection("history")}
          />
          <NavRow
            title={t("faq.title")}
            desc={t("profile.faq_nav_desc")}
            active={activeSection === "faq"}
            badge={activeSection === "faq" ? t("profile.open_badge") : undefined}
            onClick={() => activateSection("faq")}
          />
        </SettingsDisclosure>

        {activeSection === "wallet" ? (
          <SectionCard
            title={t("wallet.title")}
            note={t("profile.wallet_section_note")}
          >
            <div ref={walletBlockRef} className="space-y-3">
              <ProfileWalletSection
                wallets={wallets}
                walletsLoading={walletsLoading}
                walletsError={walletsError}
                walletHint={props.walletHint}
                sessionConnected={props.tonSessionConnected}
                sessionRestoring={props.tonSessionRestoring}
                tonProofAccepted={props.tonProofAccepted}
                connectionPhase={
                  props.tonSessionRestoring
                    ? "restoring"
                    : props.tonSessionConnected
                      ? "connected"
                      : "disconnected"
                }
                onConnect={props.onOpenWalletConnect}
                onDisconnectSession={props.onDisconnectWalletSession}
                onMakePrimary={(id) => {
                  makePrimaryWallet(id)
                    .then(() => refreshWallets())
                    .catch(() => undefined);
                }}
                onRemove={(id) => {
                  deleteWallet(id)
                    .then(() => refreshWallets())
                    .catch(() => undefined);
                }}
                hapticsEnabled={props.settings.haptics_enabled}
              />
            </div>
          </SectionCard>
        ) : null}

        {activeSection === "history" ? (
          <SectionCard title={t("history.title")}>
            <div ref={historyBlockRef} className="space-y-3">
              <ProfileHistorySection
                totalBalance={totalBalance}
                mainBalance={props.mainBalance}
                bonusBalance={props.bonusBalance}
                items={historyItems}
                loading={historyLoading}
                error={historyError}
                nextCursor={historyCursor}
                activeFilter={historyFilter}
                onFilterChange={setHistoryFilter}
                onRefresh={() => {
                  void refreshHistory();
                  void refreshWithdraws();
                  hapticMedium(props.settings.haptics_enabled);
                }}
                onLoadMore={() => {
                  if (!historyCursor) return;
                  void refreshHistory(historyCursor);
                }}
                onExportCsv={() => void exportHistory("csv")}
                onExportXlsx={() => void exportHistory("xlsx")}
              withdrawHref="/withdraw"
                exporting={historyExporting}
                reasonLabel={reasonLabel}
              />
            </div>
          </SectionCard>
        ) : null}

        {activeSection === "faq" ? (
          <SectionCard
            title={t("faq.title")}
            note={t("profile.faq_section_note")}
          >
            <div ref={faqBlockRef} className="space-y-3">
              <ProfileFaqSection t={t} catalog={faqCatalog} />
            </div>
          </SectionCard>
        ) : null}

        <SectionCard title={t("profile.interface_title")}>
          <div className="efhc-profile-compact-controls">
            <CompactLanguagePicker
              profileSurface
              value={props.settings.lang}
              label={t("profile.language_title")}
              getLabel={(lang) => t(`profile.lang.${lang}`)}
              onChange={(lang) => {
                hapticSelection(props.settings.haptics_enabled);
                selectLanguage(lang);
              }}
            />
          </div>
          <ToggleRow title={t("profile.reduce_motion")} checked={props.settings.reduce_motion} onToggle={() => updateToggle("reduce_motion", !props.settings.reduce_motion)} />
          <ToggleRow title={t("profile.ui_sounds")} checked={props.settings.sfx_enabled} onToggle={() => updateToggle("sfx_enabled", !props.settings.sfx_enabled)} />
          <ToggleRow title={t("profile.haptic_feedback")} checked={props.settings.haptics_enabled} onToggle={() => updateToggle("haptics_enabled", !props.settings.haptics_enabled)} />
          <ToggleRow title={t("profile.background_music")} checked={props.settings.music_enabled} onToggle={() => updateToggle("music_enabled", !props.settings.music_enabled)} />
        </SectionCard>

        <Modal open={avatarEditorOpen && props.open} onClose={() => setAvatarEditorOpen(false)} title={t("profile.edit_profile_photo")} portalColorThemeId={props.settings.color_theme_id}>
          <AvatarPreferenceEditor />
        </Modal>

        {props.isAdmin ? (
          <div className="flex justify-end" data-admin-entry-owner="profile-only" data-admin-global-id-gate="future-backend-authoritative">
            <Button onClick={props.onOpenAdmin}>{t("profile.admin_panel")}</Button>
          </div>
        ) : null}
      </div>
    </Modal>
  );
}
