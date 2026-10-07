# Gate 6: bounded live verification

Prepared 4 October 2026. This is the next execution step after offline correction closure, not permission to spend provider credits or accept Gate 6.

## Starting evidence

- Frozen source: `8bb8cb4c68e813dc44781acc236b0d63de6bd3b7c2077dd58e897cda47c260af`.
- Parent checkpoint: `../verification/gate6-comprehensive-20261002/final-checkpoint.json`.
- Full suite: 611 passed, zero failures/errors/skips; exit 0; two dependency warnings. Includes 108 PostgreSQL-labelled cases.
- Browser: 17 passed. Installed wheel: 9 runtime/upgrade probes, 90 installed module origins, PASS.
- Astra surface correction review PASS; Sol residual review PASS. Original blocker reports remain historical evidence.
- Four-file final residual delta is bound to the review. Generated assets match the build; 49 protected files, applied migrations 0001–0010 and accepted Gates 0–5 are unchanged.
- 4 October offline inspection: no configured API key, agent disabled, exact model configured. Zero network requests. Inspect `../verification/gate6-comprehensive-20261002/offline-preflight-20261004.json`.

## Required from the user

1. Configure `NEBIUS_API_KEY` locally, in the application `.env` or the execution process environment. Do not put the value in chat, logs, tracked files or evidence.
2. Confirm authorization for **one preflight attempt, at most 3 requests, with an 8,192-token allowance**, using `nvidia/Nemotron-3_5-Lightning`. This is a usage ceiling, not a price quote or a promise that the provider will pass the tests.
3. After inspecting that result, authorize a separately bounded flagship run/read/compare attempt. The three-request allowance does not cover it.

## Step 1: preflight only, after authorization

Parent checks the frozen source again. Use the existing Python environment; do not install software, change accounts, substitute models or redeem credits.

The script reads process environment variables. If the key is stored only in `.env`, transfer the three provider settings into that invocation using the existing Settings loader; never print their values. This PowerShell command must be run from the `shiftguard` application directory **only after the explicit allowance is approved**:

```powershell
$sgAttempt = Join-Path '..\verification' ('gate6-live-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8))
New-Item -ItemType Directory -Path $sgAttempt | Out-Null
& .\.venv\Scripts\python.exe -B -c 'import os,runpy; from shiftguard.settings import Settings; s=Settings(); os.environ["NEBIUS_API_KEY"]=s.nebius_api_key or ""; os.environ["NEBIUS_BASE_URL"]=s.nebius_base_url; os.environ["NEBIUS_MODEL"]=s.nebius_model; runpy.run_path("scripts/preflight_nebius.py",run_name="__main__")' --live --model nvidia/Nemotron-3_5-Lightning --allow-calls 3 --allow-tokens 8192 --write-redacted-evidence "$sgAttempt\preflight.json"
$sgExit = $LASTEXITCODE
Write-Output "Preflight exit code: $sgExit"
```

The existing script reserves a conservative input/output allowance before each request, uses zero SDK retries, and imposes a total deadline on each canary. Its three calls check exact chat output, a typed tool call, and the original tool-call ID exchange with a strict explanation plan. No fabricated scientific scores are accepted as evidence.

Parent records command, exit code, source manifest, redacted evidence, returned model and usage. Only `test_kind=provider_live_canary`, `mode=live`, and a successful actual provider attempt qualify as live evidence. The recorded attempt must fit both approved limits.

Stop on missing credentials/access/model, timeout, failed canary, insufficient allowance or unknown usage. Preserve the failed attempt and report the exact blocker. Do not retry automatically or relabel an injected provider as live. A preflight PASS alone does not close Gate 6.

## Step 2: real flagship workflow

After preflight success, parent prepares an isolated local server/database/artifact directory using this same source and genuine provider. Use the existing PostgreSQL 16 setup; leave the normal user database and server untouched. Use no scripted-provider or test-only override.

Before any call, obtain a separate call/token ceiling and enforce an aggregate attempt allowance at the provider boundary, covering every turn and continuation. Stop before dispatch if a request cannot fit the remainder. Per-output limits alone are not an aggregate token budget.

Perform one natural-language Bank development run, durable WAITING/resume, published-result read and bound comparison. Record issued request/job/experiment identities and actual tool traces. Verify the comparison references persisted conditions, unavailable results stay unavailable, and every rendered numeric claim comes from Python-owned evidence. Do not run confirmatory seeds or alter the scientific protocol.

Keep browser evidence and backend evidence separately labelled. A model canary against fixed metadata does not establish this runtime workflow. If a material defect appears, preserve its counterexample, apply one scoped correction, and rerun only affected checks before a new source freeze.

## Step 3: acceptance checkpoint

Bind live evidence to the exact source, provider model, usage and successful runtime trace. Record any additional required checks from the active gate contract. Parent owns the source commit and a separate governance checkpoint after the required evidence and authorization are available. Do not infer a clean candidate from the dirty working-tree manifest or mark Gate 6 accepted merely because offline tests and canaries pass.

Until that checkpoint is recorded: **Gate 6 PENDING; live A7 NOT_RUN**.
