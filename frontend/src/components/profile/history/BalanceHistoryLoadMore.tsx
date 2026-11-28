import React from "react";
import { useT } from "../../../hooks/useT";
import { Button } from "../../ui/Button";

export function BalanceHistoryLoadMore(
  props: { onLoadMore: () => void },
) {
  const t = useT();
  return (
    <div className="flex justify-center px-3 py-3">
      <Button variant="secondary" onClick={props.onLoadMore}>
        {t("common.load_more")}
      </Button>
    </div>
  );
}
