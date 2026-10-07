param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 8000
)

$ErrorActionPreference = 'Stop'
$sgRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$sgPython = Join-Path $sgRoot '.venv\Scripts\python.exe'
$sgRuntime = Join-Path $sgRoot 'var\runtime'
$sgUrl = "http://127.0.0.1:$Port"
if (-not (Test-Path -LiteralPath $sgPython -PathType Leaf)) {
    throw 'The existing project Python environment is missing. Follow README local setup.'
}

# Reuse only this launcher's worker-enabled server; do not replace another process.
$sgAlreadyRunning = $false
try {
    $sgExisting = Invoke-RestMethod -Uri "$sgUrl/api/v1/datasets" -TimeoutSec 2
    $sgAlreadyRunning = ($sgExisting | ConvertTo-Json -Depth 6) -match 'bank'
} catch { }
if ($sgAlreadyRunning) {
    $sgRecordPath = Join-Path $sgRuntime 'server.json'
    if (Test-Path -LiteralPath $sgRecordPath -PathType Leaf) {
        $sgRecord = Get-Content -LiteralPath $sgRecordPath -Raw | ConvertFrom-Json
        $sgOwner = Get-Process -Id $sgRecord.process_id -ErrorAction SilentlyContinue
        if ($sgOwner -and $sgRecord.url -eq $sgUrl -and $sgRecord.embedded_worker -eq $true `
            -and $sgOwner.StartTime.ToUniversalTime().Ticks -eq ([datetime]$sgRecord.process_started_utc).ToUniversalTime().Ticks) {
            $sgHealth = Invoke-RestMethod -Uri "$sgUrl/health/ready" -TimeoutSec 2
            if ($sgHealth.status -eq 'ready') {
                Write-Output "SHIFTGUARD is already available at $sgUrl with its experiment worker running."
                return
            }
        }
    }
    throw "Another SHIFTGUARD server is responding at $sgUrl, but its worker configuration is unverified. Stop that server in its owning terminal before using this launcher."
}

New-Item -ItemType Directory -Path $sgRuntime -Force | Out-Null
$sgAttempt = Get-Date -Format 'yyyyMMdd-HHmmss'
$sgStdout = Join-Path $sgRuntime "server-$sgAttempt.stdout.log"
$sgStderr = Join-Path $sgRuntime "server-$sgAttempt.stderr.log"
$sgEnvironment = @{
    SHIFTGUARD_EMBEDDED_WORKER = 'true'
    SHIFTGUARD_AGENT_ENABLED = 'false'
    PYTHONDONTWRITEBYTECODE = '1'
    OPENBLAS_NUM_THREADS = '1'
    OMP_NUM_THREADS = '1'
    MKL_NUM_THREADS = '1'
    NUMEXPR_NUM_THREADS = '1'
}
$sgPreviousEnvironment = @{}
foreach ($sgName in $sgEnvironment.Keys) {
    $sgPreviousEnvironment[$sgName] = [Environment]::GetEnvironmentVariable($sgName, 'Process')
    [Environment]::SetEnvironmentVariable($sgName, $sgEnvironment[$sgName], 'Process')
}
try {
    # Hidden, persistent API process; its lifespan owns worker and recovery.
    # The existing local database, artifact paths and frozen data are retained.
    $sgProcess = Start-Process -FilePath $sgPython -WorkingDirectory $sgRoot `
        -ArgumentList @('-B', '-m', 'uvicorn', 'shiftguard.api.main:app', '--host', '127.0.0.1', '--port', "$Port") `
        -WindowStyle Hidden -RedirectStandardOutput $sgStdout -RedirectStandardError $sgStderr -PassThru
} finally {
    foreach ($sgName in $sgEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($sgName, $sgPreviousEnvironment[$sgName], 'Process')
    }
}

$sgRecordPath = Join-Path $sgRuntime 'server.json'
$sgRecord = @{
    process_id = $sgProcess.Id
    process_started_utc = $sgProcess.StartTime.ToUniversalTime().ToString('o')
    url = $sgUrl
    started_at = (Get-Date).ToString('o')
    embedded_worker = $true
    agent_enabled = $false
    state = 'STARTING'
    stdout = $sgStdout
    stderr = $sgStderr
}
$sgRecord | ConvertTo-Json | Set-Content -LiteralPath $sgRecordPath

$sgReady = $false
$sgDeadline = (Get-Date).AddSeconds(60)
while ((Get-Date) -lt $sgDeadline) {
    $sgProcess.Refresh()
    if ($sgProcess.HasExited) {
        throw "SHIFTGUARD stopped during startup. See $sgStderr"
    }
    try {
        $sgHealth = Invoke-WebRequest -Uri "$sgUrl/health/ready" -TimeoutSec 2
        if ($sgHealth.StatusCode -eq 200) {
            $sgReady = $true
            break
        }
    } catch { }
    Start-Sleep -Milliseconds 250
}
if (-not $sgReady) {
    throw "SHIFTGUARD did not become ready within 60 seconds. Inspect $sgStderr; process ID $($sgProcess.Id)."
}
$sgRecord.state = 'READY'
$sgRecord | ConvertTo-Json | Set-Content -LiteralPath $sgRecordPath
Write-Output "SHIFTGUARD is ready at $sgUrl with its experiment worker running."
