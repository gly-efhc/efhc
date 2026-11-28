import React from "react";

export function TelegramBadgeGroup(
  props: React.PropsWithChildren<{
    className?: string;
  }>,
) {
  return (
    <div className={["flex flex-wrap gap-2", props.className || ""].join(" ")}>
      {props.children}
    </div>
  );
}
