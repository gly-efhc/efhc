import React, { useMemo } from "react";
import { LayoutContext } from "../components/Layout";
import { Card } from "../components/ui/Card";
import { FaqSearchBar } from "../components/faq/FaqSearchBar";
import { FaqNoResultsState } from "../components/faq/FaqNoResultsState";
import { FaqVerticalTree } from "../components/faq/FaqVerticalTree";
import { FaqSectionList } from "../components/faq/FaqSectionList";
import { FaqSubsectionList } from "../components/faq/FaqSubsectionList";
import { FaqQuestionItem } from "../components/faq/FaqQuestionItem";
import { FaqBreadcrumbHeader } from "../components/faq/FaqBreadcrumbHeader";
import { useT } from "../hooks/useT";
import { useFaqCatalog } from "../hooks/faq/useFaqCatalog";
import { useFaqNavigation } from "../hooks/faq/useFaqNavigation";
import { useFaqSearch } from "../hooks/faq/useFaqSearch";
import { FaqAnswerText } from "../components/faq/FaqAnswerText";
import type { FaqSection } from "../data/faq/types";
import { useInterfaceVariantSurface } from "../hooks/useInterfaceVariantSurface";

function normalizedFaqTitle(value: string): string {
  return value.trim().toLocaleLowerCase().replace(/\s+/g, " ");
}

function isRedundantSingleSubsection(section: FaqSection): boolean {
  return section.subsections.length === 1
    && normalizedFaqTitle(section.subsections[0]?.title || "")
      === normalizedFaqTitle(section.title);
}

export default function FaqPage() {
  const t = useT();
  const ctx = React.useContext(LayoutContext);
  const faq = useFaqCatalog(ctx.lang);
  const catalog = faq.catalog;
  const nav = useFaqNavigation();
  const search = useFaqSearch(catalog);
  const faqSurface = useInterfaceVariantSurface<HTMLDivElement>("FQ", {
    dotsPlacement: "below",
  });
  const variant = faqSurface.variant;

  const selectedSection = useMemo(
    () => catalog.sections.find((section) => section.id === nav.sectionId) || null,
    [catalog.sections, nav.sectionId],
  );
  const selectedSubsection = useMemo(
    () => selectedSection?.subsections.find(
      (subsection) => subsection.id === nav.subsectionId,
    ) || null,
    [nav.subsectionId, selectedSection],
  );
  const renderDrilldown = () => {
    if (!selectedSection) {
      return (
        <Card title={t("faq.sections")}>
          <FaqSectionList
            sections={catalog.sections}
            countLabel={t("faq.subsections_count")}
            questionsLabel={t("faq.questions_count")}
            onOpen={nav.openSection}
          />
        </Card>
      );
    }
    if (!selectedSubsection) {
      if (isRedundantSingleSubsection(selectedSection)) {
        const subsection = selectedSection.subsections[0];
        return (
          <Card title={selectedSection.title}>
            <FaqBreadcrumbHeader
              parts={[t("faq.sections"), selectedSection.title]}
              onBack={nav.goToSections}
            />
            <div className="mt-3 grid gap-2">
              {subsection.items.map((item) => (
                <FaqQuestionItem
                  key={item.id}
                  item={item}
                  isOpen={nav.openItemIds.has(item.id)}
                  onToggle={() => nav.openQuestion(
                    selectedSection.id,
                    subsection.id,
                    item.id,
                  )}
                />
              ))}
            </div>
          </Card>
        );
      }
      return (
        <Card title={selectedSection.title}>
          <FaqBreadcrumbHeader
            parts={[t("faq.sections"), selectedSection.title]}
            onBack={nav.goToSections}
          />
          <div className="mt-3">
            <FaqSubsectionList
              section={selectedSection}
              questionsLabel={t("faq.questions_count")}
              onOpen={nav.openSubsection}
            />
          </div>
        </Card>
      );
    }
    return (
      <Card title={selectedSubsection.title}>
        <FaqBreadcrumbHeader
          parts={[selectedSection.title, selectedSubsection.title]}
          onBack={nav.goToSubsections}
        />
        <div className="mt-3 grid gap-2">
          {selectedSubsection.items.map((item) => (
            <FaqQuestionItem
              key={item.id}
              item={item}
              isOpen={nav.openItemIds.has(item.id)}
              onToggle={() => nav.openQuestion(
                selectedSection.id,
                selectedSubsection.id,
                item.id,
              )}
            />
          ))}
        </div>
      </Card>
    );
  };

  const renderTopicFocus = () => {
    if (!selectedSection) {
      return (
        <Card title={t("faq.sections")}>
          <FaqSectionList
            sections={catalog.sections}
            countLabel={t("faq.subsections_count")}
            questionsLabel={t("faq.questions_count")}
            onOpen={nav.openSection}
          />
        </Card>
      );
    }
    const redundantSubsection = isRedundantSingleSubsection(selectedSection)
      ? selectedSection.subsections[0]
      : null;
    return (
      <Card title={selectedSection.title}>
        <FaqBreadcrumbHeader
          parts={[t("faq.sections"), selectedSection.title]}
          onBack={nav.goToSections}
        />
        <div className="mt-3">
          {redundantSubsection ? (
            <div className="grid gap-2">
              {redundantSubsection.items.map((item) => (
                <FaqQuestionItem
                  key={item.id}
                  item={item}
                  isOpen={nav.openItemIds.has(item.id)}
                  onToggle={() => nav.openQuestion(
                    selectedSection.id,
                    redundantSubsection.id,
                    item.id,
                  )}
                />
              ))}
            </div>
          ) : (
            <FaqVerticalTree
              catalog={{ ...catalog, sections: [selectedSection] }}
              openItemIds={nav.openItemIds}
              onToggleQuestion={nav.toggleQuestion}
              compactTreeProof="v103-topic-focus"
            />
          )}
        </div>
      </Card>
    );
  };

  const renderVariantBody = () => {
    if (variant === "FQ-03" || variant === "FQ-07") return renderDrilldown();
    if (variant === "FQ-04") return renderTopicFocus();
    return (
      <FaqVerticalTree
        catalog={catalog}
        openItemIds={nav.openItemIds}
        onToggleQuestion={nav.toggleQuestion}
        compactTreeProof={`v103-${variant.toLowerCase()}`}
      />
    );
  };

  return (
    <div
      key={ctx.lang}
      ref={faqSurface.ref}
      {...faqSurface.handlers}
      className="efhc-faq-shell grid gap-3"
      data-fq={variant}
      data-fq-family="global-theme"
      data-fq-ux={
        variant === "FQ-01" ? "compact-tree"
          : variant === "FQ-02" ? "collapsed-outline"
            : variant === "FQ-03" ? "drilldown"
              : variant === "FQ-04" ? "topic-focus"
                : variant === "FQ-05" ? "collapsed-handbook"
                  : variant === "FQ-06" ? "minimal-accordion"
                    : "quick-sections"
      }
      data-public-visual-trust="profile-wallet-history-faq"
      data-public-surface="faq"
      data-faq-compact-tree="1309"
      data-faq-no-horizontal-pills="true"
      data-public-no-admin-diagnostics="true"
      data-public-no-raw-payload="true"
    >
      <header className="efhc-faq-user-header" data-faq-user-header="simple">
        <h1>{t("faq.title")}</h1>
      </header>

      <div className="efhc-faq-search-zone">
        <FaqSearchBar
          value={search.query}
          onChange={search.setQuery}
          placeholder={t("faq.search_placeholder")}
          inputLabel={t("faq.search_placeholder")}
          clearLabel={t("faq.reset_search")}
          resultCount={search.hasQuery ? search.results.length : undefined}
          resultCountLabel={search.hasQuery
            ? `${t("faq.search_results")}: ${search.results.length}`
            : undefined}
          onClear={search.clearQuery}
        />
      </div>

      {search.hasQuery ? (
        <Card title={t("faq.search_results")}>
          {search.results.length ? (
            <div className="efhc-faq-search-results">
              {search.results.map((hit) => (
                <details
                  key={hit.item.id}
                  className="efhc-faq-question-node"
                  open={nav.openItemIds.has(hit.item.id)}
                >
                  <summary
                    onClick={(event) => {
                      event.preventDefault();
                      nav.toggleQuestion(hit.item.id);
                    }}
                  >
                    {hit.item.question}
                  </summary>
                  <div className="efhc-faq-answer-block">
                    <div className="text-xs efhc-text-muted2">
                      {normalizedFaqTitle(hit.section.title)
                        === normalizedFaqTitle(hit.subsection.title)
                        ? hit.section.title
                        : `${hit.section.title} → ${hit.subsection.title}`}
                    </div>
                    <FaqAnswerText
                      compact
                      text={hit.item.answer}
                    />
                  </div>
                </details>
              ))}
            </div>
          ) : (
            <FaqNoResultsState
              title={t("faq.no_matches")}
              detail={t("faq.search_scope")}
              onReset={search.clearQuery}
            />
          )}
        </Card>
      ) : renderVariantBody()}
    </div>
  );
}
