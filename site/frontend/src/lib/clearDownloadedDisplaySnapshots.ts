import type { QueryClient } from "@tanstack/react-query";
import { clearAdminDisplaySnapshots } from "./adminReadCache";
import { clearPublicCatalogSnapshots } from "./publicCatalogPersistence";
import { clearUserDisplaySnapshots } from "./userDataCache";

/** Active-client commit step; peer clients must participate in their own clearing. */
export async function clearDownloadedDisplaySnapshots(client: QueryClient): Promise<void> {
  // Start every cleanup even when a storage domain refuses an operation.
  const clear = (cleanup: () => void | Promise<void>) => {
    try { return Promise.resolve(cleanup()); }
    catch (error) { return Promise.reject(error); }
  };
  const results = await Promise.allSettled([
    clear(() => clearUserDisplaySnapshots(client)),
    clear(() => clearPublicCatalogSnapshots(client)),
    clear(clearAdminDisplaySnapshots),
  ]);
  if (results.some(result => result.status === "rejected")) throw new Error("DISPLAY_SNAPSHOT_CLEAR_FAILED");
}
