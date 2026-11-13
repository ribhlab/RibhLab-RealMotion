# Optional one-time TRUE LIP SYNC installer. MuseTalk 1.5, isolated Python 3.10.
# It never uploads user photos, sends a video to a service, or uses Replicate.
param([switch]$SkipWeights)
$ErrorActionPreference='Stop'
$project = Split-Path -Parent $PSScriptRoot
$mu = Join-Path $project 'external\MuseTalk'
$venv = Join-Path $mu '.venv\Scripts\python.exe'
Write-Host 'RealMotion: LOCAL MuseTalk 1.5 lip-sync setup' -ForegroundColor Cyan
Write-Host 'MuseTalk model and dependency licenses apply to generated media.'
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  throw 'Git missing: winget install --id Git.Git -e; reopen PowerShell'
}
$pyOK = $false
try {
  & py -3.10 --version *> $null
  $pyOK = $LASTEXITCODE -eq 0
} catch {}
if (-not $pyOK) {
  throw 'Separate Python 3.10 required for MuseTalk. Install: winget install --id Python.Python.3.10 -e'
}
if (-not (Test-Path (Join-Path $mu 'scripts\inference.py'))) {
  New-Item -ItemType Directory -Force -Path (Split-Path $mu) | Out-Null
  Write-Host 'Downloading official MIT-licensed MuseTalk source...'
  & git clone --depth 1 https://github.com/TMElyralab/MuseTalk.git $mu
  if ($LASTEXITCODE -ne 0) { throw 'MuseTalk git clone failed' }
}
if (-not (Test-Path $venv)) {
  & py -3.10 -m venv (Join-Path $mu '.venv')
  if ($LASTEXITCODE -ne 0) { throw 'Could not create isolated MuseTalk Python 3.10 environment' }
}
Set-Location $mu
Write-Host 'Installing CUDA PyTorch in isolated MuseTalk Python...'
& $venv -m pip install --upgrade pip wheel setuptools
if ($LASTEXITCODE -ne 0) { throw 'pip bootstrap failed' }
& $venv -m pip install 'torch==2.0.1' 'torchvision==0.15.2' 'torchaudio==2.0.2' --index-url 'https://download.pytorch.org/whl/cu118'
if ($LASTEXITCODE -ne 0) { throw 'MuseTalk CUDA PyTorch installation failed' }
Write-Host 'Installing MuseTalk requirements...'
& $venv -m pip install -r (Join-Path $mu 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'MuseTalk requirements failed; review Windows compatibility' }
& $venv -m pip install 'openmim'
if ($LASTEXITCODE -ne 0) { throw 'OpenMIM installation failed' }
foreach ($pkg in @('mmengine', 'mmcv==2.0.1', 'mmdet==3.1.0', 'mmpose==1.1.0')) {
  Write-Host "Installing $pkg..."
  & $venv -m mim install $pkg
  if ($LASTEXITCODE -ne 0) {
    throw ("MuseTalk dependency "+$pkg+" could not install on this Windows system. " +
      "This can require a compatible Windows CUDA wheel or MSVC Build Tools. See LIPSYNC_SETUP.md.")
  }
}
Write-Host 'Checking CUDA support...' -ForegroundColor Yellow
& $venv -c 'import torch; print("CUDA available:", torch.cuda.is_available()); print("PyTorch:", torch.__version__)'
if ($LASTEXITCODE -ne 0) { throw 'MuseTalk torch verification failed' }
if (-not $SkipWeights) {
  Write-Host 'Downloading official MuseTalk 1.5 + supporting models (one-time only)...'
  & $venv (Join-Path $PSScriptRoot 'download_musetalk_weights.py') (Join-Path $mu 'models')
  if ($LASTEXITCODE -ne 0) { throw 'MuseTalk model downloads incomplete. Rerun setup to resume.' }
}
Write-Host 'MuseTalk installed. Restart RealMotion and enable true lip sync in the UI.' -ForegroundColor Green
