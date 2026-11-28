import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/router";
import { faqQuery } from "../../lib/faq/navigation";

type State = {
  sectionId: string | null;
  subsectionId: string | null;
  openItemId: string | null;
};

export function useFaqNavigation() {
  const router = useRouter();
  const [state, setState] = useState<State>({
    sectionId: null,
    subsectionId: null,
    openItemId: null,
  });
  const [openItemIds, setOpenItemIds] = useState<Set<string>>(
    () => new Set<string>(),
  );

  useEffect(() => {
    const sectionId = typeof router.query.section === "string"
      ? router.query.section
      : null;
    const subsectionId = typeof router.query.subsection === "string"
      ? router.query.subsection
      : null;
    const openItemId = typeof router.query.item === "string"
      ? router.query.item
      : null;
    setState({ sectionId, subsectionId, openItemId });
    if (openItemId) {
      setOpenItemIds((current) => {
        if (current.has(openItemId)) return current;
        const next = new Set(current);
        next.add(openItemId);
        return next;
      });
    }
  }, [
    router.query.item,
    router.query.section,
    router.query.subsection,
  ]);

  const pushState = (next: State) => {
    setState(next);
    void router.push(
      { pathname: "/faq", query: faqQuery({
        sectionId: next.sectionId,
        subsectionId: next.subsectionId,
        itemId: next.openItemId,
      }) },
      undefined,
      { shallow: true },
    );
  };

  const toggleQuestion = (itemId: string) => {
    setOpenItemIds((current) => {
      const next = new Set(current);
      if (next.has(itemId)) next.delete(itemId);
      else next.add(itemId);
      return next;
    });
  };

  return useMemo(() => ({
    ...state,
    openItemIds,
    toggleQuestion,
    openSection: (sectionId: string) => {
      pushState({ sectionId, subsectionId: null, openItemId: null });
    },
    openSubsection: (sectionId: string, subsectionId: string) => {
      pushState({ sectionId, subsectionId, openItemId: null });
    },
    openQuestion: (
      sectionId: string,
      subsectionId: string,
      itemId: string,
    ) => {
      const isOpen = openItemIds.has(itemId);
      toggleQuestion(itemId);
      pushState({
        sectionId,
        subsectionId,
        openItemId: isOpen && state.openItemId === itemId
          ? null
          : isOpen
            ? state.openItemId
            : itemId,
      });
    },
    goToSections: () => {
      pushState({
        sectionId: null,
        subsectionId: null,
        openItemId: null,
      });
    },
    goToSubsections: () => {
      if (!state.sectionId) return;
      pushState({
        sectionId: state.sectionId,
        subsectionId: null,
        openItemId: null,
      });
    },
  }), [
    openItemIds,
    state.sectionId,
    state.subsectionId,
    state.openItemId,
  ]);
}
