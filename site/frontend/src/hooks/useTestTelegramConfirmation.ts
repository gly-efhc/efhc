import { useEffect, useRef } from "react";
import { useRouter } from "next/router";
import { useAuthSessionController } from "../auth/AuthSessionProvider";
import { isDemoBackendMode } from "../demo/session";
import { getAuthAuthorizationHeader, getAuthSessionRevision } from "../lib/auth-session";
import { runConfirmedOperation } from "../lib/confirmed-operation";
import { isTelegramConfirmationTest } from "../lib/telegram";

export function useTestTelegramConfirmation<T>(expectedOwner: string | null, state: T) {
  const router = useRouter();
  const auth = useAuthSessionController();
  const current = useRef({ state, auth });
  current.current = { state, auth };
  const navigation = useRef(0);
  const mounted = useRef(false);
  useEffect(() => {
    mounted.current = true;
    const invalidate = () => { navigation.current++; };
    router.events.on("routeChangeStart", invalidate);
    return () => {
      mounted.current = false;
      invalidate();
      router.events.off("routeChangeStart", invalidate);
    };
  }, [router.events]);

  return async (
    confirm: () => Promise<boolean>,
    eligible: (latest: T) => boolean,
    dispatch: (beforeSend?: () => boolean, sameActor?: () => boolean) => Promise<void>,
  ): Promise<void> => {
    if (!isTelegramConfirmationTest(isDemoBackendMode())) {
      if (await confirm()) await dispatch();
      return;
    }
    const owner = auth.status === "authenticated" ? auth.context?.global_id : undefined;
    const authorization = getAuthAuthorizationHeader();
    if (!owner || owner !== expectedOwner || !authorization) return;
    const revision = getAuthSessionRevision();
    const route = window.location.href;
    const routeRevision = navigation.current;
    const sameActor = () => mounted.current &&
      navigation.current === routeRevision && window.location.href === route &&
      current.current.auth.status === "authenticated" &&
      current.current.auth.context?.global_id === owner &&
      getAuthAuthorizationHeader() === authorization && getAuthSessionRevision() === revision;
    const isCurrent = () => sameActor() && eligible(current.current.state);
    await runConfirmedOperation(isCurrent, confirm, (beforeSend) => dispatch(beforeSend, sameActor));
  };
}
