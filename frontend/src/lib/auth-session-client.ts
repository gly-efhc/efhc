import {
  clearAuthSession,
  getAuthAuthorizationHeader,
  storeAuthSession,
  validateAuthSessionContext,
  type AuthSessionContext,
  type AuthSessionCredential,
} from "./auth-session";
import {
  requestAuthLogout,
  requestAuthSessionContext,
} from "../services/authSession.service";
import {recordResolvedDisplayOwner} from "./displayOwner";
import {parseGlobalId} from "../types/identity";

export type SessionIssuingResult = {
  session: AuthSessionCredential;
  global_id?: string;
};

export function acceptIssuedAuthSession(
  result: SessionIssuingResult,
): void {
  const owner = result.global_id ? parseGlobalId(result.global_id) : null;
  storeAuthSession(result.session);
  if(owner)recordResolvedDisplayOwner(owner);
}

export async function fetchAuthSessionContext():
  Promise<AuthSessionContext> {
  const authorization = getAuthAuthorizationHeader();
  const result = await requestAuthSessionContext();
  if (authorization !== getAuthAuthorizationHeader()) throw new Error("AUTH_SESSION_REPLACED");
  const context=validateAuthSessionContext(result);
  recordResolvedDisplayOwner(context.global_id);
  return context;
}

export async function revokeAuthSession(): Promise<void> {
  try {
    await requestAuthLogout();
  } finally {
    clearAuthSession();
  }
}
