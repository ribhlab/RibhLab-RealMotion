# One-time local model installer for Wan 2.2 5B Q2 GGUF image-to-video.
# Official files only; NO paid GPU service, no keys, no upload of personal photos.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
  throw 'Run Start-RealMotion.bat first to create the Python environment.'
}
Write-Host 'RibhLab RealMotion - Wan 2.2 motion model installer' -ForegroundColor Cyan
$locations = @(
  $env:REALMOTION_COMFYUI_HOME,
  'C:\AI\ComfyUI_windows_portable',
  'C:\ComfyUI_windows_portable',
  (Join-Path $env:USERPROFILE 'Downloads\ComfyUI_windows_portable'),
  (Join-Path $env:USERPROFILE 'Desktop\ComfyUI_windows_portable'),
  (Join-Path $env:USERPROFILE 'Documents\ComfyUI_windows_portable')
) | Where-Object { $_ }
$comfy = $null
foreach ($candidate in $locations) {
  if (Test-Path (Join-Path $candidate 'ComfyUI\models')) { $comfy = $candidate; break }
}
if (-not $comfy) {
  $comfy = (Read-Host 'Enter full path of the ComfyUI_windows_portable folder').Trim('"')
  if (-not (Test-Path (Join-Path $comfy 'ComfyUI\models'))) { throw 'ComfyUI portable models folder not found.' }
}
$modelRoot = Join-Path $comfy 'ComfyUI\models'
$drive = [System.IO.Path]::GetPathRoot((Resolve-Path $modelRoot).Path)
$freeGB = [math]::Round((Get-PSDrive -Name $drive.Substring(0,1)).Free/1GB,1)
Write-Host "ComfyUI models: $modelRoot"
Write-Host "Free disk space: $freeGB GB"
if ($freeGB -lt 20) {
  Write-Warning '20 GB or more free disk space is recommended for downloading Wan 2.2 Q2 GGUF weights.'
  $override = Read-Host 'Continue despite limited free space? Type YES to proceed'
  if ($override -ne 'YES') { exit 1 }
}
Write-Host 'One-time download: about 10 GB from the official Hugging Face model repositories.'
Write-Host 'After download, generation uses your own GPU with no paid API.'
$consent = Read-Host 'Download now? Type YES to continue'
if ($consent -ne 'YES') { Write-Host 'Cancelled. No models downloaded.'; exit 0 }
& $python -m pip install 'huggingface_hub>=0.30,<2'
if ($LASTEXITCODE -ne 0) { throw 'Cannot install Hugging Face downloader.' }
& $python (Join-Path $PSScriptRoot 'download_models.py') $modelRoot
if ($LASTEXITCODE -ne 0) { throw 'Model download failed. You can rerun it to resume.' }
Write-Host 'Wan 2.2 motion models installed. Start RealMotion again.' -ForegroundColor Green
