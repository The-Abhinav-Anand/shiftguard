import { Brand } from "../components/brand/Brand";

export default function PlannedWorkspace() {
  return (
    <main className="route-page route-page--planned" id="main-content">
      <div className="route-page__inner">
        <header className="route-page__header">
          <Brand />
          <nav aria-label="Main navigation">
            <a href="/">Method</a>
            <a href="/demo">Benchmark demo</a>
          </nav>
        </header>
        <section className="planned-message" aria-labelledby="planned-workspace-title">
          <p className="route-page__eyebrow">Planned — not available in this build</p>
          <h1 id="planned-workspace-title">Private workspace</h1>
          <p>Private workspaces are planned. This build supports the Bank benchmark demo.</p>
          <a className="route-page__primary" href="/demo">Open benchmark demo <span aria-hidden="true">↗</span></a>
        </section>
        <footer className="route-page__footer">SHIFTGUARD · BANK BENCHMARK EVIDENCE</footer>
      </div>
    </main>
  );
}
