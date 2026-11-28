/** Register real TEST API, never synthetic browser balances. */
import { registerTransport } from "../data/transport";
import { demoBackendTransport } from "./transport";
export function register(): void { registerTransport(demoBackendTransport); }
