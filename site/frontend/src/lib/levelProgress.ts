/**
 * Energy-level completion is a presentation of confirmed D8 lifetime energy.
 * Values are atomic kWh units (bigint); no demo presentation adjustments.
 */
export function levelProgressPct(
  energy: bigint,
  start: bigint,
  end: bigint | null,
  level: number,
): number {
  if (level >= 12) return 100;
  if (end === null || end <= start) return 0;
  if (energy <= start) return 0;
  if (energy >= end) return 100;
  return Number(((energy - start) * 100n) / (end - start));
}
