import {
  useAuthSessionController,
} from "../../auth/AuthSessionProvider";

export function useSessionRestore() {
  const {
    restoreSession,
    status,
    errorCode,
  } = useAuthSessionController();
  return {
    restoreSession,
    restoring: status === "restoring",
    errorCode,
  } as const;
}
