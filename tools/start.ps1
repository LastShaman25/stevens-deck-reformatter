param([int]$Port = 8000)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$runtime = Join-Path $root '.local/runtime'
New-Item -ItemType Directory -Force $runtime | Out-Null
# Use the project's local credential, not an unrelated inherited shell credential.
Remove-Item Env:OPENAI_API_KEY -ErrorAction SilentlyContinue
$env:STEVENS_OFFLINE = '0'
# Development is intentionally unlimited, even if the shell or .env carries a
# deployment budget. Do not introduce development spending/request/token caps.
$env:STEVENS_AI_MAX_CALLS = '0'
$env:STEVENS_AI_MAX_TOKENS = '0'
$env:STEVENS_PUBLIC_URL = "http://localhost:$Port"
$process = Start-Process -FilePath (Join-Path $root '.venv/Scripts/python.exe') -ArgumentList '-m','uvicorn','app.main:app','--app-dir','backend','--host','127.0.0.1','--port',"$Port",'--no-access-log' -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtime 'server.stdout.log') -RedirectStandardError (Join-Path $runtime 'server.stderr.log')
$process.Id | Set-Content (Join-Path $runtime 'server.pid')
Write-Output "Stevens Slide Studio launcher PID $($process.Id): http://localhost:$Port"
