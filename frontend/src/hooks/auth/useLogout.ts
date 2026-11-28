import {
  useAuthSessionController,
} from "../../auth/AuthSessionProvider";

export function useLogout() {
  const { logout, status } = useAuthSessionController();
  return {
    logout,
    pending: status === "authenticating",
  } as const;
}
