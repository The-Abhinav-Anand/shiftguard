# Gate 5 acceptance packet

**PASS — G5-R01 and G5-R02 resolved; Gate 5 accepted by the parent on 29 September 2026.** No reproducible material blocker remained in the correction delta or affected invariants.

- Accepted source: `f63116fedc2751493d79d44897ba913b6d28b0b5`.
- Reviewed 36-file source digest: `0e961a563ca38f02074b86a95c67fac8267b26f27182a8dab9a2f1256e28f492`.
- Independent reviewer: GPT-6 Astra, Extra High (`xhigh`).
- Source commit and governance checkpoint are separate. The final checkpoint SHA and clean-state check are recorded in [acceptance.json](../../verification/gate5/correction-review-20260929/acceptance.json).

## Results

| Required behavior | Evidence and outcome |
| --- | --- |
| Persisted fallback/cache | PASS: exact eight-field projection, 9 fallback rows / 8,229 fitted-bin / 9 source-remasked; both predictors, selection changes and reload with result refetch blocked. Internal failed_attempts excluded. |
| Submission-time auth recovery | PASS: four supported 401 codes expose explicit reconnect, retain published cache, clear rejected intent on session replacement and require a new intentional submission. Business 403 retains existing identity. |
| Accepted-job lost-response identity | PASS: parent real backend acceptance then simulated response loss, reload/retry, same key and job through completion. Reviewer separately covers 503 and transport abort. |
| Generated assets | PASS: fresh isolated Vite build, exact four-file set and byte hashes match served frozen assets. |
| Protected backend | PASS: 79/79 raw hashes match accepted baseline; no backend implementation change. |

Parent independently ran typecheck/build (exit 0), **3 affected browser tests** and **5 static tests**, with no failures/skips. Astra ran **8 complementary probes**, all passing. Author full browser report has **9 passing cases**, distinctly labeled supporting evidence. Two existing static-test deprecation warnings remain. Parent also inspected the fresh mobile capture. Original initial-candidate evidence covers unchanged G5-A1–A8 portions; it is not relabeled as testing the corrections.

## Exact packet and history

- [Correction review and all probe details](gate5-correction-review.md).
- [Parent verification and report hashes](../../verification/gate5/correction-review-20260929/validation.json).
- [Source-to-commit binding](../../verification/gate5/correction-review-20260929/source-binding.json).
- [Reviewer proof](../../verification/gate5/correction-review-20260929/reviewer-evidence.json).
- [Current source manifest](../../verification/gate5/correction-review-20260929/source-manifest.json).
- [Fresh visual observation](../../verification/gate5/correction-review-20260929/parent-visual.json).
- [Original BLOCKERS verdict](gate5-review.md) preserved byte-for-byte; its historical ownership text is not current policy.

Tests ran against frozen working bytes before the source commit. Parent verified every manifest file remains identical and maps to its committed Git blob using repository text filters. No post-commit test rerun is claimed. The old pending states in immutable review/evidence files describe when those files were produced; this separate acceptance record closes the checkpoint.

Review scope stayed on G5-R01/R02 and affected contracts. No unrelated Gate 4/full-backend audit was restarted. Simulated auth/transport failures prove client behavior; real parent acceptance/completion supplies the backend-linked identity proof. No live Nemotron, hosted deployment or confirmatory research acceptance is implied.

Next prepared batch: [AG-G6-OFFLINE](gate6-batch.md). It was not started by this review.
