import React from "react";

type CardProps = React.PropsWithChildren<
  React.HTMLAttributes<HTMLDivElement> & {
    title?: string;
    highlight?: "energy" | "none";
  }
>;

export const Card = React.forwardRef<HTMLDivElement, CardProps>(
  function Card(props, ref) {
    const {
      children,
      className,
      highlight,
      title,
      ...rest
    } = props;
    const hl = highlight === "energy" ? "efhc-border-energy" : "";
    return (
      <div
        {...rest}
        ref={ref}
        data-canon-frame="source-card"
        className={`efhc-card p-4 ${hl} ${className || ""}`}
      >
        {title ? (
          <div className="text-lg font-semibold mb-2">
            {title}
          </div>
        ) : null}
        {children}
      </div>
    );
  },
);
