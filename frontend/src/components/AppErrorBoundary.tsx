import { Component, type ErrorInfo, type ReactNode } from "react";

interface State {
  failed: boolean;
}

export class AppErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  componentDidCatch(_error: Error, _info: ErrorInfo): void {
    // The screen stays useful without exposing runtime details or sensitive URLs.
  }

  render() {
    if (this.state.failed) {
      return (
        <main className="route-failure" id="main-content" role="alert">
          <p className="eyebrow">PAGE LOAD</p>
          <h1>This page could not be loaded.</h1>
          <p>Reload the page to try opening its content again.</p>
          <div className="route-failure__actions">
            <button className="button button--primary" type="button" onClick={() => window.location.reload()}>Reload page</button>
            <a className="text-link" href="/">Back to SHIFTGUARD</a>
          </div>
        </main>
      );
    }
    return this.props.children;
  }
}
