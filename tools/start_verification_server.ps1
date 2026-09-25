param([int]$Port = 8001)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$evidence = Join-Path $root '.local/verification'
New-Item -ItemType Directory -Force $evidence | Out-Null
$env:STEVENS_OFFLINE = '1'
$env:STEVENS_AUTH_DB = Join-Path $evidence 'browser-accounts.sqlite3'
$env:STEVENS_WORKSPACE_ROOT = Join-Path $evidence 'browser-workspaces'
$env:STEVENS_PUBLIC_URL = "http://127.0.0.1:$Port"
$server = Start-Process -FilePath (Join-Path $root '.venv/Scripts/python.exe') -ArgumentList '-m','uvicorn','app.main:app','--app-dir','backend','--host','127.0.0.1','--port',"$Port",'--no-access-log' -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $evidence 'browser-server.stdout.log') -RedirectStandardError (Join-Path $evidence 'browser-server.stderr.log')
$server.Id | Set-Content (Join-Path $evidence 'browser-server.pid')
Write-Output "Synthetic verification server PID $($server.Id), port $Port."
