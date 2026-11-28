/** A stalled TEST API must finish as an operation error, never stall the UI. */
export async function demoFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const controller = new AbortController();
  const abort = () => controller.abort(options.signal?.reason);
  options.signal?.addEventListener("abort", abort, { once: true });
  if (options.signal?.aborted) abort();
  const timer = setTimeout(() => {
    controller.abort(Object.assign(new Error("DEMO_API_TIMEOUT"), { name: "TimeoutError" }));
  }, 15_000);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timer);
    options.signal?.removeEventListener("abort", abort);
  }
}
