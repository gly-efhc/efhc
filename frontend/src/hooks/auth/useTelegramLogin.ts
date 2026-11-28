import {
  useAuthSessionController,
} from "../../auth/AuthSessionProvider";

export function useTelegramLogin() {
  const { loginTelegram, status } = useAuthSessionController();
  return {
    loginTelegram,
    pending: status === "authenticating",
  } as const;
}
