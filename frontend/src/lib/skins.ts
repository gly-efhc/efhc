import {appBasePath} from "./appBasePath";
export function getShopSkinBgUrl(
  active_skin_id: number,
): string | null {
  if (!active_skin_id || active_skin_id <= 0) return null;
  const base = appBasePath();
  return `${base}/skins/${active_skin_id}.webp`;
}

// ------------------------------------------------------------------
// Internal Energy skin thresholds. They are earned by total generation
// and must not be rendered as a public level ladder in Ranks.
// ------------------------------------------------------------------

export type UserLevelSkin = {
  level: number;
  name: string;
  min_kwh: number;
  accent_1: string;
  accent_2: string;
  energy: string;
};

export const USER_LEVEL_SKINS: UserLevelSkin[] = [
  {
    level: 1,
    name: "Eco Initiate",
    min_kwh: 0,
    accent_1: "#f4d27a",
    accent_2: "#e8c15f",
    energy: "#ff8a1f",
  },
  {
    level: 2,
    name: "Hope Bringer",
    min_kwh: 100,
    accent_1: "#a8ffd6",
    accent_2: "#5eead4",
    energy: "#34d399",
  },
  {
    level: 3,
    name: "Energy Seeker",
    min_kwh: 300,
    accent_1: "#93c5fd",
    accent_2: "#60a5fa",
    energy: "#3b82f6",
  },
  {
    level: 4,
    name: "Nature's Voice",
    min_kwh: 600,
    accent_1: "#c4b5fd",
    accent_2: "#a78bfa",
    energy: "#8b5cf6",
  },
  {
    level: 5,
    name: "Earth Ally",
    min_kwh: 1000,
    accent_1: "#fca5a5",
    accent_2: "#fb7185",
    energy: "#f43f5e",
  },
  {
    level: 6,
    name: "Climate Fighter",
    min_kwh: 2000,
    accent_1: "#fdba74",
    accent_2: "#fb923c",
    energy: "#f97316",
  },
  {
    level: 7,
    name: "Green Sentinel",
    min_kwh: 3500,
    accent_1: "#86efac",
    accent_2: "#22c55e",
    energy: "#16a34a",
  },
  {
    level: 8,
    name: "Planet Defender",
    min_kwh: 5000,
    accent_1: "#67e8f9",
    accent_2: "#22d3ee",
    energy: "#06b6d4",
  },
  {
    level: 9,
    name: "Eco Champion",
    min_kwh: 7500,
    accent_1: "#fef08a",
    accent_2: "#facc15",
    energy: "#eab308",
  },
  {
    level: 10,
    name: "Planet Saver",
    min_kwh: 10_000,
    accent_1: "#d8b4fe",
    accent_2: "#c084fc",
    energy: "#a855f7",
  },
  {
    level: 11,
    name: "Green Commander",
    min_kwh: 15_000,
    accent_1: "#c7d2fe",
    accent_2: "#818cf8",
    energy: "#6366f1",
  },
  {
    level: 12,
    name: "Guardian of Earth",
    min_kwh: 20_000,
    accent_1: "#fcd34d",
    accent_2: "#f59e0b",
    energy: "#d97706",
  },
];

export function parseKwh(v: string | null | undefined): number {
  if (!v) return 0;
  const n = Number(String(v).replace(/,/g, "."));
  if (!Number.isFinite(n)) return 0;
  return n;
}

export function getUserLevel(total_generated_kwh: string): number {
  const kwh = parseKwh(total_generated_kwh);
  let best = 1;
  for (const s of USER_LEVEL_SKINS) {
    if (kwh >= s.min_kwh) best = s.level;
  }
  return best;
}

export function getUserSkin(level: number): UserLevelSkin {
  const idx = Math.min(Math.max(level, 1), 12) - 1;
  return USER_LEVEL_SKINS[idx];
}

export function getSkinKey(level: number): string {
  const n = String(Math.min(Math.max(level, 1), 12)).padStart(2, "0");
  return `lvl${n}`;
}

/* canonical user-facing progression theme layer */
