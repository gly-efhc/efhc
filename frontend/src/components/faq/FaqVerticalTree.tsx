import React from "react";
import type { FaqCatalog, FaqItem } from "../../data/faq/types";
import { FaqKeywordTags } from "./FaqKeywordTags";
import { FaqAnswerText } from "./FaqAnswerText";

type Props = {
  catalog: FaqCatalog;
  defaultItemId?: string | null;
  openItemIds?: ReadonlySet<string>;
  onToggleQuestion?: (itemId: string) => void;
  openAll?: boolean;
  compactTreeProof?: string;
  showAllSubsections?: boolean;
};


export function FaqVerticalTree(props: Props) {
  const isQuestionOpen = (itemId: string) =>
    props.openAll
    || props.openItemIds?.has(itemId)
    || itemId === props.defaultItemId;
  const hasOpenQuestion = (items: FaqItem[]) =>
    items.some((item) => isQuestionOpen(item.id));
  const toggleSummary = (
    event: React.MouseEvent<HTMLElement>,
    itemId: string,
  ) => {
    if (!props.onToggleQuestion) return;
    event.preventDefault();
    props.onToggleQuestion(itemId);
  };

  const sameTitle = (left: string, right: string) =>
    left.trim().toLocaleLowerCase().replace(/\s+/g, " ")
      === right.trim().toLocaleLowerCase().replace(/\s+/g, " ");

  return (
    <div
      className="efhc-faq-vertical-tree"
      data-faq-visual-trust-tree="profile-wallet-history-faq"
      data-faq-vertical-tree={props.compactTreeProof || "true"}
    >
      {props.catalog.sections.map((section) => {
        const redundantSubsection = section.subsections.length === 1
          && sameTitle(section.title, section.subsections[0]?.title || "")
          ? section.subsections[0]
          : null;
        const sectionItems = section.subsections.flatMap(
          (subsection) => subsection.items,
        );
        return (
          <details
            key={section.id}
            className="efhc-faq-section-node"
            open={
              props.openAll || props.showAllSubsections || hasOpenQuestion(sectionItems)
            }
          >
            <summary>
              <span>{section.id}. {section.title}</span>
              <em>{sectionItems.length}</em>
            </summary>
            {redundantSubsection ? (
              <div className="efhc-faq-question-stack">
                {redundantSubsection.items.map((item) => (
                  <details
                    key={item.id}
                    className="efhc-faq-question-node"
                    open={isQuestionOpen(item.id)}
                  >
                    <summary onClick={(event) => toggleSummary(event, item.id)}>
                      {item.question}
                    </summary>
                    <div className="efhc-faq-answer-block">
                      <FaqAnswerText text={item.answer} />
                      {item.keywords?.length ? (
                        <FaqKeywordTags tags={item.keywords} />
                      ) : null}
                    </div>
                  </details>
                ))}
              </div>
            ) : (
              <div className="efhc-faq-subsection-stack">
                {section.subsections.map((subsection) => (
                  <details
                    key={subsection.id}
                    className="efhc-faq-subsection-node"
                    open={
                      props.openAll || props.showAllSubsections || hasOpenQuestion(subsection.items)
                    }
                  >
                    <summary>
                      <span>{subsection.id}. {subsection.title}</span>
                      <em>{subsection.items.length}</em>
                    </summary>
                    <div className="efhc-faq-question-stack">
                      {subsection.items.map((item) => (
                        <details
                          key={item.id}
                          className="efhc-faq-question-node"
                          open={isQuestionOpen(item.id)}
                        >
                          <summary onClick={(event) => toggleSummary(event, item.id)}>
                            {item.question}
                          </summary>
                          <div className="efhc-faq-answer-block">
                            <FaqAnswerText text={item.answer} />
                            {item.keywords?.length ? (
                              <FaqKeywordTags tags={item.keywords} />
                            ) : null}
                          </div>
                        </details>
                      ))}
                    </div>
                  </details>
                ))}
              </div>
            )}
          </details>
        );
      })}
    </div>
  );
}
