import {
  useAuthSessionController,
} from "../../auth/AuthSessionProvider";

export function useTonLogin() {
  const { loginTon, status } = useAuthSessionController();
  return {
    loginTon,
    pending: status === "authenticating",
  } as const;
}
