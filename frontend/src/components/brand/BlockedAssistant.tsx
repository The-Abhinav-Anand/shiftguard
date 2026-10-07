export function BlockedAssistant() {
  return (
    <aside className="sg-assistant-blocked" aria-labelledby="sg-assistant-title">
      <span className="sg-assistant-blocked__marker" aria-hidden="true">i</span>
      <div>
        <p className="sg-assistant-blocked__eyebrow">Optional interpretation</p>
        <h2 id="sg-assistant-title">Assistant integration under review.</h2>
        <p>Use the benchmark controls above to run and inspect the recorded evidence.</p>
      </div>
    </aside>
  );
}
