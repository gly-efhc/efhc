/** Exact D8 percentage of the current energy level. No demo presentation offsets. */
export function levelProgressPct(
  generatedKwhScaled: bigint,
  levelStartScaled: bigint | null,
  levelEndScaled: bigint | null,
  level: number,
): number {
  if (level >= 12) return 100;
  if (
    levelStartScaled === null ||
    levelEndScaled === null ||
    levelEndScaled <= levelStartScaled
  ) return 0;

  const span = levelEndScaled - levelStartScaled;
  const fromStart = generatedKwhScaled - levelStartScaled;
  const bounded = fromStart < 0n ? 0n : fromStart > span ? span : fromStart;
  return Number((bounded * 100n) / span);
}
