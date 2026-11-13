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

function PwaMaintenanceSection(): React.JSX.Element {
  const t = useT();
  const [checking, setChecking] = React.useState(false);
  const [snapshot, setSnapshot] = React.useState<CacheSnapshot | null>(null);
  const [outcome, setOutcome] = React.useState<"checked" | "unavailable" | "failed" | null>(null);

  async function checkApplication(): Promise<void> {
    if (checking) return;
    if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) {
      setOutcome("unavailable");
      return;
    }
    setChecking(true);
    setOutcome(null);
    try {
      const registration = await navigator.serviceWorker.getRegistration(`${appBasePath() || ""}/`);
      if (!registration) {
        setOutcome("unavailable");
        return;
      }
      let updateFailed = false;
      try {
        await registration.update();
      } catch {
        updateFailed = true;
      }
      const worker = registration.active || navigator.serviceWorker.controller;
      if (!worker) {
        setOutcome("unavailable");
        return;
      }
      const result = await new Promise<CacheSnapshot>((resolve, reject) => {
        let timer = 0;
        const receive = (event: MessageEvent) => {
          const data = event.data;
          if (data?.type !== "CACHE_STATUS") return;
          finish();
          resolve({
            buildId: String(data.buildId || ""),
            entries: Math.max(0, Number(data.staticEntries || 0) + Number(data.contentEntries || 0)),
            bytes: Math.max(0, Number(data.staticBytes || 0) + Number(data.contentBytes || 0)),
            missing: Math.max(0, Number(data.precacheMissing || 0)),
          });
        };
        const finish = () => {
          window.clearTimeout(timer);
          navigator.serviceWorker.removeEventListener("message", receive);
        };
        navigator.serviceWorker.addEventListener("message", receive);
        timer = window.setTimeout(() => {
          finish();
          reject(new Error("PWA status timed out"));
        }, 9000);
        try {
          worker.postMessage({ type: "GET_CACHE_STATUS" });
        } catch (error) {
          finish();
          reject(error);
        }
      });
      setSnapshot(result);
      setOutcome(updateFailed ? "failed" : "checked");
    } catch {
      setOutcome("failed");
    } finally {
      setChecking(false);
    }
  }

  return (
    <details className="efhc-profile-pwa-maintenance">
      <summary>{t("pwa.maintenance_title")}</summary>
      <div className="efhc-profile-source-settings">
        <div className="standalone-settings-row">
          <span>{t("pwa.check_now")}</span>
          <button
            type="button"
            className="source-button secondary standalone-setting-toggle"
            disabled={checking}
            onClick={() => void checkApplication()}
          >
            {t(checking ? "common.loading" : "common.refresh")}
          </button>
        </div>
        {snapshot ? (
          <div aria-live="polite">
            <small>{t("pwa.build")}: {snapshot.buildId}</small>
            <small style={{ display: "block" }}>
              {t("pwa.cached_files")}: {snapshot.entries} · {(snapshot.bytes / (1024 * 1024)).toFixed(1)} MB
            </small>
            <small style={{ display: "block" }}>
              {t("pwa.missing_files")}: {snapshot.missing}
            </small>
          </div>
        ) : null}
        {outcome ? (
          <small role="status">
            {t(outcome === "checked" ? "pwa.checked" : outcome === "unavailable" ? "pwa.unavailable" : "pwa.check_failed")}
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
