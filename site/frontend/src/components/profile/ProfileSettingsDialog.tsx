import React, { useContext } from "react";

import { useT } from "../../hooks/useT";
import type { UserSettings } from "../../lib/settings";
import { appBasePath } from "../../lib/appBasePath";
import { InterfaceCustomizationContext } from "../interface-settings/InterfaceCustomizationProvider";
import { Modal } from "../ui/Modal";

type CacheSnapshot = {
  buildId: string;
  entries: number;
  bytes: number;
  missing: number;
};

type MaintenanceOutcome =
  | "up_to_date"
  | "update_pending"
  | "checked_failed"
  | "unavailable"
  | "clear_complete"
  | "clear_empty"
  | "clear_partial"
  | "clear_other_tabs"
  | "clear_update_required"
  | "clear_offline"
  | "clear_failed";

async function requestWorkerMessage(
  worker: ServiceWorker,
  type: string,
  expectedType: string,
): Promise<Record<string, unknown>> {
  return new Promise((resolve, reject) => {
    const channel = new MessageChannel();
    let settled = false;
    let timeout = 0;
    const finish = (value?: Record<string, unknown>, error?: Error) => {
      if (settled) return;
      settled = true;
      window.clearTimeout(timeout);
      channel.port1.close();
      channel.port2.close();
      if (error) reject(error);
      else resolve(value || {});
    };
    channel.port1.onmessage = event => {
      const data = event.data as Record<string, unknown> | null;
      if (data?.type === expectedType) finish(data);
    };
    timeout = window.setTimeout(
      () => finish(undefined, new Error("PWA maintenance timed out")), 10000,
    );
    try {
      worker.postMessage({type}, [channel.port2]);
    } catch (error) {
      finish(undefined, error instanceof Error ? error : new Error("PWA message failed"));
    }
  });
}

function PwaMaintenanceSection(): React.JSX.Element {
  const t = useT();
  const [busy, setBusy] = React.useState<"update" | "clear" | null>(null);
  const [snapshot, setSnapshot] = React.useState<CacheSnapshot | null>(null);
  const [outcome, setOutcome] = React.useState<MaintenanceOutcome | null>(null);
  const [removed, setRemoved] = React.useState(0);
  const [failed, setFailed] = React.useState(0);

  async function registrationAndWorker(): Promise<{
    registration: ServiceWorkerRegistration;
    worker: ServiceWorker;
  } | null> {
    if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) return null;
    const registration = await navigator.serviceWorker.getRegistration(`${appBasePath() || ""}/`);
    const worker = registration?.active || navigator.serviceWorker.controller;
    return registration && worker ? {registration, worker} : null;
  }

  async function checkApplication(): Promise<void> {
    if (busy) return;
    setBusy("update");
    setOutcome(null);
    try {
      if (!navigator.onLine) {
        setOutcome("checked_failed");
        return;
      }
      const current = await registrationAndWorker();
      if (!current) {
        setOutcome("unavailable");
        return;
      }
      // A successful update() only checks for an installation; it does not
      // prove that the installed React document is already the new version.
      await current.registration.update();
      const report = await requestWorkerMessage(
        current.registration.active || current.worker, "GET_CACHE_STATUS", "CACHE_STATUS",
      );
      const nextSnapshot = {
        buildId: String(report.buildId || ""),
        entries: Math.max(0, Number(report.staticEntries || 0) + Number(report.contentEntries || 0)),
        bytes: Math.max(0, Number(report.staticBytes || 0) + Number(report.contentBytes || 0)),
        missing: Math.max(0, Number(report.precacheMissing || 0)),
      };
      setSnapshot(nextSnapshot);
      const response = await fetch(`${appBasePath()}/pwa-build.json`, {cache: "no-store"});
      if (!response.ok) throw new Error("PWA build manifest unavailable");
      const published = await response.json() as {build_id?: string};
      if (!published.build_id || !nextSnapshot.buildId) throw new Error("PWA build unknown");
      setOutcome(published.build_id === nextSnapshot.buildId &&
        !current.registration.waiting && !current.registration.installing
        ? "up_to_date" : "update_pending");
    } catch {
      setOutcome("checked_failed");
    } finally {
      setBusy(null);
    }
  }

  async function clearApplicationCache(): Promise<void> {
    if (busy) return;
    setBusy("clear");
    setOutcome(null);
    setRemoved(0);
    setFailed(0);
    try {
      if (!navigator.onLine) {
        setOutcome("clear_offline");
        return;
      }
      const current = await registrationAndWorker();
      if (!current) {
        setOutcome("unavailable");
        return;
      }
      // A private MessageChannel response confirms this specific request,
      // rather than mistaking another tab's CACHE_STATUS broadcast for success.
      const result = await requestWorkerMessage(
        current.registration.active || current.worker,
        "CLEAN_STALE_PUBLIC_CACHE", "PUBLIC_CACHE_CLEAN_RESULT",
      );
      const removedCount = Math.max(0, Number(result.removed || 0));
      setRemoved(removedCount);
      setFailed(Math.max(0, Number(result.failed || 0)));
      switch (result.status) {
        case "complete": setOutcome(removedCount ? "clear_complete" : "clear_empty"); break;
        case "partial": setOutcome("clear_partial"); break;
        case "other_tabs": setOutcome("clear_other_tabs"); break;
        case "update_required": setOutcome("clear_update_required"); break;
        case "offline": setOutcome("clear_offline"); break;
        default: setOutcome("clear_failed");
      }
    } catch {
      setOutcome("clear_failed");
    } finally {
      setBusy(null);
    }
  }

  const outcomeLabel: Record<MaintenanceOutcome, string> = {
    up_to_date: "pwa.up_to_date",
    update_pending: "pwa.update_pending",
    checked_failed: "pwa.check_failed",
    unavailable: "pwa.unavailable",
    clear_complete: "pwa.clear_removed",
    clear_empty: "pwa.clear_empty",
    clear_partial: "pwa.clear_partial",
    clear_other_tabs: "pwa.clear_other_tabs",
    clear_update_required: "pwa.clear_update_required",
    clear_offline: "pwa.clear_offline",
    clear_failed: "pwa.clear_failed",
  };

  return (
    <details className="efhc-profile-pwa-maintenance">
      <summary>{t("pwa.maintenance_title")}</summary>
      <div className="efhc-profile-source-settings">
        <div className="standalone-settings-row">
          <span>{t("pwa.update_action")}</span>
          <button type="button"
            className="source-button secondary standalone-setting-toggle"
            disabled={busy !== null}
            onClick={() => void checkApplication()}>
            {t(busy === "update" ? "common.loading" : "pwa.update_now")}
          </button>
        </div>
        <div className="standalone-settings-row">
          <span>{t("pwa.clear_action")}</span>
          <button type="button"
            className="source-button secondary standalone-setting-toggle"
            disabled={busy !== null}
            onClick={() => void clearApplicationCache()}>
            {t(busy === "clear" ? "common.loading" : "pwa.clear_now")}
          </button>
        </div>
        {snapshot ? (
          <div aria-live="polite">
            <small>{t("pwa.build")}: {snapshot.buildId}</small>
            <small style={{display: "block"}}>
              {t("pwa.cached_files")}: {snapshot.entries} · {(snapshot.bytes / (1024 * 1024)).toFixed(1)} MB
            </small>
            <small style={{display: "block"}}>
              {t("pwa.missing_files")}: {snapshot.missing}
            </small>
          </div>
        ) : null}
        {outcome ? (
          <small role="status">
            {t(outcomeLabel[outcome])}
            {outcome === "clear_complete" || outcome === "clear_partial" ? ` ${removed}` : ""}
            {outcome === "clear_partial" ? ` · ${t("pwa.clear_failed_entries")}: ${failed}` : ""}
          </small>
        ) : null}
      </div>
    </details>
  );
}

type SettingName = "reduce_motion" | "sfx_enabled" | "haptics_enabled" | "music_enabled";

const SETTINGS: ReadonlyArray<Readonly<{ key: SettingName; title: string }>> = [
  { key: "reduce_motion", title: "profile.reduce_motion" },
  { key: "sfx_enabled", title: "profile.ui_sounds" },
  { key: "haptics_enabled", title: "profile.haptic_feedback" },
  { key: "music_enabled", title: "profile.background_music" },
];

/** Compact four-setting overlay from the physical account reference.
 *  The canonical settings store still persists the values for every device.
 */
export function ProfileSettingsDialog(props: {
  open: boolean;
  onClose: () => void;
  settings: UserSettings;
  setSettings: (next: UserSettings) => void;
}): React.JSX.Element {
  const t = useT();
  const { colorThemeId } = useContext(InterfaceCustomizationContext);

  return (
    <Modal
      open={props.open}
      onClose={props.onClose}
      title={t("profile.settings_title")}
      referenceLayout="settings"
      portalColorThemeId={colorThemeId}
    >
      <div className="efhc-profile-source-settings" data-profile-settings-compact="four">
        {SETTINGS.map(({ key, title }) => {
          const active = props.settings[key];
          return (
            <div className="standalone-settings-row" key={key} data-setting-row={key}>
              <span>{t(title)}</span>
              <button
                type="button"
                className={active ? "source-button standalone-setting-toggle" : "source-button secondary standalone-setting-toggle"}
                data-setting={key}
                data-active={active ? "true" : "false"}
                aria-pressed={active}
                onClick={() => props.setSettings({ ...props.settings, [key]: !active })}
              >
                {t(active ? "common.on" : "common.off")}
              </button>
            </div>
          );
        })}
      </div>
      <PwaMaintenanceSection />
    </Modal>
  );
}
