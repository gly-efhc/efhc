import { useEffect } from "react";
import { useRouter } from "next/router";

// React stays mounted while an installed PWA is backgrounded or BFCache'd.
// Web Audio must be silent whenever the page is not visible.
let userGestureContext: AudioContext | null = null;

function audioContextConstructor(): (new () => AudioContext) | null {
  if (typeof window === "undefined") return null;
  const browser = window as Window & { webkitAudioContext?: new () => AudioContext };
  return window.AudioContext ?? browser.webkitAudioContext ?? null;
}

/** Called synchronously when the user turns music ON (autoplay unlock). */
export function primeBackgroundMusicFromGesture(): void {
  const Ctor = audioContextConstructor();
  if (!Ctor || document.visibilityState === "hidden") return;
  try {
    if (!userGestureContext || userGestureContext.state === "closed") {
      userGestureContext = new Ctor();
    }
    void userGestureContext.resume().catch(() => {});
  } catch { /* Unsupported/blocked device audio context. */ }
}

/** One OWNER-approved background composition, never played in the background. */
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
    let visible = document.visibilityState !== "hidden";
    let buffer: AudioBuffer | null = null;
    let source: AudioBufferSourceNode | null = null;
    let gain: GainNode | null = null;

    const stopPlayback = () => {
      // Silence synchronously; suspend() is asynchronous on Android.
      if (gain) gain.gain.value = 0;
      if (source) {
        try { source.stop(); } catch { /* Source already stopped. */ }
        source.disconnect();
        source = null;
      }
      if (gain) { gain.disconnect(); gain = null; }
      if (context.state !== "closed") void context.suspend().catch(() => {});
    };
    const startPlayback = () => {
      if (!active || !visible || !buffer || source || context.state === "closed") return;
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
    };
    const stopForHiddenPage = () => {
      visible = false;
      stopPlayback();
    };
    const onVisibilityChange = () => {
      if (document.visibilityState === "hidden") stopForHiddenPage();
      else { visible = true; startPlayback(); }
    };
    const onPageShow = () => {
      visible = document.visibilityState !== "hidden";
      if (visible) startPlayback();
    };
    const retryAfterGesture = () => {
      if (!active || !visible) return;
      startPlayback();
      if (context.state === "suspended") void context.resume().catch(() => {});
    };

    document.addEventListener("pointerdown", retryAfterGesture);
    document.addEventListener("keydown", retryAfterGesture);
    document.addEventListener("visibilitychange", onVisibilityChange);
    document.addEventListener("freeze", stopForHiddenPage);
    window.addEventListener("pagehide", stopForHiddenPage);
    window.addEventListener("pageshow", onPageShow);

    // A decode finishing after pagehide must not start background audio.
    void (async () => {
      try {
        const response = await fetch(`${basePath}/audio/background/1.mp3`, {
          signal: controller.signal,
        });
        if (!response.ok) throw new Error("background track unavailable");
        const bytes = await response.arrayBuffer();
        if (!active) return;
        buffer = await context.decodeAudioData(bytes);
        if (!active) return;
        startPlayback();
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
      document.removeEventListener("visibilitychange", onVisibilityChange);
      document.removeEventListener("freeze", stopForHiddenPage);
      window.removeEventListener("pagehide", stopForHiddenPage);
      window.removeEventListener("pageshow", onPageShow);
      stopPlayback();
      void context.close().catch(() => {});
    };
  }, [enabled, basePath]);
  return null;
}
