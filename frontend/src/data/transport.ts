/** Single stable API transport. Never silently downgrade a failed server to fixtures. */
import type { ApiRequestOptions, HttpMethod } from "../lib/api";

export interface ApiTransport {
  request<T>(path: string, method: HttpMethod, options: ApiRequestOptions): Promise<T>;
  requestRaw(path: string, method: HttpMethod, options: ApiRequestOptions): Promise<Response>;
}
let registered: ApiTransport | null = null;
let initialization: Promise<void> | null = null;

export function registerTransport(transport: ApiTransport): void {
  registered = transport;
}

async function resolveTransport(): Promise<ApiTransport> {
  if (registered) return registered;
  if (!initialization) {
    initialization = (async () => {
      const dataSource = process.env.NEXT_PUBLIC_EFHC_DATA_SOURCE || "production";
      if (dataSource === "demo_backend") {
        const demo = await import("../demo");
        demo.register();
      } else if (dataSource === "production") {
        const production = await import("./productionTransport");
        production.register();
      } else {
        throw new Error("EFHC_UNKNOWN_DATA_SOURCE");
      }
    })().catch(error => {
      initialization = null;
      throw error;
    });
  }
  await initialization;
  if (!registered) throw new Error("EFHC_API_TRANSPORT_NOT_REGISTERED");
  return registered;
}

export async function transportRequest<T>(
  path: string, method: HttpMethod, options: ApiRequestOptions = {},
): Promise<T> {
  return (await resolveTransport()).request<T>(path, method, options);
}

export async function transportRawRequest(
  path: string, method: HttpMethod, options: ApiRequestOptions = {},
): Promise<Response> {
  return (await resolveTransport()).requestRaw(path, method, options);
}
