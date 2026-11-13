import React from "react";
import { QuietPageSurface } from "./QuietPageSurface";

type Translator = (key: string) => string;

type Props = React.PropsWithChildren<{
  title?: string;
  t?: Translator;
}>;

type State = { hasError: boolean; error?: unknown };

export class ErrorBoundary extends React.Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(error: unknown): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: unknown) {
    if (process.env.NODE_ENV !== "production") {
      try {
        // eslint-disable-next-line no-console
        console.error("EFHC UI error", error);
      } catch {
        // ignore
      }
    }
  }

  render() {
    if (!this.state.hasError) return this.props.children;

    const translate = this.props.t || ((key: string) => key);
    const pathname = typeof window === "undefined" ? "/" : window.location.pathname;
    return <QuietPageSurface pathname={pathname} t={translate} />;

  }
}
