import React from "react";
import type { UserSettings } from "../../lib/settings";
import { useAvatarPreference } from "../../queries/useAvatarPreference";
import { UnifiedAvatar } from "./UnifiedAvatar";

/** Unified server preference; legacy props retained for callers only. */
export function ProfileAvatarVisual(props: {
  settings: UserSettings;
  telegramAvatarUrl?: string | null;
  size?: number;
  alt?: string;
}) {
  const { avatar } = useAvatarPreference();
  return <UnifiedAvatar value={avatar} size={props.size ?? 28} alt={props.alt ?? ""} />;
}
