import {
  useAuthSessionController,
} from "../../auth/AuthSessionProvider";

export function useProviderState() {
  const { status, context } = useAuthSessionController();
  return {
    provider: context?.provider ?? null,
    authenticated: status === "authenticated" && context !== null,
  } as const;
}
