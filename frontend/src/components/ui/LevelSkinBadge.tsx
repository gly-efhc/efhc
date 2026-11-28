import React from "react";
import {
  getUserLevel,
  getUserSkin,
} from "../../lib/skins";

export function LevelSkinBadge(
  props: {
    total_generated_kwh: string | null | undefined;
    compact?: boolean;
  },
) {
  const total = props.total_generated_kwh || "0";
  const level = getUserLevel(total);
  const skin = getUserSkin(level);
  const pad = props.compact ? "px-2 py-1" : "px-3 py-1";
  const cls =
    "inline-flex items-center text-xs font-semibold " +
    "efhc-level-badge " +
    pad;

  return (
    <span
      className={cls}
      title={`${skin.name} (L${skin.level})`}
    >
      <span className="mr-1">L{skin.level}</span>
      <span>{skin.name}</span>
    </span>
  );
}
