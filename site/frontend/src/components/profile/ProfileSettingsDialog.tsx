import React, { useContext } from "react";

import { useT } from "../../hooks/useT";
import type { UserSettings } from "../../lib/settings";
import { appBasePath } from "../../lib/appBasePath";
import { InterfaceCustomizationContext } from "../interface-settings/InterfaceCustomizationProvider";
import { Modal } from "../ui/Modal";

/** Native SW update check; all HTTP cache eviction stays with Serwist.
 * Serwist has no standard API to manually erase only its runtime caches.
 * Do not pretend that register.update() is a cache-clearing operation.
 */
function PwaMaintenanceSection(): React.JSX.Element {
  const t = useT();
  const [checking, setChecking] = React.useState(false);
  const [outcome, setOutcome] = React.useState<
    "checked" | "pending" | "unavailable" | "failed" | null
  >(null);

  async function checkApplication(): Promise<void> {
    if (checking) return;
    if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) {
      setOutcome("unavailable");
      return;
    }
    setChecking(true);
    setOutcome(null);
    try {
      if (!navigator.onLine) throw new Error("offline");
      const registration = await navigator.serviceWorker.getRegistration(
        `${appBasePath() || ""}/`,
      );
      if (!registration) {
        setOutcome("unavailable");
        return;
      }
      await registration.update();
      setOutcome(registration.waiting || registration.installing
        ? "pending" : "checked");
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
            {t(checking ? "common.loading" : "pwa.update_now")}
          </button>
        </div>
        <small>{t("pwa.native_cache_managed")}</small>
        {outcome ? (
          <small role="status">
            {t(outcome === "checked" ? "pwa.checked"
              : outcome === "pending" ? "pwa.update_pending"
              : outcome === "unavailable" ? "pwa.unavailable"
              : "pwa.check_failed")}
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
