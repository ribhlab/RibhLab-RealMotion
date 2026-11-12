# Install the FREE, locally executed LTXV 2B FP8 model + separate T5 XXL.
# PowerShell 5.1. Explicit, opt-in download only. NO cloud inference/API use.
# Based on official Lightricks and Comfy-Org model assets (Nov 2026).
param(
  [string]$ComfyRoot = 'C:\AI\ComfyUI_windows_portable'
)
$ErrorActionPreference = 'Stop'

$models = Join-Path $ComfyRoot 'ComfyUI\models'
if (-not (Test-Path $models -PathType Container)) {
  throw "ComfyUI models folder missing: $models. Set -ComfyRoot to the correct installation."
}
if (-not (Get-Command curl.exe -ErrorAction SilentlyContinue)) {
  throw 'Windows curl.exe missing. Please install/update Windows curl first.'
}
$drive = (Get-Item $models).PSDrive
if ($drive -and $drive.Free -lt 12GB) {
  throw "At least 12 GB disk space recommended for LTX model and T5 (and temporary downloads). Free: $([math]::Round($drive.Free/1GB,1)) GB"
}

function Download-Checked {
  param([string]$Folder,[string]$Name,[string]$Url,[string]$SHA256)
  New-Item -Path $Folder -ItemType Directory -Force | Out-Null
  $dest = Join-Path $Folder $Name
  $part = $dest + '.part'
  if (Test-Path $dest) {
    Write-Host "Checking existing file: $Name" -ForegroundColor Yellow
    if ((Get-FileHash -Path $dest -Algorithm SHA256).Hash -ieq $SHA256) {
      Write-Host "Already verified: $Name" -ForegroundColor Green
      return
    }
    throw "Existing $Name has a wrong SHA256. Not overwriting it. Move the bad file out of the folder and retry."
  }
  Write-Host "Downloading $Name; interrupted transfers can be resumed..." -ForegroundColor Cyan
  & curl.exe --fail --location --retry 6 --retry-delay 3 --continue-at - --output $part $Url
  if ($LASTEXITCODE -ne 0) {
    throw "curl failed for $Name (exit $LASTEXITCODE). Partial file kept at $part. Run the script again to resume."
  }
  Write-Host "Verifying SHA256 of $Name. This reads the entire downloaded file..." -ForegroundColor Yellow
  $actual = (Get-FileHash -Path $part -Algorithm SHA256).Hash
  if ($actual -ine $SHA256) {
    throw "SHA256 mismatch for $Name. Partial file not activated. Expected $SHA256; got $actual"
  }
  Move-Item -Path $part -Destination $dest
  Write-Host "Verified and installed: $dest" -ForegroundColor Green
}

Download-Checked -Folder (Join-Path $models 'checkpoints') -Name 'ltxv-2b-0.9.8-distilled-fp8.safetensors' `
  -Url 'https://huggingface.co/Lightricks/LTX-Video/resolve/main/ltxv-2b-0.9.8-distilled-fp8.safetensors' `
  -SHA256 'd6d8fa8ed3a98346787c2503ac80fb5d7cebcf80e356b79a2ba361fbadf97e15'

Download-Checked -Folder (Join-Path $models 'text_encoders') -Name 't5xxl_fp8_e4m3fn.safetensors' `
  -Url 'https://huggingface.co/Comfy-Org/stable-diffusion-3.5/resolve/main/text_encoders/t5xxl_fp8_e4m3fn.safetensors' `
  -SHA256 '7d330da4816157540d6bb7838bf63a0f02f573fc48ca4d8de34bb0cbfd514f09'

Write-Host ''
Write-Host 'Model and separate T5 successfully downloaded and verified.' -ForegroundColor Green
Write-Host 'Restart ComfyUI on the NVIDIA Windows PC. Then restart RealMotion and choose LTX 2B FP8.'
Write-Host 'This GPU has 6GB VRAM. Actual inference compatibility is not yet verified; errors may occur.'
