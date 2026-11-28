import React from "react";
import { Card } from "./Card";

export function EfhcCard(
  props: React.PropsWithChildren<{
    title?: string;
    highlight?: "energy" | "none";
    className?: string;
  }>,
) {
  return <Card {...props} />;
}
