import { Component, type ErrorInfo, type ReactNode } from "react";

interface State {
  failed: boolean;
}

export class ChartErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  componentDidCatch(_error: Error, _info: ErrorInfo): void {
    // Numeric evidence is rendered in sibling tables outside this boundary.
  }

  render() {
    if (this.state.failed) {
      return (
        <div className="chart-error" role="status" aria-live="polite">
          <strong>Chart unavailable.</strong>
          <span>Persisted values remain available in the table below.</span>
          <button className="text-button" type="button" onClick={() => window.location.reload()}>Reload this view</button>
        </div>
      );
    }
    return this.props.children;
  }
}
