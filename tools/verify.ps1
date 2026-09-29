param([switch]$SkipBrowser)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$run = 'run-' + [guid]::NewGuid().ToString('N')
$evidence = Join-Path $root ('.local/verification/' + $run)
New-Item -ItemType Directory -Force $evidence | Out-Null
$python = Join-Path $root '.venv/Scripts/python.exe'
$env:STEVENS_OFFLINE = '1'
$env:STEVENS_LEARN = '0'
$env:STEVENS_AUTH_DB = Join-Path $evidence 'accounts.sqlite3'
$env:STEVENS_WORKSPACE_ROOT = Join-Path $evidence 'workspaces'
function Check-Exit([string]$step) { if ($LASTEXITCODE -ne 0) { throw "$step failed ($LASTEXITCODE). Evidence: $evidence" } }
Push-Location frontend
try {
    node node_modules/vitest/vitest.mjs run --reporter=dot
    Check-Exit 'Frontend tests'
    node node_modules/typescript/bin/tsc -b
    Check-Exit 'TypeScript'
    node node_modules/vite/bin/vite.js build
    Check-Exit 'Production build'
} finally { Pop-Location }
# HTTP tests require a fresh production frontend, just like CI.
& $python -m pytest -q --basetemp="$evidence/pytest" --junitxml="$evidence/backend.xml"
Check-Exit 'Backend and real renderer tests'
if (-not $SkipBrowser) {
    & $python tools/create_test_fixture.py
    Check-Exit 'Synthetic browser fixture'
    $env:STEVENS_PUBLIC_URL = 'http://127.0.0.1:8002'
    $env:STEVENS_TEST_URL = $env:STEVENS_PUBLIC_URL
    $server = Start-Process -FilePath $python -ArgumentList '-m','uvicorn','app.main:app','--app-dir','backend','--host','127.0.0.1','--port','8002','--no-access-log' -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput "$evidence/server.stdout.log" -RedirectStandardError "$evidence/server.stderr.log"
    try {
        $ready = $false
        for ($attempt=0; $attempt -lt 30; $attempt++) {
            try { Invoke-WebRequest "$env:STEVENS_PUBLIC_URL/api/health" -UseBasicParsing -TimeoutSec 3 | Out-Null; $ready=$true; break } catch { $startupError=$_.Exception.Message; Start-Sleep -Seconds 1 }
        }
        if (-not $ready) { throw "Verification server did not become reachable: $startupError" }
        Push-Location frontend
        try { node node_modules/@playwright/test/cli.js test; Check-Exit 'Browser workflows' } finally { Pop-Location }
    } finally {
        # Windows venv launchers may have a Python child. Stop only this server tree.
        $children = Get-CimInstance Win32_Process -Filter "ParentProcessId=$($server.Id)"
        foreach ($child in $children) { Stop-Process -Id $child.ProcessId -ErrorAction SilentlyContinue }
        Stop-Process -Id $server.Id -ErrorAction SilentlyContinue
    }
}
Write-Output "Verification completed. Backend evidence: $evidence/backend.xml"
Write-Output 'Live model quality is a separate checkpoint: use verify_authoring.py and verify_output_qa.py --live.'
