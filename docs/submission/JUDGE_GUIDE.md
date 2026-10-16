# Judge guide

**Live app:** https://shiftguard.duckdns.org. No account is needed; the app issues a private session in your browser.
**Recorded demo (fallback only):** [YouTube URL]. It is a recording, not the live app.
**Source:** https://github.com/The-Abhinav-Anand/shiftguard at release [tag / commit].

## Five-minute path

1. Open the live app. It opens the **Bank calibration workbench**. **About SHIFTGUARD**
   (`/about`) explains the problem in one screen.
2. Under **Choose an approved analysis**, pick a preset and press **Run analysis**. The **Job ledger** shows it queued, running and then completed. 
   Measured on the judge server (a free 1-CPU Oracle VM) on 15 October 2026:

   | Preset | What it runs | Time |
   |---|---|---|
   | Bank baseline | Unshifted reference | about 12 s |
   | Bank outage · 50 (default) | History-block outage, 50-label target temperature | about 15 s |
   | Bank stress | All 400 conditions | about 5½ min |

   Identical presets produce the same content-addressed result, so a repeat run reopens the
   same experiment ID.
3. Open the result under **Saved results**. Use the view filters for:
   - the reliability plot;
   - the budget curve;
   - decision loss;
   - pattern versus rate;
   - fallback details.
   **Identity & provenance** lists the exact data, split, mask and fit identities and the
   content hashes.
4. With a saved result open, choose **Results assistant**. Under **Ask about this result**,
   press **Summarize experiment …**, or **Compare experiment …** for a stress result. The
   button only fills in the exact command; press **Submit Query** to send it. Saved results
   are read only through these exact commands. A free-form question about a result usually gets
   a short notice explaining how to ask, and never an invented answer. The assistant calls approved
   read tools; every number is rendered from the stored record, and the tool trace shows what
   it did.
5. **General chat** is a separate, tool-free Nemotron conversation. Its replies are labelled
   unverified.

## Model allowance

Both assistants share one budget of 50 model calls and 100,000 tokens per UTC day across all
visitors, with no retries. A Results question can use several calls. When the day's budget
is used up, both assistants say so plainly, and everything else keeps working: runs, saved
results and charts. The budget resets at 00:00 UTC (05:30 IST).

There is no separate judge reservation: the shared daily allowance is the arrangement. How
many Results questions fit in a day depends on the measured cost per question, which is
recorded here after the live check on the fixed build [to be measured]. If the assistants
report that the day's allowance is used up, the recorded demo shows the assistant flow
(driven by a scripted stand-in, labelled as such), and every other part of the app stays
usable.

## Scope

- Bank Marketing (public UCI data) only. Uploading your own data is not supported.
- Results are single-seed development evidence. See CLAIMS_AND_EVIDENCE.md for what is and
  is not claimed.
