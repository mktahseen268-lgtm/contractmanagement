"use client";

import { Component, type ReactNode } from "react";
import { AlertTriangle } from "lucide-react";

// Reusable React error boundary. Wrap each dashboard widget (or any independent panel) so an
// unexpected render crash in one widget shows a small inline fallback + Retry, instead of
// blanking the whole page. Fetch errors are handled in the widgets themselves; this catches
// the unexpected (bad data shape, render throw, etc.).

type Props = { children: ReactNode; label?: string; onRetry?: () => void };
type State = { hasError: boolean };

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: unknown) {
    // surface to the console for dev; a real deploy would forward to the SIEM/telemetry sink
    // eslint-disable-next-line no-console
    console.error("Widget crashed:", this.props.label ?? "", error);
  }

  reset = () => {
    this.setState({ hasError: false });
    this.props.onRetry?.();
  };

  render() {
    if (!this.state.hasError) return this.props.children;
    return (
      <div className="flex flex-col items-start gap-2 rounded-xl border border-line bg-white p-4 text-sm">
        <div className="flex items-center gap-2 text-ink-2">
          <AlertTriangle className="h-4 w-4 text-amber-600" />
          <span>{this.props.label ? `Couldn't load ${this.props.label}.` : "Something went wrong here."}</span>
        </div>
        <button onClick={this.reset} className="text-xs font-medium text-accent hover:underline">
          Retry
        </button>
      </div>
    );
  }
}
