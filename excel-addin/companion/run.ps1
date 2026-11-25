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
$generated = Join-Path $addin "generated"
New-Item -ItemType Directory -Force -Path $generated | Out-Null

# Per-installation access token. It is persisted so the local manifest stays
# usable across launches; delete generated\addin-token.txt and restart to rotate.
$tokenFile = Join-Path $generated "addin-token.txt"
if (Test-Path $tokenFile) {
  $addinToken = (Get-Content $tokenFile -Raw).Trim()
} else {
  $bytes = New-Object byte[] 32
  $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
  try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
  $addinToken = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
  [System.IO.File]::WriteAllText($tokenFile, $addinToken, [System.Text.UTF8Encoding]::new($false))
}
if (-not $addinToken) { throw "Could not create the add-in access token." }

$manifestSource = Get-Content (Join-Path $addin "manifest.xml") -Raw
$localManifest = $manifestSource.Replace(
  "https://localhost:9443/taskpane.html",
  "https://localhost:9443/taskpane.html?token=$addinToken"
)
$localManifestPath = Join-Path $generated "manifest.local.xml"
[System.IO.File]::WriteAllText($localManifestPath, $localManifest, [System.Text.UTF8Encoding]::new($false))

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
$env:ADDIN_TOKEN = $addinToken
# The companion is a local desktop helper with its own token, not the hosted app.
# Never set REQUIRE_AUTH here, and never expose it without the token.
$env:REQUIRE_AUTH = "false"
# The local companion is single-user on localhost; do not inherit hosted auth.
$env:SUPABASE_URL = ""
$env:SUPABASE_PUBLISHABLE_KEY = ""
$env:SUPABASE_SERVICE_ROLE_KEY = ""
$env:STORAGE_SIGNING_KEY = ""

Write-Host ""
Write-Host "DataNeat Excel add-in companion" -ForegroundColor Green
Write-Host "Task pane: https://localhost:9443/taskpane.html?token=..."
Write-Host "Local manifest: $localManifestPath"
Write-Host ""
Write-Host "Use the generated local manifest (not manifest.xml) for sideloading."
Write-Host "Keep this window open while using Excel. Press Ctrl+C to stop."
Write-Host ""

& $Python -m uvicorn app.main:app `
  --host 127.0.0.1 `
  --port 9443 `
  --ssl-keyfile $key `
  --ssl-certfile $cert
