import Link from "next/link";
import React from "react";

type Variant = "primary" | "secondary" | "ghost";

type CommonProps = React.PropsWithChildren<{
  variant?: Variant;
  className?: string;
}>;

type ButtonOnlyProps = CommonProps &
  React.ButtonHTMLAttributes<HTMLButtonElement> & {
    href?: undefined;
  };

type LinkButtonProps = CommonProps &
  Omit<React.AnchorHTMLAttributes<HTMLAnchorElement>, "href"> & {
    href: string;
    disabled?: boolean;
  };

type ButtonProps = ButtonOnlyProps | LinkButtonProps;

function buttonClassName(
  variant: Variant,
  className?: string,
  disabled?: boolean,
): string {
  const base = [
    "inline-flex items-center justify-center",
    "rounded-2xl",
    "px-4 py-2",
    "border",
    "text-sm font-semibold",
    "disabled:opacity-50 disabled:cursor-not-allowed",
    "transition",
    "active:scale-[0.99]",
  ].join(" ");
  const v =
    variant === "primary"
      ? "efhc-btn-primary"
      : variant === "secondary"
        ? "efhc-btn-secondary"
        : "efhc-btn-ghost";
  const blocked = disabled ? "opacity-50 pointer-events-none" : "";
  return `${base} ${v} ${blocked} ${className || ""}`.trim();
}

export function Button(props: ButtonProps) {
  const { className, variant = "primary" } = props;
  if ("href" in props && props.href) {
    const {
      href,
      disabled,
      children,
      onClick,
      className: _className,
      variant: _variant,
      ...rest
    } = props;
    return (
      <Link
        {...rest}
        href={href}
        aria-disabled={disabled ? "true" : undefined}
        onClick={disabled ? undefined : onClick}
        className={buttonClassName(variant, className, disabled)}
      >
        {children}
      </Link>
    );
  }
  const { disabled, ...rest } = props as ButtonOnlyProps;
  return (
    <button
      {...rest}
      type={(props as ButtonOnlyProps).type || "button"}
      disabled={disabled}
      className={buttonClassName(variant, className, disabled)}
    />
  );
}
