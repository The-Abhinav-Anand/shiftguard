# SHIFTGUARD Claude Code entrypoint

Requested executor: Claude Code Opus 5.5. Prepared 12 October 2026. Model availability must be checked in the receiving Claude environment; it was not verified here.

Read in order:

1. `../deliverables/claude-handoff-20261012/START_HERE.md`
2. `../deliverables/claude-handoff-20261012/PROJECT_HANDOFF.md`
3. `docs/superpowers/plans/2026-10-12-claude-project-continuation.md`
4. `AGENTS.md`, `.agent/session-state.md`, `.agent/gates.json`
5. `docs/ordinary-chat.md` and the affected source/tests listed in the plan.
6. `../deliverables/claude-handoff-20261012/RESEARCH_HANDOFF.md` before any research work.

Current branch: `implementation/gate-0`. Retained HEAD: `f3f696579345347884d547f7ec4c75a84ce21184`. Ordinary chat is dirty/unaccepted; both local assistant flags are false. Gates 0–7 retain their exact accepted/frozen bindings. Gate 8 is pending; protocol is DRAFT_NOT_LOCKED.

The user's transfer request supersedes historical Luna/Astra/Sol/Antigravity staffing instructions. Claude is the receiving coordinator and executor. Do not invent an independent review by renaming the executor. Completed historical reviews remain evidence; pending reviews need actual independent assessment. One writer per file, coherent batches, one consolidated review of each frozen major delta.

Never reset, clean, overwrite or recreate the checkout. Preserve untracked implementation files. Never print `.env`, credentials or a PostgreSQL URL. Do not use old paid allowances. Handoff preparation grants no new API-call budget, installation, public deployment, push, scientific approval or outcome access. Source commits remain behind the existing parent-verification/authorization boundary. Do not edit applied migrations 0001–0011.

Verify transfer before editing:

```powershell
& .\.venv\Scripts\python.exe -B ..\deliverables\claude-handoff-20261012\verify_handoff.py
```

First execution batch after the user instructs Claude to continue: verify the retained migration assertion on both backends, close ordinary-chat frontend/build/integration and scoped review, then local activation under the existing cost contract. Gate 8 P2 follows using fabricated fixtures only.

## Session Config

project-name: shiftguard
vcs: none
persistence: true
enforcement: warn
waves: 1
agents-per-wave: 1
test-command: .\.venv\Scripts\python.exe -B -m pytest tests -q -p no:cacheprovider
typecheck-command: npm --prefix frontend run typecheck
lint-command: git -c safe.directory=C:/Users/Abhinav Anand/Downloads/nvidia/shiftguard diff --check
recent-commits: 20
stale-branch-days: 7
auto-skill-dispatch: false
