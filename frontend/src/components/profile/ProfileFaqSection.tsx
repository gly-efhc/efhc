import React from "react";
import { useRouter } from "next/router";
import type { FaqCatalog } from "../../data/faq/types";
import { getFaqPreviewItems } from "../../data/faq/utils";
import { Button } from "../ui/Button";
import { FaqVerticalTree } from "../faq/FaqVerticalTree";

type Props = {
  t: (key: string) => string;
  catalog: FaqCatalog;
};

export function ProfileFaqSection(props: Props) {
  const router = useRouter();
  const faqPreviewItems = React.useMemo(() => {
    return getFaqPreviewItems(
      props.catalog,
      [
        { sectionId: "5", subsectionId: "5.1" },
        { sectionId: "6", subsectionId: "6.1" },
        { sectionId: "7", subsectionId: "7.1" },
      ],
      3,
    );
  }, [props.catalog]);

  return (
    <div className="efhc-profile-faq-block">
      <div className="efhc-profile-faq-head">
        <div>
          <div className="text-sm font-extrabold">
            {props.t("faq.title")}
          </div>
          <p className="mt-1 text-xs efhc-text-muted2">
            {props.t("faq.profile_intro")}
          </p>
        </div>
        <Button href="/faq" variant="secondary">
          {props.t("faq.open_full")}
        </Button>
      </div>

      <div className="efhc-profile-faq-preview">
        {faqPreviewItems.map(({ item, section, subsection }) => (
          <button
            key={item.id}
            type="button"
            className="efhc-profile-faq-row"
            onClick={() => {
              void router.push(
                `/faq?section=${section.id}`
                + `&subsection=${subsection.id}`
                + `&item=${item.id}`,
              );
            }}
          >
            <span>{item.question}</span>
            <em>{section.title} · {subsection.title}</em>
          </button>
        ))}
      </div>

      <details className="efhc-profile-faq-mini">
        <summary>{props.t("faq.sections")}</summary>
        <FaqVerticalTree catalog={props.catalog} />
      </details>
    </div>
  );
}
