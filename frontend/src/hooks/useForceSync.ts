// Deprecated: Forced Sync is now achieved by calling
// /sync/user/{tg_id}?fresh=1 via useSnapshot.
// This hook is kept only to avoid broken imports in older pages.
export function useForceSync(): void {
  return;
}
