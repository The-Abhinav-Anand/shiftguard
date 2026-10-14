# Judge guide

**Live app:** [HTTPS URL]. No account is needed; the app issues a private session in your browser.
**Recorded demo (fallback only):** [YouTube URL]. It is a recording, not the live app.
**Source:** [repository URL] at release [tag / commit].

## Five-minute path

1. Open the live app. It opens the **Bank calibration workbench**. **About SHIFTGUARD**
   (`/about`) explains the problem in one screen.
2. Under **Choose an approved analysis**, pick a preset and press **Run analysis**. The **Job ledger** shows it queued, running and then completed. The
   short preset takes about [measured time] on the judge deployment.
3. Open the result under **Saved results**. Use the view filters for:
   - the reliability plot;
   - the budget curve;
   - decision loss;
   - pattern versus rate;
   - fallback details.
   **Identity & provenance** lists the exact data, split, mask and fit identities and the
   content hashes.
4. Choose **Results assistant** and ask, for example: "Explain the budget-50 comparison for
   this result." The assistant calls approved read tools; every number is rendered from the
   stored record. The tool trace shows what it did.
5. **General chat** is a separate, tool-free Nemotron conversation. Its replies are labelled
   unverified.

## Model allowance

Both assistants share one budget of 10 model calls and 50,000 tokens per UTC day across all
visitors, with no retries. A Results question can use several calls. When the day's budget
is used up, both assistants say so plainly, and everything else keeps working: runs, saved
results and charts. The budget resets at 00:00 UTC (05:30 IST).

[Owner: describe any reserved judge capacity or access arrangement here once agreed.]

## Scope

- Bank Marketing (public UCI data) only. Uploading your own data is not supported.
- Results are single-seed development evidence. See CLAIMS_AND_EVIDENCE.md for what is and
  is not claimed.
