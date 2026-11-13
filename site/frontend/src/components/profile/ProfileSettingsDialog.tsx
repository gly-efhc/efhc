import React, { useContext } from "react";

import { useT } from "../../hooks/useT";
import type { UserSettings } from "../../lib/settings";
import { InterfaceCustomizationContext } from "../interface-settings/InterfaceCustomizationProvider";
import { Modal } from "../ui/Modal";

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
    </Modal>
  );
}
