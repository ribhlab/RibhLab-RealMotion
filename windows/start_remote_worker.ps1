# Run on a secondary Windows PC. No NVIDIA/ComfyUI installation is required.
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
Set-Location $project
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue) -or -not (Get-Command ffprobe -ErrorAction SilentlyContinue)) {
  throw "Install FFmpeg first: winget install --id Gyan.FFmpeg -e ; reopen PowerShell."
}
$venv = Join-Path $project '.venv\Scripts\python.exe'
if (-not (Test-Path $venv)) {
  $python = $null
  foreach ($version in @('3.12', '3.11')) {
    try {
      & py "-$version" --version *> $null
      if ($LASTEXITCODE -eq 0) { $python = $version; break }
    } catch {}
  }
  if ($python) {
    Write-Host "Creating worker environment with Python $python..." -ForegroundColor Cyan
    & py "-$python" -m venv (Join-Path $project '.venv')
  } elseif (Get-Command python -ErrorAction SilentlyContinue) {
    Write-Host "Creating worker environment with installed Python..." -ForegroundColor Cyan
    & python -m venv (Join-Path $project '.venv')
  } else {
    throw "Python is missing. Install Python 3.11 or 3.12."
  }
  if ($LASTEXITCODE -ne 0) { throw "Failed creating the Python environment." }
}
$reqFile = Join-Path $project 'requirements.txt'
$hash = (Get-FileHash $reqFile -Algorithm SHA256).Hash
$marker = Join-Path $project '.venv\installed-requirements.sha256'
if (-not (Test-Path $marker) -or (Get-Content $marker -Raw).Trim() -ne $hash) {
  & $venv -m pip install -r $reqFile
  if ($LASTEXITCODE -ne 0) { throw "Installing the worker requirements failed." }
  Set-Content -Path $marker -Value $hash -Encoding ASCII
}
$secretFile = Join-Path $project '.worker_token'
if (-not (Test-Path $secretFile)) {
  $secret = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
  Set-Content -Path $secretFile -Value $secret -Encoding ASCII
}
$env:REALMOTION_WORKER_TOKEN = (Get-Content $secretFile -Raw).Trim()
if ($env:REALMOTION_WORKER_TOKEN.Length -lt 32) { throw "The worker token must be 32 characters or longer." }
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  RibhLab RealMotion - MACBOOK LAN WORKER" -ForegroundColor Cyan
Write-Host "============================================"
Write-Host "This PC processes MP4 and audio. It does not generate AI video."
Write-Host "Port: 8787 | Protocol: HTTP on trusted local LAN only"
Write-Host "Worker token saved privately in: $secretFile" -ForegroundColor Yellow
Write-Host "Never paste the token in a public chat or commit it to GitHub."
Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
  Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254*' } |
  Select-Object InterfaceAlias, IPAddress | Format-Table -AutoSize
Write-Host "Keep this window open; Ctrl+C stops the worker." -ForegroundColor Green
& $venv -m uvicorn remote_worker:app --host 0.0.0.0 --port 8787
if ($LASTEXITCODE -ne 0) { throw "Worker failed to start." }
