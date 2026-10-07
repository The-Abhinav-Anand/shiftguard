import { useRef } from 'react';
import { Brand } from '../components/brand/Brand';
import { SceneFrame } from '../components/brand/SceneFrame';
import { useBrandMotion } from '../motion/useBrandMotion';

function GapDiagram() {
  return (
    <svg className="overview-diagram" viewBox="0 0 560 170" role="img" aria-labelledby="gap-title gap-desc">
      <title id="gap-title">A fixed reference with a distinct history-input region</title>
      <desc id="gap-desc">Seven ordinary input columns sit beside three history-input columns. The diagram shows structure only, not a measured rate.</desc>
      <path d="M34 28h286M34 55h286M34 82h286M34 109h286M34 136h286" className="diagram-rule" />
      <path d="M357 19v124m0-124h12m-12 124h12" className="diagram-bracket" />
      <path d="M385 28h132M385 55h132M385 82h132M385 109h132M385 136h132" className="diagram-history-rule" />
      <path d="M34 155h286" className="diagram-baseline" />
      <text x="34" y="13" className="diagram-label">ORDINARY INPUTS</text>
      <text x="385" y="13" className="diagram-label">HISTORY INPUTS</text>
      <text x="34" y="168" className="diagram-note">A fixed reference makes the shift inspectable.</text>
    </svg>
  );
}

function EvidenceDiagram() {
  const rows = [
    { label: 'Raw', y: 42 },
    { label: 'Source', y: 82 },
    { label: 'Target', y: 122 },
  ];
  return (
    <svg className="overview-diagram" viewBox="0 0 560 170" role="img" aria-labelledby="evidence-title evidence-desc">
      <title id="evidence-title">Three calibration records compared on equal rails</title>
      <desc id="evidence-desc">Raw, source-calibrated, and target-calibrated records have equal-length lines. The illustration encodes no quality ranking.</desc>
      {rows.map((row, index) => (
        <g key={row.label}>
          <text x="34" y={row.y + 4} className="diagram-row-label">{row.label}</text>
          <path d={'M145 ' + row.y + 'h330'} className={index === 1 ? 'diagram-measure diagram-measure--active' : 'diagram-measure'} />
          <path d={'M475 ' + (row.y - 5) + 'v10'} className="diagram-tick" />
        </g>
      ))}
      <text x="145" y="157" className="diagram-note">Equal marks · measured results live in the workbench</text>
    </svg>
  );
}

function LossDiagram() {
  return (
    <svg className="overview-diagram" viewBox="0 0 560 170" role="img" aria-labelledby="loss-title loss-desc">
      <title id="loss-title">Recorded decision loss follows a named cost pair</title>
      <desc id="loss-desc">False-positive and false-negative cost settings feed a recorded loss calculation. The diagram does not represent money or realized savings.</desc>
      <rect x="34" y="27" width="178" height="48" rx="2" className="diagram-box" />
      <rect x="34" y="91" width="178" height="48" rx="2" className="diagram-box" />
      <text x="50" y="47" className="diagram-label">FALSE POSITIVE</text>
      <text x="50" y="65" className="diagram-row-label">Recorded cost setting</text>
      <text x="50" y="111" className="diagram-label">FALSE NEGATIVE</text>
      <text x="50" y="129" className="diagram-row-label">Recorded cost setting</text>
      <path d="M212 51h58v32m-58 32h58V83h46" className="diagram-bracket" />
      <rect x="316" y="57" width="201" height="52" rx="2" className="diagram-result-box" />
      <text x="333" y="79" className="diagram-label">PERSISTED RESULT</text>
      <text x="333" y="98" className="diagram-row-label">Traceable to saved evidence</text>
      <text x="316" y="133" className="diagram-note">A decision metric, not currency or ROI.</text>
    </svg>
  );
}

export default function Overview() {
  const pageRef = useRef<HTMLElement>(null);
  useBrandMotion(pageRef);

  return (
    <main className="overview-page" ref={pageRef}>
      <div className="overview-wrap">
        <header className="overview-header">
          <Brand />
          <nav className="overview-nav" aria-label="Main navigation">
            <a href="#method">Method</a>
            <a href="#availability">Availability</a>
            <a className="overview-nav__cta" href="/demo">Explore demo <span aria-hidden="true">↗</span></a>
          </nav>
        </header>

        <section className="overview-hero" aria-labelledby="overview-title">
          <div className="overview-hero__copy" data-motion="hero-copy">
            <p className="overview-eyebrow"><span aria-hidden="true" /> Calibration under missing inputs</p>
            <h1 id="overview-title">When inputs shift,<br className="overview-wide-break" /> know what <em>still holds.</em></h1>
            <p className="overview-lede">Inspect how missing inputs affect probability quality and decision loss. Explore reproducible Bank benchmark runs, compare recorded calibration results, and trace each result to its saved evidence.</p>
            <div className="overview-actions">
              <a className="overview-button overview-button--primary" href="/demo">Explore benchmark demo <span aria-hidden="true">↗</span></a>
              <a className="overview-text-link" href="#method">How evidence is built <span aria-hidden="true">↓</span></a>
            </div>
            <p className="overview-hero__availability-note">Available today: Bank benchmark presets. Single-seed development evidence. Private-data workflows are planned.</p>
          </div>
          <div className="overview-hero__figure" data-motion="hero-figure">
            <SceneFrame />
          </div>
        </section>

        <aside className="overview-evidence-strip" aria-label="Evidence scope">
          <div><span>01</span><strong>Bank benchmark</strong></div>
          <div><span>02</span><strong>Development evidence</strong></div>
          <div><span>03</span><strong>Traceable records</strong></div>
        </aside>

        <section className="overview-method" id="method" aria-labelledby="method-title">
          <div className="overview-section-heading">
            <p className="overview-eyebrow"><span aria-hidden="true" /> A readable evidence path</p>
            <h2 id="method-title">From shifted inputs<br className="overview-heading-break" /> to recorded consequence.</h2>
            <p>Three steps keep the question, comparison, and saved evidence in view. The diagrams explain the method; measured values stay tied to actual benchmark records.</p>
          </div>

          <article className="overview-chapter" data-reveal>
            <div className="overview-chapter__index">01</div>
            <div className="overview-chapter__text">
              <p className="overview-eyebrow">Expose the gap</p>
              <h3>See which inputs go missing.</h3>
              <p>Separate ordinary features from the recorded history inputs. A fixed reference makes the pattern understandable without implying a result.</p>
            </div>
            <div className="overview-chapter__art"><GapDiagram /></div>
          </article>

          <article className="overview-chapter" data-reveal>
            <div className="overview-chapter__index">02</div>
            <div className="overview-chapter__text">
              <p className="overview-eyebrow">Compare the evidence</p>
              <h3>Read each calibration record on its own terms.</h3>
              <p>Inspect raw, source, and target methods against persisted results, including qualifications and unfavorable outcomes.</p>
            </div>
            <div className="overview-chapter__art"><EvidenceDiagram /></div>
          </article>

          <article className="overview-chapter" data-reveal>
            <div className="overview-chapter__index">03</div>
            <div className="overview-chapter__text">
              <p className="overview-eyebrow">Inspect the consequence</p>
              <h3>Trace decision loss to its recorded cost pair.</h3>
              <p>See the false-positive and false-negative settings used by a result. Decision loss is a persisted metric, not currency, savings, or ROI.</p>
            </div>
            <div className="overview-chapter__art"><LossDiagram /></div>
          </article>
        </section>

        <section className="overview-availability" id="availability" aria-labelledby="availability-title">
          <div className="overview-availability__intro">
            <p className="overview-eyebrow"><span aria-hidden="true" /> Current scope</p>
            <h2 id="availability-title">What you can use today.</h2>
            <p>Explore the accepted Bank benchmark workbench and inspect the evidence it has saved.</p>
            <ol className="overview-capabilities">
              <li><span>01</span><div><strong>Run approved presets</strong><p>Use the fixed Bank benchmark presets and their recorded development seed.</p></div></li>
              <li><span>02</span><div><strong>Compare persisted results</strong><p>Inspect calibration, missingness, reliability, and decision-loss records where available.</p></div></li>
              <li><span>03</span><div><strong>Follow the evidence</strong><p>Review each result's source, qualification, and saved provenance.</p></div></li>
            </ol>
          </div>
          <aside className="overview-planned" aria-labelledby="planned-title">
            <div className="overview-planned__top"><span className="overview-eyebrow">Planned — not available</span><span className="overview-planned__index">FUTURE SCOPE / 01</span></div>
            <h3 id="planned-title">Private workspace</h3>
            <p>Private-data workflows are planned. This build does not accept a dataset or run a business model.</p>
            <div className="overview-planned__schematic" aria-hidden="true">
              <div className="planned-line planned-line--wide" /><div className="planned-line" />
              <div className="planned-steps"><span>Schema</span><i /><span>Validation</span><i /><span>Evidence</span></div>
              <div className="planned-outline"><span /><span /><span /></div>
            </div>
            <p className="overview-planned__foot">No upload, account, or private-run controls in this build.</p>
          </aside>
        </section>

        <footer className="overview-footer">
          <div><Brand dark /><p>Calibration evidence for conditions where model inputs change.</p></div>
          <p className="overview-footer__scope">Bank benchmark presets · Single-seed development evidence<br />Results describe recorded experiments; they do not guarantee adaptation.</p>
          <a className="overview-button overview-button--footer" href="/demo">Explore benchmark demo <span aria-hidden="true">↗</span></a>
        </footer>
      </div>
    </main>
  );
}
