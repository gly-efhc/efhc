import React from "react";
import { Button } from "./Button";

type Variant = "primary" | "secondary" | "ghost";

export function EfhcButton(
  props: React.PropsWithChildren<
    React.ButtonHTMLAttributes<HTMLButtonElement> & {
      variant?: Variant;
      isLoading?: boolean;
    }
  >,
) {
  const { children, isLoading, disabled, ...rest } = props;
  return (
    <Button
      {...rest}
      disabled={Boolean(disabled) || Boolean(isLoading)}
      aria-busy={Boolean(isLoading)}
    >
      {isLoading ? "Loading…" : children}
    </Button>
  );
}
