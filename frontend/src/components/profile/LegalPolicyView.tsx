import React, { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/router";
import type { Lang } from "../../lib/i18n";
import {
  getLegalPolicy,
  type LegalPolicyKind,
} from "../../data/legalPolicies";

function sectionId(index: number): string {
  return `legal-section-${index + 1}`;
}

export function LegalPolicyView(props: {
  kind: LegalPolicyKind;
  lang: Lang;
}) {
  const router = useRouter();
  const policy = getLegalPolicy(props.kind, props.lang);
  const sectionIds = useMemo(
    () => policy.sections.map((_, index) => sectionId(index)),
    [policy.sections],
  );
  const [activeSection, setActiveSection] = useState(sectionIds[0]);

  useEffect(() => {
    const targets = sectionIds
      .map((id) => document.getElementById(id))
      .filter((item): item is HTMLElement => Boolean(item));
    if (!targets.length || !("IntersectionObserver" in window)) {
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio);
        const id = visible[0]?.target.id;
        if (id) setActiveSection(id);
      },
      {
        rootMargin: "-28% 0px -58% 0px",
        threshold: [0.15, 0.4, 0.75],
      },
    );
    targets.forEach((target) => observer.observe(target));
    return () => observer.disconnect();
  }, [sectionIds]);

  const navigateToSection = (id: string) => {
    document.getElementById(id)?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  };

  return (
    <main
      className="efhc-legal-page"
      data-public-surface={`legal-${props.kind}`}
      data-legal-policy-language={props.lang}
      data-legal-english-fallback="controlled"
      data-legal-sticky-index="true"
      data-legal-version={policy.version}
    >
      <header className="efhc-legal-topbar">
        <button
          type="button"
          onClick={() => void router.push("/web-profile")}
        >
          ← {policy.back}
        </button>
        <span>EFHC</span>
      </header>

      <section className="efhc-legal-hero">
        <span className="efhc-legal-eyebrow">{policy.eyebrow}</span>
        <h1>{policy.title}</h1>
        <p>{policy.summary}</p>
        <div className="efhc-legal-meta-grid">
          <span>
            <b>{policy.versionLabel}</b>
            {policy.version}
          </span>
          <span>
            <b>{policy.effectiveLabel}</b>
            {policy.effectiveDate}
          </span>
        </div>
        <span className="efhc-legal-updated">{policy.updated}</span>
        <details className="efhc-legal-changes">
          <summary>{policy.changesLabel}</summary>
          <ul>
            {policy.changes.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </details>
      </section>

      <nav
        className="efhc-legal-index"
        aria-label={policy.sectionIndexLabel}
      >
        <strong>{policy.sectionIndexLabel}</strong>
        <div>
          {policy.sections.map((section, index) => {
            const id = sectionIds[index];
            return (
              <button
                key={id}
                type="button"
                data-active={activeSection === id ? "true" : "false"}
                aria-current={
                  activeSection === id ? "location" : undefined
                }
                onClick={() => navigateToSection(id)}
              >
                <span>{index + 1}</span>
                {section.title}
              </button>
            );
          })}
        </div>
      </nav>

      <div className="efhc-legal-sections">
        {policy.sections.map((section, index) => (
          <section
            id={sectionIds[index]}
            className="efhc-card efhc-legal-card"
            key={section.title}
          >
            <h2>{section.title}</h2>
            {section.paragraphs.map((paragraph) => (
              <p key={paragraph}>{paragraph}</p>
            ))}
          </section>
        ))}
      </div>

      <aside
        className="efhc-legal-warning"
        data-legal-security-warning="seed-private-key"
      >
        <div className="efhc-legal-warning-icon" aria-hidden="true">
          !
        </div>
        <div>
          <strong>{policy.warningLabel}</strong>
          <ul>
            <li>{policy.important}</li>
          </ul>
        </div>
      </aside>

      <div className="efhc-legal-actions">
        <button
          type="button"
          className="efhc-btn efhc-btn--primary"
          onClick={() => void router.push("/faq")}
        >
          {policy.faq}
        </button>
        <button
          type="button"
          className="efhc-btn efhc-btn--secondary"
          onClick={() => void router.push("/web-profile")}
        >
          {policy.back}
        </button>
      </div>
      <button
        type="button"
        className="efhc-legal-support-fab"
        onClick={() => void router.push("/support")}
      >
        {policy.supportLabel}
      </button>
    </main>
  );
}
