// UI sound effects (no external audio files): uses WebAudio
// oscillators.
// Invariants:
// - Must be safe to call in Telegram WebApp.
// - Must not throw when AudioContext is unavailable.

export type SfxKind = "tap" | "success" | "error" | "nav";

let ctx: AudioContext | null = null;

function getCtx(): AudioContext | null {
  if (typeof window === "undefined") return null;
  try {
    if (!ctx) {
      const AC = (
        window.AudioContext ||
        (window as any).webkitAudioContext
      ) as any;
      if (!AC) return null;
      ctx = new AC();
    }
    return ctx;
  } catch {
    return null;
  }
}

function beep(
  freq: number, durMs: number, volume: number, type: OscillatorType,
) {
  const c = getCtx();
  if (!c) return;
  try {
    const o = c.createOscillator();
    const g = c.createGain();
    o.type = type;
    o.frequency.value = freq;
    g.gain.value = Math.max(0, Math.min(1, volume)) * 0.08;
    o.connect(g);
    g.connect(c.destination);
    const now = c.currentTime;
    o.start(now);
    o.stop(now + durMs / 1000);
  } catch {
    // ignore
  }
}

export function playSfx(
  kind: SfxKind, enabled: boolean, volume: number,
) {
  if (!enabled) return;
  // Some environments require user gesture to unlock; calling is safe.
  if (kind === "tap") beep(520, 30, volume, "square");
  if (kind === "nav") beep(420, 45, volume, "sine");
  if (kind === "success") {
    beep(660, 45, volume, "triangle");
    setTimeout(() => beep(880, 60, volume, "triangle"), 55);
  }
  if (kind === "error") {
    beep(220, 80, volume, "sawtooth");
  }
}
