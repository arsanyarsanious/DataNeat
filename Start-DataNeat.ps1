param([switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$mutex = [Threading.Mutex]::new($false, 'Local\DataNeatLauncher')
$owned = $mutex.WaitOne(0)
if (-not $owned) { $mutex.Dispose(); exit 0 }
$log = Join-Path $PSScriptRoot 'dataneat-startup.log'
function Test-DockerReady {
    $ErrorActionPreference = 'Continue'
    & docker info *> $null
    return $LASTEXITCODE -eq 0
}
try {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw 'Docker Desktop is required. Install it from docker.com, then run Start DataNeat again.'
    }
    if (-not (Test-DockerReady)) {
        if ($CheckOnly) { throw 'Docker is not running.' }
        $desktop = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
        if (-not (Test-Path -LiteralPath $desktop)) { throw 'Start Docker Desktop, then run Start DataNeat again.' }
        Start-Process -FilePath $desktop -WindowStyle Hidden
        $deadline = (Get-Date).AddMinutes(2)
        do {
            Start-Sleep -Seconds 3
            $dockerReady = Test-DockerReady
        } until ($dockerReady -or (Get-Date) -gt $deadline)
        if (-not $dockerReady) { throw 'Docker did not become ready. Open Docker Desktop and check its status.' }
    }
    if (-not $CheckOnly) {
        Push-Location -LiteralPath $PSScriptRoot
        try {
            & docker compose -p dataneat up -d --build backend frontend *> $log
            if ($LASTEXITCODE -ne 0) { throw "DataNeat could not start. See $log" }
        } finally { Pop-Location }
    }
    $ready = $false
    $deadline = (Get-Date).AddMinutes(2)
    do {
        try {
            $health = Invoke-RestMethod -Uri 'http://localhost:3000/api/health' -TimeoutSec 5
            $ready = $health.status -eq 'ok'
        } catch { $ready = $false }
        if (-not $ready) { Start-Sleep -Seconds 2 }
    } until ($ready -or (Get-Date) -gt $deadline)
    if (-not $ready) { throw "DataNeat did not become ready. Check Docker and $log" }
    if ($CheckOnly) { Write-Output 'DataNeat is ready at http://localhost:3000/' }
    else { Start-Process 'http://localhost:3000/' }
} catch {
    $_.Exception.Message | Out-File -LiteralPath $log -Append -Encoding utf8
    if ($CheckOnly) { Write-Error $_; exit 1 }
    Add-Type -AssemblyName System.Windows.Forms
    [Windows.Forms.MessageBox]::Show($_.Exception.Message, 'DataNeat startup') | Out-Null
} finally {
    if ($owned) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
