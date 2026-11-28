import {
  useAuthSessionController,
} from "../../auth/AuthSessionProvider";

export function useAuthState() {
  const { status, context, errorCode } = useAuthSessionController();
  return {
    status,
    context,
    globalId: context?.global_id ?? null,
    roles: context?.roles ?? [],
    authenticated: status === "authenticated" && context !== null,
    errorCode,
  } as const;
}
