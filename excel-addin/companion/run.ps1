param(
  [string]$Python = ""
)

$ErrorActionPreference = "Stop"
$addin = Split-Path $PSScriptRoot -Parent
$repo = Split-Path $addin -Parent

if (-not $Python) {
  $venvPython = Join-Path $addin ".venv\Scripts\python.exe"
  if (Test-Path $venvPython) { $Python = $venvPython }
  elseif (Get-Command python -ErrorAction SilentlyContinue) { $Python = "python" }
  else { throw "Python was not found. Install 64-bit Python 3.12 and run setup.ps1." }
}

$cert = Join-Path $PSScriptRoot "certs\cert.pem"
$key = Join-Path $PSScriptRoot "certs\key.pem"
if (-not (Test-Path $cert) -or -not (Test-Path $key)) {
  & $Python (Join-Path $PSScriptRoot "certs.py")
  if ($LASTEXITCODE -ne 0) { throw "Certificate setup failed." }
}

$storage = Join-Path $env:LOCALAPPDATA "DataNeat\excel-addin\storage"
New-Item -ItemType Directory -Force -Path $storage | Out-Null

$env:PYTHONPATH = Join-Path $repo "backend"
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:STATIC_DIR = Join-Path $addin "taskpane"
$env:STORAGE_DIR = $storage
$env:MAX_UPLOAD_MB = "60"
$env:MAX_UPLOAD_ROWS = "1000000"
$env:MAX_UPLOAD_COLUMNS = "100"
$env:MAX_WORKFLOW_CELLS = "3000000"
$env:ADDIN_MAX_CELLS = "3000000"
$env:ADDIN_MAX_UPLOAD_MB = "60"
$env:ANALYSIS_SYNC_CELLS = "0"
$env:AI_ASSIST_ENABLED = "false"
$env:COOKIE_SECURE = "false"
$env:CORS_ORIGINS = "https://localhost:9443"
# The web-tunnel helper serves the same task pane from a temporary
# *.trycloudflare.com origin; allow only that host pattern, not arbitrary sites.
$env:CORS_ORIGIN_REGEX = "https://([a-z0-9-]+\.)?trycloudflare\.com"
# The local companion is single-user on localhost; do not inherit hosted auth.
$env:SUPABASE_URL = ""
$env:SUPABASE_PUBLISHABLE_KEY = ""
$env:SUPABASE_SERVICE_ROLE_KEY = ""
$env:STORAGE_SIGNING_KEY = ""

Write-Host ""
Write-Host "DataNeat Excel add-in companion" -ForegroundColor Green
Write-Host "Task pane: https://localhost:9443/taskpane.html"
Write-Host "Manifest:  $addin\manifest.xml"
Write-Host ""
Write-Host "Keep this window open while using Excel. Press Ctrl+C to stop."
Write-Host ""

& $Python -m uvicorn app.main:app `
  --host 127.0.0.1 `
  --port 9443 `
  --ssl-keyfile $key `
  --ssl-certfile $cert
