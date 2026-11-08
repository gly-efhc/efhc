import React, {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useQueryClient } from "@tanstack/react-query";

import {
  clearAuthSession,
  getAuthAuthorizationHeader,
  readAuthSession,
  subscribeAuthSessionInvalidation,
  type AuthSessionContext,
} from "../lib/auth-session";
import {
  fetchAuthSessionContext,
  revokeAuthSession,
} from "../lib/auth-session-client";
import { completeTelegramSessionLogin } from "../lib/telegram-auth";
import { getTelegramInitData } from "../lib/telegram";
import { completeTonProofLogin } from "../lib/ton-auth";
import {
  captureReferralStartParamFromFirstEntry,
} from "../lib/referral-start-param";
import {beginDisplayOwnerResolution,needsTelegramOwnerResolution,resolvedDisplayOwner,subscribeDisplayOwner} from "../lib/displayOwner";
import { clearDemoSession, isDemoBackendMode, isDemoGuestSession, loginDemoGuest as issueDemoGuest, loginDemo as issueDemoLogin, selectDemoGlobalId as issueDemoSelection, logoutDemo as revokeDemoLogin } from "../demo/session";

export type AuthBootstrapStatus =
  | "anonymous"
  | "restoring"
  | "authenticated"
  | "authenticating"
  | "error";

export type ProviderState = Readonly<{
  provider: string | null;
  authenticated: boolean;
}>;

export type AuthState = Readonly<{
  status: AuthBootstrapStatus;
  context: AuthSessionContext | null;
  errorCode: string | null;
}>;

type AuthSessionController = AuthState & {
  restoreSession: () => Promise<AuthSessionContext | null>;
  logout: () => Promise<void>;
  loginTelegram: () => Promise<AuthSessionContext>;
  loginTon: (proofRequest: unknown) => Promise<AuthSessionContext>;
  loginDemo: (password: string) => Promise<AuthSessionContext>;
  selectDemoGlobalId: (globalId: string) => Promise<AuthSessionContext>;
};

const AuthSessionStore =
  createContext<AuthSessionController | null>(null);

function initialAuthState(): AuthState {
  return readAuthSession() || isDemoBackendMode()
    ? { status: "restoring", context: null, errorCode: null }
    : { status: "anonymous", context: null, errorCode: null };
}

function errorCode(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return "AUTH_SESSION_BOOTSTRAP_FAILED";
}

export function AuthSessionProvider(props: {
  children: ReactNode;
}): React.JSX.Element {
  const [state, setState] = useState<AuthState>(initialAuthState);
  const queryClient = useQueryClient();
  const telegramBootstrapStarted = useRef(false);
  const guestBootstrapStarted = useRef(false);

  useEffect(() => {
    captureReferralStartParamFromFirstEntry();
  }, []);

  const restoreSession = useCallback(async () => {
    const authorization = getAuthAuthorizationHeader();
    if (!readAuthSession() && !isDemoBackendMode()) {
      setState({
        status: "anonymous",
        context: null,
        errorCode: null,
      });
      return null;
    }
    setState((current) => ({
      status: "restoring",
      context: current.context,
      errorCode: null,
    }));
    try {
      const context = await fetchAuthSessionContext();
      setState({
        status: "authenticated",
        context,
        errorCode: null,
      });
      return context;
    } catch (error) {
      if (errorCode(error) === "AUTH_SESSION_REPLACED" ||
          (getAuthAuthorizationHeader() && getAuthAuthorizationHeader() !== authorization)) return null;
      if (!readAuthSession() && isDemoBackendMode()) {
        setState({ status: "anonymous", context: null, errorCode: null });
        return null;
      }
      if (!readAuthSession()) {
        setState({
          status: "anonymous",
          context: null,
          errorCode: null,
        });
        return null;
      }
      setState({
        status: "error",
        context: null,
        errorCode: errorCode(error),
      });
      return null;
    }
  }, []);


  useEffect(() => subscribeAuthSessionInvalidation(() => {
    guestBootstrapStarted.current = false;
    setState({
      status: "anonymous",
      context: null,
      errorCode: null,
    });
  }), []);

  const loginTelegram = useCallback(async () => {
    const initData = getTelegramInitData();
    if (!initData) {
      throw new Error("TELEGRAM_INIT_DATA_UNAVAILABLE");
    }
    beginDisplayOwnerResolution();
    setState((current) => ({
      status: "authenticating",
      context: current.context,
      errorCode: null,
    }));
    try {
      await completeTelegramSessionLogin(initData);
      clearDemoSession(); // Signed Telegram identity supersedes any guest/operator scope hint.
      const context = await fetchAuthSessionContext();
      setState({
        status: "authenticated",
        context,
        errorCode: null,
      });
      return context;
    } catch (error) {
      setState({
        status: readAuthSession() ? "error" : "anonymous",
        context: null,
        errorCode: errorCode(error),
      });
      throw error;
    }
  }, []);

  useEffect(() => {
    const credential = readAuthSession();
    const signedTelegramData = getTelegramInitData();
    if (isDemoBackendMode() && signedTelegramData && (!credential || isDemoGuestSession())) {
      // Real Telegram Mini App proof takes precedence over a public DEMO guest.
      void loginTelegram().catch(() => undefined);
    } else if (credential || isDemoBackendMode()) {
      if (!isDemoBackendMode() && signedTelegramData && needsTelegramOwnerResolution()) {
        void loginTelegram().catch(() => undefined);
      } else {
        void restoreSession();
      }
    }
  }, [restoreSession, loginTelegram]);

  useEffect(() => {
    if (
      state.status !== "anonymous"
      || readAuthSession()
      || telegramBootstrapStarted.current
    ) {
      return;
    }
    if (!getTelegramInitData()) return;
    telegramBootstrapStarted.current = true;
    void loginTelegram().catch(() => undefined);
  }, [loginTelegram, state.status]);

  useEffect(() => {
    if (!isDemoBackendMode() || state.status !== "anonymous" ||
        readAuthSession() || getTelegramInitData() || guestBootstrapStarted.current) return;
    guestBootstrapStarted.current = true;
    setState({status: "authenticating", context: null, errorCode: null});
    void (async () => {
      await issueDemoGuest();
      const context = await fetchAuthSessionContext();
      setState({status: "authenticated", context, errorCode: null});
    })().catch((error) => {
      guestBootstrapStarted.current = false;
      if (errorCode(error) === "DEMO_SESSION_REPLACED" || errorCode(error) === "AUTH_SESSION_REPLACED") return;
      // A temporary context/read failure does not revoke a server-issued session.
      // Actual 401 invalidation is scoped to the credential used by transport.
      setState({status: "error", context: null, errorCode: errorCode(error)});
    });
  }, [state.status]);

  const loginTon = useCallback(async (proofRequest: unknown) => {
    beginDisplayOwnerResolution(true);
    setState((current) => ({
      status: "authenticating",
      context: current.context,
      errorCode: null,
    }));
    try {
      await completeTonProofLogin(proofRequest);
      clearDemoSession(); // Verified TON Proof supersedes guest/operator session hints.
      const context = await fetchAuthSessionContext();
      setState({
        status: "authenticated",
        context,
        errorCode: null,
      });
      return context;
    } catch (error) {
      setState({
        status: readAuthSession() ? "error" : "anonymous",
        context: null,
        errorCode: errorCode(error),
      });
      throw error;
    }
  }, []);

  const stateRef=useRef(state);stateRef.current=state;
  useEffect(() => {
    if (state.status !== "authenticated") return;
    let active = true;
    // Reads started while restoring a cached owner may have used an expired
    // credential. Refresh after server proof is ready, without replaying writes.
    void queryClient.cancelQueries({type: "active"}).then(async () => {
      if (!active) return;
      window.dispatchEvent(new Event("efhc:activity-sync"));
      await queryClient.refetchQueries({type: "active"});
    });
    return () => { active = false; };
  }, [state.status, state.context, queryClient]);
  useEffect(()=>{
    const activity=()=>{
      const status=stateRef.current.status;
      if(status==="restoring"||status==="authenticating"||status==="authenticated")return;
      if(getTelegramInitData()&&needsTelegramOwnerResolution())void loginTelegram().catch(()=>undefined);
      else if(readAuthSession()||isDemoBackendMode())void restoreSession();
    };
    window.addEventListener("efhc:activity-sync",activity);
    return()=>window.removeEventListener("efhc:activity-sync",activity);
  },[loginTelegram,restoreSession]);

  const loginDemo = useCallback(async (password: string): Promise<AuthSessionContext> => {
    if (!isDemoBackendMode()) throw new Error("DEMO_BACKEND_DISABLED");
    await issueDemoLogin(password);
    const context = await fetchAuthSessionContext();
    setState({ status: "authenticated", context, errorCode: null });
    return context;
  }, []);

  const selectDemoGlobalId = useCallback(async (globalId: string): Promise<AuthSessionContext> => {
    if (!isDemoBackendMode()) throw new Error("DEMO_BACKEND_DISABLED");
    // The backend validates owner existence and issues a new session token.
    await issueDemoSelection(globalId);
    const context = await fetchAuthSessionContext();
    setState({ status: "authenticated", context, errorCode: null });
    if (typeof window !== "undefined") window.dispatchEvent(new Event("efhc:activity-sync"));
    return context;
  }, []);

  const logout = useCallback(async () => {
    try {
      if (isDemoBackendMode() && !readAuthSession()) await revokeDemoLogin();
      else await revokeAuthSession();
    } finally {
      clearAuthSession();
      clearDemoSession();
      // Do not automatically reissue a public guest after explicit sign-out.
      guestBootstrapStarted.current = true;
      setState({
        status: "anonymous",
        context: null,
        errorCode: null,
      });
    }
  }, []);

  const controller = useMemo<AuthSessionController>(() => ({
    ...state,
    restoreSession,
    logout,
    loginTelegram,
    loginTon,
    loginDemo,
    selectDemoGlobalId,
  }), [
    state,
    restoreSession,
    logout,
    loginTelegram,
    loginTon,
    loginDemo,
    selectDemoGlobalId,
  ]);

  return (
    <AuthSessionStore.Provider value={controller}>
      {props.children}
    </AuthSessionStore.Provider>
  );
}

export function useAuthSessionController(): AuthSessionController {
  const value = useContext(AuthSessionStore);
  if (!value) {
    throw new Error("AUTH_SESSION_PROVIDER_REQUIRED");
  }
  return value;
}
const useBeforePaintEffect = typeof window === "undefined" ? useEffect : useLayoutEffect;

export function useAuthOwnerGlobalId(): AuthSessionContext["global_id"] | null {
  const session = useAuthSessionController();
  const authenticated = session.status === "authenticated" ? session.context?.global_id ?? null : null;
  const [cachedId, setCachedId] = useState<AuthSessionContext["global_id"] | null>(null);
  useBeforePaintEffect(() => {
    // This association was recorded from a validated server session. It keeps
    // same-owner display/cache stable through transport failures, not API rights.
    const update = () => setCachedId(resolvedDisplayOwner());
    update();
    return subscribeDisplayOwner(update);
  }, [session.status, authenticated]);
  return authenticated ?? cachedId;
}
