import React, { useContext, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/router";

import { LayoutContext } from "../../components/Layout";
import { AdminListExpandControl, useAdminListWindow } from "../../components/admin/AdminListWindow";
import { ProfileHistorySection } from "../../components/profile/ProfileHistorySection";
import { BalanceSummaryCard } from "../../components/profile/history/BalanceSummaryCard";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { GameSection, GameStat, GameStatsGrid } from "../../components/ui/GameShell";
import { TelegramEmptyState } from "../../components/ui/telegram/TelegramEmptyState";
import { TelegramSectionRow } from "../../components/ui/telegram/TelegramSectionRow";
import { TelegramStatusBadge } from "../../components/ui/telegram/TelegramStatusBadge";
import { useT } from "../../hooks/useT";
import {
  formatD8ToHuman,
  format8,
  fromScaledBigint,
  sumScaledDown,
  toScaledBigintDown,
} from "../../lib/format";
import { newIdempotencyKey } from "../../lib/idempotency";
import { getUserLevel } from "../../lib/skins";
import { balanceHistoryReasonLabel } from "../../lib/humanLabels";
import { navigateBackWithinApp } from "../../lib/appBackNavigation";
import { parseGlobalId, type GlobalId } from "../../types/identity";
import {
  adminPath,
  ADMIN_USERS_GLOBAL_ID_HISTORY_PATH,
  ADMIN_USERS_GLOBAL_ID_PATH,
  ADMIN_USERS_GLOBAL_ID_PANELS_ACTIVATE_PATH,
  ADMIN_USERS_RESOLVE_PROVIDER_PATH,
  ADMIN_TRANSFER_PATH,
} from "../../lib/api/generated/adminSeams";
import { adminUiErrorMessage } from "../../lib/adminError";
import { useAdminPageGlobalIdSelection } from "../../hooks/admin/useAdminPageGlobalIdSelection";
import { useAdminLinkedTransport } from "../../queries/useAdminLinkedTransport";
import {
  profileHistoryPageSchema,
  type ProfileHistoryItem,
} from "../../services/profile.service";

type UserDetail = {
  global_id: GlobalId;
  username?: string | null;
  is_active: boolean;
  is_vip: boolean;
  ton_wallet?: string | null;
  main_balance: string;
  bonus_balance: string;
  available_kwh: string;
  total_generated_kwh: string;
  active_panels_count: number;
  last_seen_at?: string | null;
  created_at: string;
  updated_at: string;
  vip_checked_at?: string | null;
  vip_since?: string | null;
  last_sync_at?: string | null;
};

type Tab = "profile" | "funds" | "history" | "providers";
type TransferDirection = "credit" | "debit";
type TransferBalance = "main" | "bonus";

type TransferState = {
  direction: TransferDirection;
  balance: TransferBalance;
  amount: string;
  reason: string;
};

const ADMIN_USERS_LAST_GLOBAL_ID_KEY = "efhc:admin:users:last-global-id";
const ADMIN_USERS_RECENT_GLOBAL_IDS_KEY = "efhc:admin:users:recent-global-ids";
const PANEL_PRICE_EFHC = "100.00000000";

function normalAmount(value: string): string {
  return value.trim().replace(",", ".");
}

function userLabel(name?: string | null): string {
  return name ? `@${name}` : "Пользователь";
}

function normalizeTab(value: unknown): Tab {
  return value === "funds" || value === "history" || value === "providers"
    ? value
    : "profile";
}

function SectionCard(
  props: React.PropsWithChildren<{ title: string; note?: string; eam?: string }>,
) {
  return (
    <section className="efhc-card efhc-admin-user-section-card p-3.5 space-y-3" data-eam-family={props.eam}>
      <div className="space-y-1">
        <div className="text-sm font-semibold">{props.title}</div>
        {props.note ? (
          <div className="text-xs text-[color:var(--tg-hint)]">{props.note}</div>
        ) : null}
      </div>
      {props.children}
    </section>
  );
}

function ProfileNavRow(props: {
  title: string;
  desc?: string;
  badge?: string;
  active?: boolean;
  onClick: () => void;
}) {
  return (
    <TelegramSectionRow
      title={props.title}
      subtitle={props.desc}
      onClick={props.onClick}
      compact
      rightSlot={props.badge ? (
        <TelegramStatusBadge
          label={props.badge}
          tone={props.active ? "primary" : "neutral"}
        />
      ) : undefined}
      className={`efhc-admin-user-nav-row ${props.active ? "border-[color:var(--tg-button)]/60" : ""}`.trim()}
    />
  );
}

export default function AdminUsersPage() {
  const router = useRouter();
  const ctx = useContext(LayoutContext);
  const adminApiRequest = useAdminLinkedTransport();
  const t = useT();
  const { selectedGlobalId, restored: selectionRestored, rememberGlobalId, clearGlobalId } = useAdminPageGlobalIdSelection("users", { storageKey: ADMIN_USERS_LAST_GLOBAL_ID_KEY });
  const [globalIdInput, setGlobalIdInput] = useState("");
  const [selected, setSelected] = useState<UserDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [uiError, setUiError] = useState("");
  const [busyAction, setBusyAction] = useState("");
  const [providerSubject, setProviderSubject] = useState("");
  const [providerLoading, setProviderLoading] = useState(false);
  const [recentGlobalIds, setRecentGlobalIds] = useState<string[]>([]);
  const [notice, setNotice] = useState("");
  const [transferConfirmed, setTransferConfirmed] = useState(false);
  const [transferIdempotencyKey, setTransferIdempotencyKey] = useState("");
  const [panelConfirmed, setPanelConfirmed] = useState(false);
  const [panelIdempotencyKey, setPanelIdempotencyKey] = useState("");
  const [historyItems, setHistoryItems] = useState<ProfileHistoryItem[]>([]);
  const [historyCursor, setHistoryCursor] = useState<string | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const historyWindow = useAdminListWindow(historyItems, `admin-user-history:${selected?.global_id || "none"}`);
  const [historyFilter, setHistoryFilter] = useState("all");
  const [historyLoadedFor, setHistoryLoadedFor] = useState<string | null>(null);
  // Cycle0238: any future Balance/History export must use the exact-one-user
  // guard in lib/adminUsersBalanceHistoryExportGuard.ts before download.
  const [transfer, setTransfer] = useState<TransferState>({
    direction: "credit",
    balance: "bonus",
    amount: "100.00000000",
    reason: "Перевод средств",
  });

  const activeTab = normalizeTab(router.query.section);
  const globalId = globalIdInput.trim();
  const validGlobalId = /^\d{10}$/.test(globalId);

  const rememberUser = (id: string) => {
    if (typeof window === "undefined") return;
    rememberGlobalId(id);
    setRecentGlobalIds((current) => {
      const next = [id, ...current.filter((value) => value !== id)].slice(0, 3);
      window.sessionStorage.setItem(ADMIN_USERS_RECENT_GLOBAL_IDS_KEY, JSON.stringify(next));
      return next;
    });
  };

  const showNotice = (message: string) => {
    setNotice(message);
  };

  const setTab = (tab: Tab) => {
    const query: Record<string, string> = {};
    if (selected?.global_id) query.global_id = String(selected.global_id);
    if (tab !== "profile") query.section = tab;
    void router.replace(
      { pathname: "/admin/users", query },
      undefined,
      { shallow: true, scroll: false },
    );
  };

  async function loadUser(id: string, nextTab: Tab = activeTab) {
    if (!/^\d{10}$/.test(id)) {
      setUiError("Global ID должен содержать ровно 10 цифр.");
      return;
    }
    setLoading(true);
    setUiError("");
    try {
      const data = await adminApiRequest<UserDetail>(
        adminPath(ADMIN_USERS_GLOBAL_ID_PATH, { global_id: parseGlobalId(id) }),
        "GET",
      );
      setSelected(data);
      setGlobalIdInput(String(data.global_id));
      rememberUser(String(data.global_id));
      setTransferConfirmed(false);
      setTransferIdempotencyKey("");
      setPanelConfirmed(false);
      setPanelIdempotencyKey("");
      setHistoryItems([]);
      setHistoryCursor(null);
      setHistoryLoadedFor(null);
      setHistoryError(null);

      const query: Record<string, string> = {
        global_id: String(data.global_id),
      };
      if (nextTab !== "profile") query.section = nextTab;
      void router.replace(
        { pathname: "/admin/users", query },
        undefined,
        { shallow: true, scroll: false },
      );
    } catch (e: unknown) {
      setSelected(null);
      setUiError(adminUiErrorMessage(e, t));
    } finally {
      setLoading(false);
    }
  }

  async function loadHistory(
    id: GlobalId,
    nextCursor: string | null = null,
    append = false,
  ) {
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const base = adminPath(
        ADMIN_USERS_GLOBAL_ID_HISTORY_PATH,
        { global_id: id },
      );
      const query = new URLSearchParams();
      query.set("limit", "20");
      if (nextCursor) query.set("cursor", nextCursor);
      const raw = await adminApiRequest<unknown>(
        `${base}?${query.toString()}`,
        "GET",
      );
      const page = profileHistoryPageSchema.parse(raw);
      setHistoryItems((current) => append ? [...current, ...page.items] : page.items);
      setHistoryCursor(page.next_cursor);
      if (append) historyWindow.revealServerPage();
      else historyWindow.collapse();
      setHistoryLoadedFor(String(id));
    } catch (e: unknown) {
      setHistoryError(adminUiErrorMessage(e, t));
    } finally {
      setHistoryLoading(false);
    }
  }

  useEffect(() => {
    if (!router.isReady || !selectionRestored || typeof window === "undefined") return;
    try {
      const stored = JSON.parse(
        window.sessionStorage.getItem(ADMIN_USERS_RECENT_GLOBAL_IDS_KEY) || "[]",
      );
      if (Array.isArray(stored)) {
        setRecentGlobalIds(
          stored.filter((value): value is string => /^\d{10}$/.test(String(value))).slice(0, 3),
        );
      }
    } catch {
      setRecentGlobalIds([]);
    }

    const queryId = String(router.query.global_id || "").trim();
    const id = /^\d{10}$/.test(queryId) ? queryId : String(selectedGlobalId || "");
    if (/^\d{10}$/.test(id) && id !== String(selected?.global_id || "")) {
      setGlobalIdInput(id);
      void loadUser(id);
    }
  }, [router.isReady, router.query.global_id, selectionRestored]);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(""), 3200);
    return () => window.clearTimeout(timer);
  }, [notice]);

  useEffect(() => {
    if (
      activeTab === "history" &&
      selected &&
      historyLoadedFor !== String(selected.global_id) &&
      !historyLoading
    ) {
      void loadHistory(selected.global_id);
    }
  }, [activeTab, selected?.global_id, historyLoadedFor, historyLoading]);

  function resetUserSelection() {
    clearGlobalId();
    setGlobalIdInput("");
    setSelected(null);
    setUiError("");
    setNotice("");
    setTransferConfirmed(false);
    setTransferIdempotencyKey("");
    setPanelConfirmed(false);
    setPanelIdempotencyKey("");
    setHistoryItems([]);
    setHistoryCursor(null);
    setHistoryLoadedFor(null);
    setHistoryError(null);
    void router.replace({ pathname: "/admin/users" }, undefined, { shallow: true, scroll: false });
  }

  const balances = useMemo(() => {
    if (!selected) return null;
    const main = String(selected.main_balance ?? "0");
    const bonus = String(selected.bonus_balance ?? "0");
    return { main, bonus, total: sumScaledDown(main, bonus, 8) };
  }, [selected]);

  const normalizedAmount = normalAmount(transfer.amount);
  const transferPreview = useMemo(() => {
    if (!selected) return null;
    try {
      const amount = toScaledBigintDown(normalizedAmount, 8);
      if (amount <= 0n) return null;
      const beforeRaw = transfer.balance === "bonus"
        ? selected.bonus_balance
        : selected.main_balance;
      const before = toScaledBigintDown(beforeRaw, 8);
      const after = transfer.direction === "credit"
        ? before + amount
        : before - amount;
      return {
        before: fromScaledBigint(before, 8),
        after: fromScaledBigint(after, 8),
        valid: after >= 0n,
      };
    } catch {
      return null;
    }
  }, [normalizedAmount, selected, transfer.balance, transfer.direction]);

  const panelPreview = useMemo(() => {
    if (!balances) return null;
    const before = toScaledBigintDown(balances.total, 8);
    const cost = toScaledBigintDown(PANEL_PRICE_EFHC, 8);
    return {
      before: fromScaledBigint(before, 8),
      after: fromScaledBigint(before - cost, 8),
      valid: before >= cost,
    };
  }, [balances]);

  const canTransfer = Boolean(
    selected &&
    transferConfirmed &&
    transferPreview?.valid &&
    transfer.reason.trim(),
  );

  async function applyTransfer() {
    if (!selected || !canTransfer) return;
    setBusyAction("transfer");
    setUiError("");
    try {
      const idem = transferIdempotencyKey || newIdempotencyKey();
      if (!transferIdempotencyKey) setTransferIdempotencyKey(idem);
      await adminApiRequest(ADMIN_TRANSFER_PATH, "POST", {
        idempotencyKey: idem,
        body: {
          global_id: selected.global_id,
          direction: transfer.direction,
          balance: transfer.balance,
          amount: normalizedAmount,
          reason: transfer.reason.trim(),
        },
      });
      setTransferConfirmed(false);
      setTransferIdempotencyKey("");
      const message = transfer.direction === "credit"
        ? `${formatD8ToHuman(normalizedAmount)} ${transfer.balance === "bonus" ? "EFHCb" : "EFHCm"} переведено`
        : `${formatD8ToHuman(normalizedAmount)} ${transfer.balance === "bonus" ? "EFHCb" : "EFHCm"} списано`;
      await loadUser(String(selected.global_id));
      showNotice(message);
    } catch (e: unknown) {
      setUiError(adminUiErrorMessage(e, t));
    } finally {
      setBusyAction("");
    }
  }

  async function activatePaidPanel() {
    if (!selected || !panelConfirmed) return;
    setBusyAction("panel");
    setUiError("");
    try {
      const idem = panelIdempotencyKey || newIdempotencyKey();
      if (!panelIdempotencyKey) setPanelIdempotencyKey(idem);
      await adminApiRequest(
        adminPath(
          ADMIN_USERS_GLOBAL_ID_PANELS_ACTIVATE_PATH,
          { global_id: selected.global_id },
        ),
        "POST",
        { idempotencyKey: idem, body: {} },
      );
      setPanelConfirmed(false);
      setPanelIdempotencyKey("");
      await loadUser(String(selected.global_id));
      showNotice("Панель активирована");
    } catch (e: unknown) {
      setUiError(adminUiErrorMessage(e, t));
    } finally {
      setBusyAction("");
    }
  }

  async function resolveProviderUser() {
    const subject = providerSubject.trim();
    if (!subject) return;
    setProviderLoading(true);
    setUiError("");
    try {
      const query = new URLSearchParams({ q: subject });
      const resolved = await adminApiRequest<{ global_id: GlobalId }>(
        `${ADMIN_USERS_RESOLVE_PROVIDER_PATH}?${query.toString()}`,
        "GET",
      );
      setProviderSubject("");
      await loadUser(String(resolved.global_id), "profile");
    } catch (e: unknown) {
      setUiError(adminUiErrorMessage(e, t));
    } finally {
      setProviderLoading(false);
    }
  }

  if (!ctx.canRenderAdminPage && typeof ctx.isAdmin === "boolean" && !ctx.isAdmin) {
    return (
      <div className="efhc-profile-page efhc-admin-user-profile" data-admin-page-marker="ADM-01" data-eam-family="EAM-ADMIN-001">
        <TelegramEmptyState title="Пользователь" detail="Доступ запрещён." />
      </div>
    );
  }

  const username = selected ? userLabel(selected.username) : "Пользователь";
  const level = selected ? getUserLevel(selected.total_generated_kwh || "0") : 0;
  const isActive = Boolean(selected && selected.active_panels_count > 0);
  const isVip = Boolean(selected?.is_vip);

  return (
    <div
      className="efhc-profile-page efhc-admin-user-profile"
      data-admin-user-profile="profile-composition"
      data-admin-bottom-nav-policy="player-nav-excluded"
      data-admin-page-marker="ADM-01"
      data-eam-family="EAM-ADMIN-001"
    >
      <div className="efhc-profile-topbar" data-eam-family="EAM-ADMIN-002">
        <button
          type="button"
          onClick={() => activeTab === "profile" ? navigateBackWithinApp(router) : setTab("profile")}
        >
          ← Назад
        </button>
        <strong>Пользователь</strong>
        <div className="efhc-profile-topbar_actions">
          <button type="button" onClick={() => void router.push("/admin")}>☰ Меню</button>
        </div>
      </div>

      <Card className="efhc-profile-action-card p-3" data-eam-family="EAM-ADMIN-008" data-admin-selected-global-id={selectedGlobalId || "none"} data-admin-global-id-search-canon="v435">
        <div className="grid gap-2">
          <input
            className="efhc-input w-full"
            inputMode="numeric"
            pattern="[0-9]*"
            maxLength={10}
            placeholder="Global ID"
            value={globalIdInput}
            onChange={(e) => setGlobalIdInput(e.target.value.replace(/\D/g, "").slice(0, 10))}
            onKeyDown={(e) => {
              if (e.key === "Enter" && validGlobalId) void loadUser(globalId, "profile");
            }}
          />
          <div className="grid grid-cols-2 gap-2">
            <Button variant="secondary" className="w-full min-w-0" disabled={loading || (!globalIdInput && !selectedGlobalId)} onClick={resetUserSelection}>
              Сбросить
            </Button>
            <Button variant="secondary" className="efhc-admin-user-search-button w-full min-w-0" disabled={!validGlobalId || loading} onClick={() => void loadUser(globalId, "profile")}>
              {loading ? t("common.loading") : "Найти"}
            </Button>
          </div>
        </div>
        {recentGlobalIds.length ? (
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className="text-xs text-[color:var(--tg-hint)]">Недавние</span>
            {recentGlobalIds.map((id) => (
              <button
                key={id}
                type="button"
                className="rounded-full border border-[color:var(--tg-hint)]/20 px-2.5 py-1 text-xs font-semibold"
                onClick={() => void loadUser(id, "profile")}
              >
                {id}
              </button>
            ))}
          </div>
        ) : null}
      </Card>

      <section
        className="efhc-profile-hero"
        data-profile-hero-layout="three-line"
        data-profile-hero-size="vertical-fit"
      >
        <div className="efhc-profile-avatar grid place-items-center text-lg font-black" aria-hidden="true">
          {(selected?.username || String(selected?.global_id || "P")).slice(0, 1).toUpperCase()}
        </div>
        <div className="efhc-profile-identity">
          <div className="efhc-profile-name-row">
            <div className="efhc-profile-name">{username}</div>
          </div>
          <div className="efhc-profile-global-id">
            <span>Global ID -</span>
            <strong>{selected?.global_id || "—"}</strong>
          </div>
          <div className="efhc-profile-third-row" data-profile-status-model="equal-lvl-vip-activ">
            <span className="efhc-profile-status efhc-profile-status--level">
              <span data-i18n-fixed-token="Lvl">Lvl</span> {level}
            </span>
            <span className={`efhc-profile-status ${isVip ? "efhc-profile-status--on" : "efhc-profile-status--off"}`}>
              VIP
            </span>
            <span className={`efhc-profile-status ${isActive ? "efhc-profile-status--on" : "efhc-profile-status--off"}`}>
              Activ
            </span>
          </div>
        </div>
      </section>

      {selected ? (
        <SectionCard title="Разделы" eam="EAM-ADMIN-007">
          <ProfileNavRow
            title="Средства"
            desc="Балансы, перевод и возврат средств"
            active={activeTab === "funds"}
            badge={activeTab === "funds" ? "Открыто" : undefined}
            onClick={() => setTab("funds")}
          />
          <ProfileNavRow
            title="Баланс"
            desc="Движение средств выбранного пользователя"
            active={activeTab === "history"}
            badge={activeTab === "history" ? "Открыто" : undefined}
            onClick={() => setTab("history")}
          />
          <ProfileNavRow
            title="Провайдеры"
            desc="Поиск по привязанному провайдеру"
            active={activeTab === "providers"}
            badge={activeTab === "providers" ? "Открыто" : undefined}
            onClick={() => setTab("providers")}
          />
        </SectionCard>
      ) : null}

      {uiError ? <TelegramEmptyState title="Не удалось выполнить действие" detail={uiError} /> : null}

      {!selected && !uiError ? (
        <TelegramEmptyState title="Выберите пользователя" detail="Введите Global ID." />
      ) : null}

      {selected && activeTab === "profile" ? (
        <div className="grid gap-3">
          <GameSection>
            <GameStatsGrid>
              <GameStat label="Активные панели" value={String(selected.active_panels_count)} />
              <GameStat label="Сгенерировано" value={format8(selected.total_generated_kwh)} note="kWh" />
              <GameStat label="Доступно" value={format8(selected.available_kwh)} note="kWh" />
            </GameStatsGrid>
          </GameSection>
          <section className="efhc-card p-3.5 efhc-admin-user-profile-data-static" data-eam-family="EAM-ADMIN-007">
            <div className="text-sm font-semibold">Данные профиля</div>
            <div className="mt-2 grid gap-1.5 text-sm">
              <div className="flex items-center justify-between gap-3"><span className="text-[color:var(--tg-hint)]">Регистрация</span><strong>{new Date(selected.created_at).toLocaleString()}</strong></div>
              <div className="flex items-center justify-between gap-3"><span className="text-[color:var(--tg-hint)]">Последняя активность</span><strong>{selected.last_seen_at ? new Date(selected.last_seen_at).toLocaleString() : "—"}</strong></div>
              {selected.vip_since ? <div className="flex items-center justify-between gap-3"><span className="text-[color:var(--tg-hint)]">VIP с</span><strong>{new Date(selected.vip_since).toLocaleString()}</strong></div> : null}
            </div>
          </section>
        </div>
      ) : null}

      {selected && balances && activeTab === "funds" ? (
        <section className="grid gap-3">
          <SectionCard title="Средства" eam="EAM-ADMIN-010">
            <div className="efhc-history-balance-stack">
              <BalanceSummaryCard title="Общий баланс" value={formatD8ToHuman(balances.total)} tone="neutral" asset="EFHC" />
              <BalanceSummaryCard title="Основной баланс" value={formatD8ToHuman(balances.main)} tone="main" asset="EFHCm" />
              <BalanceSummaryCard title="Бонусный баланс" value={formatD8ToHuman(balances.bonus)} tone="bonus" asset="EFHCb" />
            </div>
          </SectionCard>

          <SectionCard title="Перевести / забрать средства" eam="EAM-ADMIN-010">
            <div className="mt-3 grid gap-2 md:grid-cols-2">
              <label className="grid gap-1">
                <span className="text-xs opacity-75">Операция</span>
                <select className="efhc-input" value={transfer.direction} onChange={(e) => {
                  setTransferConfirmed(false);
                  setTransferIdempotencyKey("");
                  setTransfer((prev) => ({ ...prev, direction: e.target.value as TransferDirection }));
                }}>
                  <option value="credit">Перевести пользователю</option>
                  <option value="debit">Забрать у пользователя</option>
                </select>
              </label>
              <label className="grid gap-1">
                <span className="text-xs opacity-75">Назначение</span>
                <select className="efhc-input" value={transfer.balance} onChange={(e) => {
                  setTransferConfirmed(false);
                  setTransferIdempotencyKey("");
                  setTransfer((prev) => ({ ...prev, balance: e.target.value as TransferBalance }));
                }}>
                  <option value="bonus">EFHCb</option>
                  <option value="main">EFHCm</option>
                </select>
              </label>
              <label className="grid gap-1">
                <span className="text-xs opacity-75">Сумма EFHC</span>
                <input className="efhc-input" inputMode="decimal" value={transfer.amount} onChange={(e) => {
                  setTransferConfirmed(false);
                  setTransferIdempotencyKey("");
                  setTransfer((prev) => ({ ...prev, amount: e.target.value }));
                }} />
              </label>
              <label className="grid gap-1">
                <span className="text-xs opacity-75">Комментарий</span>
                <input className="efhc-input" value={transfer.reason} onChange={(e) => {
                  setTransferConfirmed(false);
                  setTransferIdempotencyKey("");
                  setTransfer((prev) => ({ ...prev, reason: e.target.value }));
                }} />
              </label>
            </div>
            {transferPreview ? (
              <div className={`mt-3 rounded-xl border p-3 text-sm ${transferPreview.valid ? "border-[color:var(--tg-hint)]/15" : "border-red-400/40"}`}>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-[color:var(--tg-hint)]">Баланс до</span>
                  <strong>{formatD8ToHuman(transferPreview.before)} {transfer.balance === "bonus" ? "EFHCb" : "EFHCm"}</strong>
                </div>
                <div className="mt-1 flex items-center justify-between gap-3">
                  <span className="text-[color:var(--tg-hint)]">После операции</span>
                  <strong>{formatD8ToHuman(transferPreview.after)} {transfer.balance === "bonus" ? "EFHCb" : "EFHCm"}</strong>
                </div>
              </div>
            ) : null}
            <label className="mt-3 flex items-start gap-2 text-xs">
              <input
                type="checkbox"
                checked={transferConfirmed}
                onChange={(e) => {
                  const checked = e.target.checked;
                  setTransferConfirmed(checked);
                  setTransferIdempotencyKey(checked ? newIdempotencyKey() : "");
                }}
              />
              <span>Подтверждаю операцию для Global ID {selected.global_id}.</span>
            </label>
            <Button
              className="mt-3 w-full"
              disabled={busyAction !== "" || !canTransfer}
              onClick={() => void applyTransfer()}
            >
              {busyAction === "transfer"
                ? t("admin.working")
                : transfer.direction === "credit"
                  ? "Перевести"
                  : "Забрать"}
            </Button>
          </SectionCard>

          <SectionCard title="Активировать панель" eam="EAM-ADMIN-010">
            <div className="grid gap-2 rounded-xl border border-[color:var(--tg-hint)]/15 p-3">
              <div className="flex items-center justify-between gap-3">
                <span className="text-sm text-[color:var(--tg-hint)]">Стоимость</span>
                <strong>{formatD8ToHuman(PANEL_PRICE_EFHC)} EFHC</strong>
              </div>
              {panelPreview ? (
                <>
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-sm text-[color:var(--tg-hint)]">Баланс до</span>
                    <strong>{formatD8ToHuman(panelPreview.before)} EFHC</strong>
                  </div>
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-sm text-[color:var(--tg-hint)]">После активации</span>
                    <strong>{formatD8ToHuman(panelPreview.after)} EFHC</strong>
                  </div>
                </>
              ) : null}
            </div>
            <label className="mt-3 flex items-start gap-2 text-xs">
              <input
                type="checkbox"
                checked={panelConfirmed}
                onChange={(e) => {
                  const checked = e.target.checked;
                  setPanelConfirmed(checked);
                  setPanelIdempotencyKey(checked ? newIdempotencyKey() : "");
                }}
              />
              <span>Подтверждаю активацию панели для Global ID {selected.global_id}.</span>
            </label>
            <Button
              className="mt-3 w-full"
              disabled={busyAction !== "" || !panelConfirmed || !panelPreview?.valid}
              onClick={() => void activatePaidPanel()}
            >
              {busyAction === "panel" ? t("admin.working") : "Активировать панель"}
            </Button>
          </SectionCard>
        </section>
      ) : null}

      {selected && balances && activeTab === "history" ? (
        <SectionCard title="Баланс" eam="EAM-HISTORY-001">
            <ProfileHistorySection
              totalBalance={formatD8ToHuman(balances.total)}
              mainBalance={formatD8ToHuman(balances.main)}
              bonusBalance={formatD8ToHuman(balances.bonus)}
              items={historyWindow.visibleItems}
              loading={historyLoading}
              error={historyError}
              nextCursor={null}
              activeFilter={historyFilter}
              onFilterChange={setHistoryFilter}
              onRefresh={() => void loadHistory(selected.global_id)}
              onLoadMore={() => {
                if (historyCursor) void loadHistory(selected.global_id, historyCursor, true);
              }}
              reasonLabel={(reason) => balanceHistoryReasonLabel(reason, t)}
            />
            <AdminListExpandControl
              shown={historyWindow.visibleCount}
              total={historyWindow.totalCount}
              hasServerMore={Boolean(historyCursor)}
              loadingMore={historyLoading}
              onExpand={() => {
                if (historyWindow.hasMore) historyWindow.expand();
                else if (historyCursor) void loadHistory(selected.global_id, historyCursor, true);
              }}
              onCollapse={historyWindow.collapse}
            />
        </SectionCard>
      ) : null}

      {activeTab === "providers" ? (
        <SectionCard title="Провайдеры" eam="EAM-ADMIN-009">
          <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto]">
            <input
              className="efhc-input w-full"
              value={providerSubject}
              onChange={(e) => setProviderSubject(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && providerSubject.trim()) void resolveProviderUser();
              }}
              placeholder="Global ID, @username, TON или другой ID"
              autoComplete="off"
            />
            <Button
              variant="secondary"
              className="efhc-admin-user-search-button"
              disabled={!providerSubject.trim() || providerLoading}
              onClick={() => void resolveProviderUser()}
            >
              {providerLoading ? t("common.loading") : "Найти пользователя"}
            </Button>
          </div>
        </SectionCard>
      ) : null}

      {notice ? (
        <div
          className="fixed bottom-5 left-1/2 z-[120] w-[min(92vw,360px)] -translate-x-1/2 rounded-2xl border border-[color:var(--tg-button)]/35 bg-[color:var(--tg-secondary-bg)] px-4 py-3 text-center text-sm font-semibold shadow-2xl"
          role="status"
          aria-live="polite"
        >
          {notice}
        </div>
      ) : null}
    </div>
  );
}
