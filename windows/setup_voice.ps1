# One-time optional offline Arabic voice installation (Piper).
# Internet is used only for downloading software + model files. No runtime cloud API.
$ErrorActionPreference='Stop'
$project = Split-Path -Parent $PSScriptRoot
$python = Join-Path $project '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { throw 'Run Start-RealMotion.bat once before voice setup.' }
$folder = Join-Path $project 'models'
New-Item -ItemType Directory -Force -Path $folder | Out-Null
Write-Host 'Installing local Piper text-to-speech package...'
& $python -m pip install 'piper-tts>=1.2,<2'
if ($LASTEXITCODE -ne 0) { throw 'Piper Python package installation failed.' }
$base = 'https://huggingface.co/rhasspy/piper-voices/resolve/main/ar/ar_JO/kareem/medium/'
$files = @('ar_JO-kareem-medium.onnx','ar_JO-kareem-medium.onnx.json')
foreach ($file in $files) {
  $dest = Join-Path $folder $file
  if (Test-Path $dest) {
    Write-Host "Already present: $file"
    continue
  }
  Write-Host "Downloading Arabic voice: $file"
  $temp = $dest + '.download'
  Invoke-WebRequest -Uri ($base + $file) -OutFile $temp -MaximumRedirection 8
  if ((Get-Item $temp).Length -lt 1024) { Remove-Item $temp -ErrorAction SilentlyContinue; throw "Voice download failed: $file" }
  Move-Item -Force $temp $dest
}
$hash = (Get-FileHash (Join-Path $folder 'ar_JO-kareem-medium.onnx') -Algorithm SHA256).Hash.ToLower()
if ($hash -ne '9e95cab07b679da603bba17c4dec7ab3111320571964ee95c0379603c086491e') {
  throw 'Arabic voice SHA256 mismatch. Do not use this model file; download again from the official repository.'
}
Write-Host 'Local Arabic Piper voice is ready! No Internet needed for future speech generation.' -ForegroundColor Green
