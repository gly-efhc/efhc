export type RuntimeProgressDetail = {
  channel: "shell" | "cache" | "faq" | "update";
  value: number;
  label?: string;
  complete?: boolean;
};

export const RUNTIME_PROGRESS_EVENT = "efhc-runtime-progress";

export function emitRuntimeProgress(
  detail: RuntimeProgressDetail,
): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(
    new CustomEvent<RuntimeProgressDetail>(
      RUNTIME_PROGRESS_EVENT,
      { detail },
    ),
  );
}
