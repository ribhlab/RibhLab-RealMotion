# Local offline diagnostics - no token and no data uploads.
$ErrorActionPreference='Continue'
$project = Split-Path -Parent $PSScriptRoot
Write-Host '=== RibhLab RealMotion - GPU and software check ==='
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
  & nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
} else { Write-Warning 'NVIDIA tool not detected' }
if (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
  Write-Host "FFmpeg: installed"
} else { Write-Warning 'FFmpeg: missing' }
$python = Join-Path $project '.venv\Scripts\python.exe'
if (Test-Path $python) { & $python --version } else { Write-Warning 'Python virtual env: missing; launch Start-RealMotion.bat first' }
foreach ($port in @(8000,8188)) {
  try {
    $url = if ($port -eq 8000) { "http://127.0.0.1:$port/api/health" } else { "http://127.0.0.1:$port/system_stats" }
    $null = Invoke-RestMethod -Uri $url -TimeoutSec 3
    Write-Host "Port $port : reachable" -ForegroundColor Green
  } catch { Write-Warning "Port $port : offline" }
}
Write-Host 'If ComfyUI is offline, inspect its NVIDIA console window.'
