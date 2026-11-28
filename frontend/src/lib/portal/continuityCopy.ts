export type ContinuityFlowLike = {
  readiness_state?: string | null;
  primary_cta?: string | null;
  next_action?: string | null;
  product_state?: string | null;
  return_path?: string | null;
  canonical_center?: string | null;
  wallet_ready?: boolean | null;
  blocker_codes?: string[] | null;
};

function normalize(value?: string | null): string {
  return String(value || "").trim();
}

export function readinessLabel(state?: string | null): string {
  switch (normalize(state)) {
    case "telegram_handoff_required":
      return "Telegram handoff required";
    case "external_flow_missing":
      return "external flow unavailable";
    case "wallet_sync_required":
      return "wallet sync required";
    case "resume_active_intent":
      return "ready to resume";
    case "ready":
      return "ready for action";
    default:
      return normalize(state) || "readiness unknown";
  }
}

export function readinessDescription(
  flow?: ContinuityFlowLike | null,
): string {
  if (!flow) {
    return "Truth-layer unavailable. Reload the state.";
  }
  const state = normalize(flow.readiness_state);
  if (state === "telegram_handoff_required") {
    return (
      "Open Telegram handoff first and continue " +
      "the same money path from there."
    );
  }
  if (state === "external_flow_missing") {
    return (
      "The external economic contour is unavailable " +
      "in this environment."
    );
  }
  if (state === "wallet_sync_required") {
    return (
      "Sync the wallet first. After that, " +
      "you can launch the money action."
    );
  }
  if (state === "resume_active_intent") {
    return (
      "Do not create a new intent. Continue " +
      "the existing payment path."
    );
  }
  if (state === "ready") {
    return flow.wallet_ready
      ? "Wallet synced. The money action is allowed."
      : "State looks ready, but the wallet still needs verification.";
  }
  const blockers = (flow.blocker_codes || []).filter(Boolean);
  if (blockers.length) {
    return blockers.join(", ");
  }
  return "No blocking conditions found.";
}

export function productStateLabel(state?: string | null): string {
  switch (normalize(state)) {
    case "active":
      return "active intent";
    case "pending_external":
      return "pending external confirmation";
    case "manual_review":
      return "manual review";
    case "terminal_success":
      return "success";
    case "terminal_failed":
      return "failed";
    case "expired":
      return "expired";
    default:
      return normalize(state) || "state unknown";
  }
}

export function nextActionLabel(action?: string | null): string {
  switch (normalize(action)) {
    case "open_telegram_handoff":
      return "open Telegram handoff";
    case "sync_wallet":
      return "sync wallet";
    case "resume_browser_shop":
      return "resume in Browser-Shop";
    case "open_browser_shop":
      return "open Browser-Shop";
    case "wait_network":
      return "wait for network confirmation";
    case "wait_processing":
      return "wait for processing";
    case "pay_or_wait":
      return "pay now or wait";
    case "wait_manual_review":
      return "wait for manual review";
    case "back_to_telegram":
      return "back to Telegram";
    case "open_web_profile":
      return "open Web-Profile";
    case "create_new_intent":
      return "create new intent";
    case "unavailable":
      return "unavailable";
    default:
      return normalize(action) || "action unknown";
  }
}

export function nextActionDescription(action?: string | null): string {
  switch (normalize(action)) {
    case "open_telegram_handoff":
      return (
        "Return to the Telegram shell and continue " +
        "the same scenario from there."
      );
    case "sync_wallet":
      return (
        "Finish wallet sync first, then " +
        "launch the payment flow."
      );
    case "resume_browser_shop":
      return (
        "Open Browser-Shop and continue the " +
        "active intent without duplication."
      );
    case "open_browser_shop":
      return "Open Browser-Shop and start the external execution path.";
    case "wait_network":
      return (
        "Wait for network confirmation and watcher processing. " +
        "Do not create a duplicate intent."
      );
    case "wait_processing":
      return (
        "Wait for backend processing. " +
        "Do not relaunch the same payment path."
      );
    case "pay_or_wait":
      return (
        "Pay with the current memo and address " +
        "if payment was not already sent."
      );
    case "wait_manual_review":
      return (
        "Wait until operator review is completed. " +
        "Do not create a new intent."
      );
    case "back_to_telegram":
      return (
        "Return to Telegram for the short status " +
        "and next action."
      );
    case "open_web_profile":
      return (
        "Open Web-Profile as the canonical account center, " +
        "not the quick overlay."
      );
    case "create_new_intent":
      return "Create a new intent only for a new attempt.";
    case "unavailable":
      return "This launch is unavailable in the current environment.";
    default:
      return (
        normalize(action) ||
        "Use the canonical path without local " +
        "guesses."
      );
  }
}

export function returnPathLabel(path?: string | null): string {
  switch (normalize(path)) {
    case "telegram":
      return "Telegram contour";
    case "browser_shop":
      return "Browser-Shop";
    case "web_profile":
      return "Web-Profile";
    case "hub":
      return "Hub";
    default:
      return normalize(path) || "return path unknown";
  }
}

export function returnPathDescription(
  path?: string | null,
  canonicalCenter?: string | null,
): string {
  switch (normalize(path)) {
    case "telegram":
      return normalize(canonicalCenter) === "web_profile"
        ? (
            "Return to Telegram for the short status. " +
            "The canonical account center remains Web-Profile."
          )
        : (
            "The short status and quick actions stay " +
            "in the Telegram shell."
          );
    case "browser_shop":
      return normalize(canonicalCenter) === "web_profile"
        ? (
            "Continue the execution path in Browser-Shop. " +
            "The final account state still returns to Web-Profile."
          )
        : (
            "The return path goes back to Browser-Shop to " +
            "continue the execution path."
          );
    case "web_profile":
      return (
        "Return to Web-Profile as the canonical account and " +
        "final state center."
      );
    case "hub":
      return (
        "Hub remains the handoff node and truth summary " +
        "before the external contour."
      );
    default:
      return (
        normalize(path) ||
        "Follow the canonical return path from the backend " +
        "truth-layer."
      );
  }
}

export function canonicalCenterLabel(center?: string | null): string {
  switch (normalize(center)) {
    case "web_profile":
      return "canonical center";
    case "telegram":
      return "Telegram center";
    default:
      return normalize(center) || "center";
  }
}


export function canonicalCenterDescription(
  center?: string | null,
): string {
  switch (normalize(center)) {
    case "web_profile":
      return (
        "Web-Profile stays the canonical account center; " +
        "ProfileModal remains the quick overlay."
      );
    case "telegram":
      return "Telegram remains the canonical center for this flow.";
    default:
      return normalize(center) || "canonical center unknown";
  }
}
