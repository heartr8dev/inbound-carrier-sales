// Per-card error boundary so a single broken visualization can't take down
// the whole dashboard.
import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // eslint-disable-next-line no-console
    console.error("[dashboard] render error", error, info);
  }

  render() {
    if (this.state.error) {
      return (
        this.props.fallback ?? (
          <div className="rounded-md border border-rose-700/40 bg-rose-950/40 p-4 text-sm text-rose-200">
            <p className="font-semibold">Component error</p>
            <p className="mt-1 break-words text-xs text-rose-300/80">
              {this.state.error.message}
            </p>
          </div>
        )
      );
    }
    return this.props.children;
  }
}
