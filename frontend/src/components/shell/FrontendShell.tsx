import React from "react";

function cx(...items: Array<string | null | undefined | false>) {
  return items.filter(Boolean).join(" ");
}

type DivProps = React.HTMLAttributes<HTMLDivElement>;

type ButtonTone = "primary" | "secondary" | "ghost" | "danger";

export function FrontendShellRoot(props: DivProps) {
  const { className, children, ...rest } = props;
  return (
    <div
      {...rest}
      className={cx("efhc-frontend-shell", className)}
    >
      {children}
    </div>
  );
}

export function FrontendShellFrame(props: DivProps) {
  const { className, children, ...rest } = props;
  return (
    <div
      {...rest}
      className={cx("efhc-frontend-frame", className)}
    >
      {children}
    </div>
  );
}

export function FrontendShellMain(props: DivProps) {
  const { className, children, ...rest } = props;
  return (
    <main
      {...rest}
      className={cx("efhc-frontend-main", className)}
    >
      {children}
    </main>
  );
}

export function FrontendPageContainer(props: DivProps) {
  const { className, children, ...rest } = props;
  return (
    <section
      {...rest}
      className={cx("efhc-frontend-page", className)}
    >
      {children}
    </section>
  );
}

export function FrontendCard(
  props: React.PropsWithChildren<{
    title?: string;
    action?: React.ReactNode;
    className?: string;
  }>,
) {
  return (
    <article className={cx("efhc-frontend-card", props.className)}>
      {props.title || props.action ? (
        <div className="efhc-frontend-card_head">
          {props.title ? <h3>{props.title}</h3> : <span />}
          {props.action}
        </div>
      ) : null}
      <div className="efhc-frontend-card_body">
        {props.children}
      </div>
    </article>
  );
}

export function FrontendButton(
  props: React.ButtonHTMLAttributes<HTMLButtonElement> & {
    tone?: ButtonTone;
    loading?: boolean;
  },
) {
  const { className, children, tone, loading, disabled, ...rest } = props;
  return (
    <button
      {...rest}
      type={props.type || "button"}
      disabled={Boolean(disabled) || Boolean(loading)}
      aria-busy={Boolean(loading)}
      className={cx(
        "efhc-frontend-button",
        `efhc-frontend-button--${tone || "primary"}`,
        className,
      )}
      data-loading={loading ? "true" : "false"}
    >
      <span className="efhc-frontend-button_content">{children}</span>
      {loading ? (
        <span
          className="efhc-frontend-button_spinner"
          aria-hidden="true"
        />
      ) : null}
    </button>
  );
}

export function FrontendProgressBar(props: {
  value: number;
  label?: string;
}) {
  const value = Math.max(0, Math.min(100, props.value));
  return (
    <div className="efhc-frontend-progress">
      {props.label ? (
        <div className="efhc-frontend-progress_label">
          {props.label}
        </div>
      ) : null}
      <div className="efhc-frontend-progress_track">
        <div
          className="efhc-frontend-progress_fill"
          style={{ width: `${value}%` }}
        />
      </div>
    </div>
  );
}

export function FrontendStatusBlock(props: {
  title: string;
  detail?: string;
  tone?: "info" | "ok" | "warn" | "error";
}) {
  return (
    <div className={`efhc-frontend-status ${props.tone || "info"}`}>
      <strong>{props.title}</strong>
      {props.detail ? <span>{props.detail}</span> : null}
    </div>
  );
}

export function FrontendLoadingState(props: { label: string }) {
  return <FrontendStatusBlock title={props.label} tone="info" />;
}

export function FrontendEmptyState(props: {
  title: string;
  detail?: string;
}) {
  return (
    <FrontendStatusBlock
      title={props.title}
      detail={props.detail}
      tone="warn"
    />
  );
}

export function FrontendErrorState(props: {
  title: string;
  detail?: string;
}) {
  return (
    <FrontendStatusBlock
      title={props.title}
      detail={props.detail}
      tone="error"
    />
  );
}
