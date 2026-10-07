import { useEffect, useRef } from "react";
import { Brand } from "../components/brand/Brand";

export default function NotFound() {
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    headingRef.current?.focus();
  }, []);

  return (
    <main className="route-page route-page--not-found" id="main-content">
      <div className="route-page__inner">
        <header className="route-page__header">
          <Brand />
          <nav aria-label="Main navigation">
            <a href="/">Home</a>
            <a href="/demo">Benchmark demo</a>
          </nav>
        </header>
        <section className="not-found-message" aria-labelledby="not-found-title">
          <div className="not-found-register" aria-hidden="true">
            <svg viewBox="0 0 96 76">
              <path d="M18 17h60M18 59h60M12 11v14m72-14v14M12 51v14m72-14v14" />
              <path className="not-found-register__shift" d="M7 38h47" />
            </svg>
          </div>
          <p className="route-page__eyebrow">Route not found</p>
          <p className="not-found-code">404</p>
          <h1 id="not-found-title" ref={headingRef} tabIndex={-1}>This route has no record.</h1>
          <p>The page may have moved, or the address may be incomplete.</p>
          <nav className="not-found-actions" aria-label="Continue">
            <a className="route-page__primary" href="/">Back to SHIFTGUARD</a>
            <a className="route-page__text-link" href="/demo">Open benchmark demo</a>
          </nav>
        </section>
      </div>
    </main>
  );
}
