# Ordinary Nemotron access

The workbench has two separate assistants:

- **General chat:** ordinary questions and follow-up conversation. Replies are AI-generated, unverified text. This mode has no tools or access to experiments, labels, jobs or artifacts.
- **Results assistant:** the existing approved run/read/compare workflow. Scientific explanations come from Python-owned persisted evidence. General-chat replies never populate result charts or empirical claims.

Local configuration in the server's `.env`:

```dotenv
SHIFTGUARD_AGENT_ENABLED=true
SHIFTGUARD_GENERAL_CHAT_ENABLED=true
```

Each flag opens only its own assistant: enabling general chat alone leaves the results assistant paused at the provider, and the reverse.

Keep the existing `NEBIUS_API_KEY` in that server-side file. Do not put it in frontend variables or source control. Source defaults remain disabled; the local launcher respects the configured flags and starts the experiment worker.

After restarting the managed local server with `scripts/start-local.ps1`, open the workbench and select General chat or Results assistant. `/api/v1/agent/status` reports configuration and usage without sending an inference request. Enabled/available status alone does not establish provider authentication; a successful actual chat is the live proof.

Both modes share one durable allowance across all sessions: **50 paid model calls and 100,000 aggregate tokens per UTC day** (owner-set on 15 October 2026; previously 10 calls and 50,000 tokens), output capped at 1,024 tokens per call, zero SDK retries. A results query can use multiple model calls. Reservations occur before dispatch; unresolved/unknown usage halts that day's allowance. Restarting the server or creating a session does not reset spending. A day already opened under a different allowance stays halted for the rest of that UTC day; the new allowance starts with the next day's ledger. Sealed gate-acceptance ledgers remain separate and cannot be reused.

General chat uses authenticated server-owned conversation history. Every stored message has a server `id` and `ordinal`. A completed reply returns the receipt, user-message and assistant-message identities and ordinals. Replaying the same key returns the identical body, including for replies stored before identities were added: those identities are derived from the stored receipt and message rows, never from text or position. The browser merges replies and history by those identities, so a reply recovered after a reload appears exactly once.

Network retries reuse the original idempotency key and return the original stored outcome. A pending crash receipt stays pending rather than issuing another paid request. A message rejected before any model request leaves the server (provider unavailable, allowance exhausted or halted, this server no longer owning dispatch) records nothing, so the same message can be retried once the cause is resolved. Changing the prompt under the same key is rejected. Session credentials cannot read another session's conversation. If an earlier reply stays unresolved, the panel says so and "New conversation" releases the tab without resending anything; the server keeps the earlier conversation and its receipt.

A reply that came back but was refused (tool calls, an empty reply, more than 8 KiB, or a malformed usage report) becomes a durable `FAILED` receipt. The same key replays the identical error with no new model request, and the user's message stays in the history with no assistant reply. A new message can continue the same conversation. The failure body never contains the refused text. Timeouts, unknown usage or an unknown dispatch outcome stay pending, because whether the model was charged is unknown.

Blank or invalid input is rejected with a 422 before any receipt is written. Validation errors list only field locations, error types and messages, never the submitted text.

## One dispatching server per database

Startup treats any open reservation as abandoned by a crashed process and closes it, which halts that day's allowance. That is only safe when no other live process could still be dispatching. A provider-enabled server therefore takes exclusive ownership of ordinary dispatch for its database before recovery or provider creation:

- **PostgreSQL:** a session advisory lock on a dedicated connection.
- **SQLite:** an operating-system lock on `<database>.ordinary-owner.lock` beside the database file.

A second provider-enabled server on the same database refuses to start and changes nothing. Ownership is released after the provider closes, on shutdown or failed startup. If ownership is lost while running, every new model request fails closed with `ORDINARY_OWNER_UNAVAILABLE` until the server restarts. Servers with both flags off and experiment workers never take ownership. Run one API process with one Uvicorn worker; do not scale it.

This local enablement does not publish or deploy the application, run the separate held-out model-quality campaign, or establish general AI prose as verified scientific evidence.
