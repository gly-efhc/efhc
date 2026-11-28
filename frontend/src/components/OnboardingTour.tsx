import { useRouter } from "next/router";
import React, { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";

const ONBOARDING_KEY = "onboarding_v1_seen";

type OnboardingTourProps = {
  t: (key: string) => string;
};

function isLegalPage(): boolean {
  if (typeof window === "undefined") return false;
  const legal = new URLSearchParams(window.location.search).get(
    "legal",
  );
  const proofWindow = window as Window & {
    __EFHC_LEGAL_PROOF_KIND__?: string;
  };
  return [
    "terms",
    "privacy",
  ].includes(legal || proofWindow.__EFHC_LEGAL_PROOF_KIND__ || "");
}

export function OnboardingTour({ t }: OnboardingTourProps) {
  const router = useRouter();
  const [visible, setVisible] = useState(false);
  const [step, setStep] = useState(0);
  const [expanded, setExpanded] = useState(false);
  const [portalReady, setPortalReady] = useState(false);

  const steps = useMemo(
    () => [
      {
        title: t("onboarding.energy_title"),
        text: t("onboarding.energy_text"),
      },
      {
        title: t("onboarding.panels_title"),
        text: t("onboarding.panels_text"),
      },
      {
        title: t("onboarding.exchange_title"),
        text: t("onboarding.exchange_text"),
      },
      {
        title: t("onboarding.help_title"),
        text: t("onboarding.help_text"),
      },
    ],
    [t],
  );

  useEffect(() => {
    setPortalReady(true);
  }, []);

  useEffect(() => {
    if (typeof window === "undefined" || isLegalPage()) return;
    try {
      if (window.localStorage.getItem(ONBOARDING_KEY) === "1") {
        return;
      }
    } catch {
      // UI-only fallback.
    }
    setVisible(true);
  }, []);

  useEffect(() => {
    if (typeof document === "undefined") return;
    const root = document.documentElement;
    if (!visible) {
      delete root.dataset.efhcOnboarding;
      return;
    }
    root.dataset.efhcOnboarding = ["/", "/app"].includes(
      router.pathname,
    )
      ? "full"
      : "compact";
    return () => {
      delete root.dataset.efhcOnboarding;
    };
  }, [router.pathname, visible]);

  const close = () => {
    try {
      window.localStorage.setItem(ONBOARDING_KEY, "1");
    } catch {
      // UI-only flag; storage failure must not break the app.
    }
    setVisible(false);
    window.dispatchEvent(
      new CustomEvent("efhc:onboarding-complete"),
    );
  };

  if (!visible || router.pathname.startsWith("/admin")) return null;

  const energyRoute = ["/", "/app"].includes(router.pathname);
  const current = steps[Math.min(step, steps.length - 1)];
  const last = step >= steps.length - 1;

  const content = !energyRoute ? (
    <aside
      className="efhc-onboarding-compact"
      data-onboarding-tour="v1"
      data-onboarding-mode="compact-deep-route"
      data-expanded={expanded ? "true" : "false"}
    >
      <button
        type="button"
        aria-expanded={expanded}
        onClick={() => setExpanded((value) => !value)}
      >
        <span>{t("onboarding.kicker")}</span>
        <b>{expanded ? "−" : "+"}</b>
      </button>
      {expanded ? (
        <div>
          <strong>{current.title}</strong>
          <p>{current.text}</p>
          <div className="efhc-onboarding-compact_actions">
            <button type="button" onClick={close}>
              {t("onboarding.skip")}
            </button>
            <button
              type="button"
              onClick={() => setStep(last ? 0 : step + 1)}
            >
              {last
                ? t("onboarding.done")
                : t("onboarding.next")}
            </button>
          </div>
        </div>
      ) : null}
    </aside>
  ) : (
    <div
      className="onboarding-tour"
      data-onboarding-tour="v1"
      data-onboarding-mode="full-energy"
      role="dialog"
      aria-modal="true"
    >
      <div className="onboarding-tour_card">
        <div className="onboarding-tour_kicker">
          {t("onboarding.kicker")}
        </div>
        <h2>{current.title}</h2>
        <p>{current.text}</p>
        <div className="onboarding-tour_steps">
          {steps.map((_, index) => (
            <span
              key={index}
              data-active={index === step ? "1" : "0"}
            />
          ))}
        </div>
        <div className="onboarding-tour_actions">
          <button type="button" onClick={close}>
            {t("onboarding.skip")}
          </button>
          <button
            type="button"
            onClick={() => (last ? close() : setStep(step + 1))}
          >
            {last ? t("onboarding.done") : t("onboarding.next")}
          </button>
        </div>
      </div>
    </div>
  );

  if (!portalReady || typeof document === "undefined") return null;
  return createPortal(content, document.body);
}
