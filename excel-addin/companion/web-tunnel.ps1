param(
  [int]$Port = 9443
)

$ErrorActionPreference = "Stop"
$addin = Split-Path $PSScriptRoot -Parent
$cert = Join-Path $PSScriptRoot "certs\cert.pem"
$tools = Join-Path $env:LOCALAPPDATA "DataNeat\excel-addin\tools"
$cf = Join-Path $tools "cloudflared.exe"
$log = Join-Path $tools "web-tunnel.log"
$err = "$log.err"

if (-not (Test-Path $cert)) {
  throw "Start .\companion\run.ps1 in another window first; the localhost certificate is missing."
}

$tokenFile = Join-Path $addin "generated\addin-token.txt"
if (-not (Test-Path $tokenFile)) {
  throw "Start .\companion\run.ps1 in another window first; the add-in token was not generated."
}
$addinToken = (Get-Content $tokenFile -Raw).Trim()
if (-not $addinToken) { throw "The add-in token file is empty; restart the companion." }

try {
  $code = & curl.exe -k -s -o NUL -w "%{http_code}" "https://localhost:$Port/api/health"
  if ($LASTEXITCODE -ne 0 -or "$code" -notmatch "200") { throw "Health check returned $code." }
} catch {
  throw "The DataNeat companion is not running. Start .\companion\run.ps1 in another window, then run this script again."
}

New-Item -ItemType Directory -Force -Path $tools | Out-Null
if (-not (Test-Path $cf)) {
  Write-Host "Downloading cloudflared (one time)…"
  Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" -OutFile $cf
}

if (Test-Path $log) { Remove-Item $log -Force }
$process = Start-Process -FilePath $cf `
  -ArgumentList "tunnel", "--url", "https://localhost:$Port", "--no-tls-verify", "--no-autoupdate" `
  -RedirectStandardOutput $log -RedirectStandardError $err `
  -PassThru -WindowStyle Hidden

$url = $null
for ($i = 0; $i -lt 40; $i++) {
  Start-Sleep -Seconds 1
  $text = ""
  if (Test-Path $err) { $text += Get-Content $err -Raw -ErrorAction SilentlyContinue }
  if (Test-Path $log) { $text += Get-Content $log -Raw -ErrorAction SilentlyContinue }
  $match = [regex]::Match($text, "https://[a-z0-9-]+\.trycloudflare\.com")
  if ($match.Success) { $url = $match.Value; break }
  if ($process.HasExited) { break }
}

if (-not $url) {
  if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force }
  throw "Could not create the Cloudflare tunnel. See $err for details."
}

$generated = Join-Path $addin "generated"
New-Item -ItemType Directory -Force -Path $generated | Out-Null
$manifestPath = Join-Path $generated "manifest.web.xml"
$manifest = Get-Content (Join-Path $addin "manifest.xml") -Raw
$manifest = $manifest.Replace("https://localhost:9443", $url)
$manifest = $manifest.Replace("$url/taskpane.html", "$url/taskpane.html?token=$addinToken")
[System.IO.File]::WriteAllText($manifestPath, $manifest, [System.Text.UTF8Encoding]::new($false))

Write-Host ""
Write-Host "DataNeat for Excel on the web" -ForegroundColor Green
Write-Host "Public task pane: $url/taskpane.html (token required)"
Write-Host "Manifest:         $manifestPath"
Write-Host ""
Write-Host "Keep this window open while testing. Press Ctrl+C to stop the tunnel."
Write-Host "The URL changes each time this script runs; upload the newly generated manifest again."
Write-Host ""
Write-Host "Security: the tunnel is temporary and the API requires the generated add-in token." -ForegroundColor Yellow
Write-Host "The token is stored in excel-addin\generated\addin-token.txt. Stop the tunnel when done and do not share it." -ForegroundColor Yellow
Write-Host ""

try {
  Wait-Process -Id $process.Id
} finally {
  if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force }
}
