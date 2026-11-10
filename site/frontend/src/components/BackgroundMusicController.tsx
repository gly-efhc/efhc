import { useEffect } from "react";
import { useRouter } from "next/router";

// The entire 58-second track is decoded once and repeated in the Web Audio
// rendering thread. An HTMLMediaElement loop can pause at an MP3 boundary.
let userGestureContext: AudioContext | null = null;

function audioContextConstructor(): (new () => AudioContext) | null {
  if (typeof window === "undefined") return null;
  const browser = window as Window & { webkitAudioContext?: new () => AudioContext };
  return window.AudioContext ?? browser.webkitAudioContext ?? null;
}

/** Called synchronously from the user turning music ON (autoplay unlock). */
export function primeBackgroundMusicFromGesture(): void {
  const Ctor = audioContextConstructor();
  if (!Ctor) return;
  try {
    if (!userGestureContext || userGestureContext.state === "closed") {
      userGestureContext = new Ctor();
    }
    void userGestureContext.resume().catch(() => {});
  } catch { /* Unsupported/blocked device audio context. */ }
}

/** One OWNER-approved background composition with a user-controlled gapless loop. */
export function BackgroundMusicController({ enabled }: { enabled: boolean }) {
  const { basePath } = useRouter();
  useEffect(() => {
    if (!enabled || typeof window === "undefined") return;
    const Ctor = audioContextConstructor();
    if (!Ctor) return;
    const controller = new AbortController();
    const context = userGestureContext ?? new Ctor();
    if (userGestureContext === context) userGestureContext = null;
    let active = true;
    let source: AudioBufferSourceNode | null = null;
    let gain: GainNode | null = null;

    const retryAfterGesture = () => {
      if (active && context.state === "suspended") {
        void context.resume().catch(() => {});
      }
    };
    document.addEventListener("pointerdown", retryAfterGesture);
    document.addEventListener("keydown", retryAfterGesture);

    // No MP3 request or decode ever occurs while disabled.
    void (async () => {
      try {
        const response = await fetch(`${basePath}/audio/background/1.mp3`, {
          signal: controller.signal,
        });
        if (!response.ok) throw new Error("background track unavailable");
        const bytes = await response.arrayBuffer();
        if (!active) return;
        const buffer = await context.decodeAudioData(bytes);
        if (!active) return;
        gain = context.createGain();
        gain.gain.value = 0.4;
        gain.connect(context.destination);
        source = context.createBufferSource();
        source.buffer = buffer;
        source.loop = true;
        source.loopStart = 0;
        source.loopEnd = buffer.duration;
        source.connect(gain);
        source.start();
        void context.resume().catch(() => {});
      } catch (error) {
        if (active && !controller.signal.aborted) {
          console.warn("EFHC background audio unavailable", error);
        }
      }
    })();
    return () => {
      active = false;
      controller.abort();
      document.removeEventListener("pointerdown", retryAfterGesture);
      document.removeEventListener("keydown", retryAfterGesture);
      if (source) {
        try { source.stop(); } catch { /* Source already stopped. */ }
        source.disconnect();
        source = null;
      }
      if (gain) { gain.disconnect(); gain = null; }
      void context.close().catch(() => {});
    };
  }, [enabled, basePath]);
  return null;
}
