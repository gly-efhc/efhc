import type { AdProviderClientAdapter, ProviderShowResult } from "../types";

type Creative = {
  video?: string;
  notification_url?: string;
  link?: string;
};

export const richadsClientAdapter: AdProviderClientAdapter = {
  code: "richads",
  async show(publicConfig): Promise<ProviderShowResult> {
    const creative = (publicConfig.creative || {}) as Creative;
    const videoUrl = String(creative.video || "").trim();
    if (!videoUrl || typeof document === "undefined") {
      return { completed: false, noFill: true };
    }
    return await new Promise<ProviderShowResult>((resolve, reject) => {
      const overlay = document.createElement("div");
      overlay.setAttribute("data-efhc-provider-ad", "richads");
      overlay.style.cssText = "position:fixed;inset:0;z-index:2147483646;background:#000;display:flex;align-items:center;justify-content:center;";
      const video = document.createElement("video");
      video.src = videoUrl;
      video.controls = true;
      video.autoplay = true;
      video.playsInline = true;
      video.style.cssText = "max-width:100%;max-height:100%;";
      overlay.appendChild(video);
      document.body.appendChild(overlay);
      const cleanup = (): void => overlay.remove();
      video.addEventListener("playing", () => {
        const notificationUrl = String(creative.notification_url || "").trim();
        if (notificationUrl) void fetch(notificationUrl, { mode: "no-cors", keepalive: true }).catch(() => undefined);
      }, { once: true });
      video.addEventListener("ended", () => {
        cleanup();
        resolve({ completed: true, shown: true, payload: { shown: true, completed: true } });
      }, { once: true });
      video.addEventListener("error", () => {
        cleanup();
        reject(new Error("PROVIDER_ERROR"));
      }, { once: true });
    });
  },
};
