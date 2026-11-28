import React from "react";
import { TelegramSearchBar } from "../ui/telegram/TelegramSearchBar";

export function FaqSearchBar(
  props: {
    value: string;
    onChange: (value: string) => void;
    placeholder: string;
    inputLabel: string;
    clearLabel: string;
    resultCount?: number;
    resultCountLabel?: string;
    onClear: () => void;
  },
) {
  return <TelegramSearchBar {...props} className="efhc-faq-search-control" />;
}
