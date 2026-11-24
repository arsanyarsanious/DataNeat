param(
  [string]$Python = ""
)

$ErrorActionPreference = "Stop"
$addin = Split-Path $PSScriptRoot -Parent
$venv = Join-Path $addin ".venv"

if (-not $Python) {
  if (Get-Command py -ErrorAction SilentlyContinue) { $Python = "py" }
  elseif (Get-Command python -ErrorAction SilentlyContinue) { $Python = "python" }
  else { throw "Python 3.12 (64-bit) is required." }
}

if (-not (Test-Path (Join-Path $venv "Scripts\python.exe"))) {
  Write-Host "Creating add-in Python environment…"
  if ($Python -eq "py") {
    & py -3.12 -m venv $venv 2>$null
    if ($LASTEXITCODE -ne 0) {
      Write-Host "Python 3.12 was not found; trying the default Python. This preview is tested on 3.12." -ForegroundColor Yellow
      & py -3 -m venv $venv
    }
  }
  else { & $Python -m venv $venv }
}

$venvPython = Join-Path $venv "Scripts\python.exe"
Write-Host "Installing local engine dependencies (first run can take a few minutes)…"
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r (Join-Path $PSScriptRoot "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }

Write-Host "Generating and trusting the localhost certificate…"
& $venvPython (Join-Path $PSScriptRoot "certs.py")
if ($LASTEXITCODE -ne 0) { throw "Certificate setup failed." }

Write-Host ""
Write-Host "Setup complete. Start the companion with:" -ForegroundColor Green
Write-Host "  .\companion\run.ps1" -ForegroundColor Cyan
