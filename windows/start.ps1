# RibhLab RealMotion - local-only Windows NVIDIA launcher.
# This launcher does not use Vercel, Replicate or a remote generation API.
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
Set-Location $project
Write-Host "====================================" -ForegroundColor Cyan
Write-Host "  RibhLab RealMotion - LOCAL GPU" -ForegroundColor Cyan
Write-Host "===================================="
Write-Host "Code: GitHub | GPU: your NVIDIA | Photos: local"
$nv = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if ($nv) {
  try {
    & nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
  } catch { Write-Warning "NVIDIA driver query failed. Update your GPU driver." }
} else {
  Write-Warning "nvidia-smi was not found. Check NVIDIA driver installation."
}
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
  throw "FFmpeg is missing. Install with: winget install --id Gyan.FFmpeg -e (then reopen this window)"
}
if (-not (Get-Command ffprobe -ErrorAction SilentlyContinue)) {
  throw "FFprobe is missing. Install FFmpeg full build and add it to PATH."
}
$venv = Join-Path $project '.venv\Scripts\python.exe'
if (-not (Test-Path $venv)) {
  $usePy = $false
  try { & py -3.11 --version *> $null; $usePy = ($LASTEXITCODE -eq 0) } catch {}
  if ($usePy) {
    & py -3.11 -m venv (Join-Path $project '.venv')
  } elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python -m venv (Join-Path $project '.venv')
  } else {
    throw "Python is missing. Install Python 3.11: winget install --id Python.Python.3.11 -e"
  }
  if ($LASTEXITCODE -ne 0) { throw "Failed creating Python virtual environment." }
}
$reqFile = Join-Path $project 'requirements.txt'
$requirementsHash = (Get-FileHash $reqFile -Algorithm SHA256).Hash
$marker = Join-Path $project '.venv\installed-requirements.sha256'
if (-not (Test-Path $marker) -or (Get-Content $marker -Raw).Trim() -ne $requirementsHash) {
  Write-Host "Installing Python dependencies (first run needs Internet)..." -ForegroundColor Yellow
  & $venv -m pip install -r $reqFile
  if ($LASTEXITCODE -ne 0) { throw "Python dependency installation failed." }
  Set-Content -Path $marker -Value $requirementsHash -Encoding ASCII
}
# Find an existing ComfyUI Portable, without requiring new GPU cloud services.
$candidates = @(
  $env:REALMOTION_COMFYUI_HOME,
  'C:\AI\ComfyUI_windows_portable',
  'C:\ComfyUI_windows_portable',
  (Join-Path $env:USERPROFILE 'Downloads\ComfyUI_windows_portable'),
  (Join-Path $env:USERPROFILE 'Desktop\ComfyUI_windows_portable'),
  (Join-Path $env:USERPROFILE 'Documents\ComfyUI_windows_portable')
) | Where-Object { $_ }
$comfyRoot = $null
foreach ($candidate in $candidates) {
  if (Test-Path (Join-Path $candidate 'ComfyUI\models')) { $comfyRoot = $candidate; break }
}
$env:COMFYUI_URL = 'http://127.0.0.1:8188'
$comfyRunning = $false
try {
  $null = Invoke-RestMethod -Uri ($env:COMFYUI_URL + '/system_stats') -TimeoutSec 2
  $comfyRunning = $true
} catch {}
if ($comfyRoot) {
  $env:REALMOTION_COMFYUI_MODELS_DIR = Join-Path $comfyRoot 'ComfyUI\models'
  Write-Host "ComfyUI: $comfyRoot" -ForegroundColor Cyan
  foreach ($spec in @(
     'unet\Wan2.2-TI2V-5B-Q2_K.gguf',
     'vae\wan2.2_vae.safetensors',
     'text_encoders\umt5_xxl_fp8_e4m3fn_scaled.safetensors'
  )) {
    if (-not (Test-Path (Join-Path $env:REALMOTION_COMFYUI_MODELS_DIR $spec))) {
      Write-Warning "Missing motion model: $spec"
    }
  }
  if (-not $comfyRunning) {
    $launch = Join-Path $comfyRoot 'run_nvidia_gpu.bat'
    if (Test-Path $launch) {
      Write-Host "Starting ComfyUI on your local NVIDIA GPU..."
      Start-Process -FilePath 'cmd.exe' -ArgumentList @('/k', ('"' + $launch + '"')) -WorkingDirectory $comfyRoot
    } else {
      Write-Warning "Run ComfyUI manually. Expected: run_nvidia_gpu.bat"
    }
  }
} elseif (-not $comfyRunning) {
  Write-Warning "ComfyUI not found. Install its Windows Portable NVIDIA version."
  Write-Host "https://docs.comfy.org/installation/comfyui_portable_windows"
  Write-Host "Or set REALMOTION_COMFYUI_HOME to the portable folder path."
}
$voice = Join-Path $project 'models\ar_JO-kareem-medium.onnx'
if (Test-Path $voice) {
  Write-Host "Offline Arabic Piper voice: installed." -ForegroundColor Green
} else {
  Write-Host "Optional: install Arabic offline voice via windows\setup_voice.ps1"
  Write-Host "Windows SAPI local voice is used automatically if Piper is absent."
}
Write-Host "Opening the local studio: http://127.0.0.1:8000" -ForegroundColor Green
Start-Process 'http://127.0.0.1:8000'
Write-Host "Keep this window open. Ctrl+C stops the studio."
& $venv -m uvicorn app:app --host 127.0.0.1 --port 8000
if ($LASTEXITCODE -ne 0) { throw "Local app failed to start." }
