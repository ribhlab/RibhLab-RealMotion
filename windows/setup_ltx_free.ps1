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

# Exactly one installer process should run. Stop an older sequential setup
# with Ctrl+C before starting this version, otherwise two curl processes might
# modify the same .part file simultaneously.
$lockPath = Join-Path $PSScriptRoot '.setup_ltx_free.lock'
try {
  $lock = [System.IO.File]::Open($lockPath,
    [System.IO.FileMode]::OpenOrCreate,
    [System.IO.FileAccess]::ReadWrite,
    [System.IO.FileShare]::None)
} catch {
  throw 'Another LTX setup may be running. Stop it before starting a new installer.'
}

$downloads = @(
  @{
    Id='LTX'
    Folder=(Join-Path $models 'checkpoints')
    Name='ltxv-2b-0.9.8-distilled-fp8.safetensors'
    Url='https://huggingface.co/Lightricks/LTX-Video/resolve/main/ltxv-2b-0.9.8-distilled-fp8.safetensors'
    SHA256='d6d8fa8ed3a98346787c2503ac80fb5d7cebcf80e356b79a2ba361fbadf97e15'
  },
  @{
    Id='T5'
    Folder=(Join-Path $models 'text_encoders')
    Name='t5xxl_fp8_e4m3fn.safetensors'
    Url='https://huggingface.co/Comfy-Org/stable-diffusion-3.5/resolve/main/text_encoders/t5xxl_fp8_e4m3fn.safetensors'
    SHA256='7d330da4816157540d6bb7838bf63a0f02f573fc48ca4d8de34bb0cbfd514f09'
  }
)
$jobs = @()
try {
  Write-Host 'Starting TWO free model downloads in parallel (shared internet bandwidth).' -ForegroundColor Cyan
  Write-Host 'Previous .part files are resumed; existing verified models are skipped.' -ForegroundColor Cyan

  foreach ($item in $downloads) {
    $jobs += Start-Job -Name ('RealMotion-' + $item.Id) -ArgumentList @(
      $item.Folder,$item.Name,$item.Url,$item.SHA256
    ) -ScriptBlock {
      param([string]$Folder,[string]$Name,[string]$Url,[string]$SHA256)
      $ErrorActionPreference = 'Stop'
      New-Item -ItemType Directory -Force -Path $Folder | Out-Null
      $dest = Join-Path $Folder $Name
      $part = $dest + '.part'
      if (Test-Path $dest) {
        if ((Get-FileHash -Path $dest -Algorithm SHA256).Hash -ieq $SHA256) {
          Write-Output "Already verified: $Name"
          return
        }
        throw "Existing $Name has wrong SHA256; it will not be overwritten."
      }

      # Each job owns a DIFFERENT file and .part path: no concurrent writes.
      & curl.exe --silent --show-error --fail --location --retry 6 --retry-delay 3 --continue-at - --output $part $Url
      if ($LASTEXITCODE -ne 0) {
        throw "curl failed downloading $Name (exit $LASTEXITCODE). Keep $part and re-run to resume."
      }

      $actual = (Get-FileHash -Path $part -Algorithm SHA256).Hash
      if ($actual -ine $SHA256) {
        throw "SHA256 mismatch for $Name. Not installing invalid .part file. Expected $SHA256; actual $actual."
      }
      Move-Item -LiteralPath $part -Destination $dest -ErrorAction Stop
      Write-Output "Verified and installed: $dest"
    }
  }

  # PowerShell 5.1 background jobs do not display curl's live progress.
  # Instead show how many MB each independent .part file contains.
  while (@($jobs | Where-Object { $_.State -eq 'Running' -or $_.State -eq 'NotStarted' }).Count -gt 0) {
    Start-Sleep -Seconds 15
    foreach ($item in $downloads) {
      $target = Join-Path $item.Folder $item.Name
      $part = $target + '.part'
      if (Test-Path $target) {
        Write-Host ("[{0}] File installed; checksum verified." -f $item.Id) -ForegroundColor Green
      } elseif (Test-Path $part) {
        $mb = [math]::Round((Get-Item -LiteralPath $part).Length / 1MB, 1)
        Write-Host ("[{0}] {1} MB downloaded or resumed" -f $item.Id, $mb)
      } else {
        Write-Host ("[{0}] Starting..." -f $item.Id)
      }
    }
  }

  $failures = @()
  foreach ($job in $jobs) {
    try {
      Receive-Job -Job $job -ErrorAction Stop | ForEach-Object { Write-Host $_ -ForegroundColor Green }
      if ($job.State -ne 'Completed') {
        $failures += "$($job.Name): $($job.State)"
      }
    } catch {
      $failures += "$($job.Name): $($_.Exception.Message)"
    }
  }
  if ($failures.Count -gt 0) {
    throw ("Some downloads failed. Existing .part files are kept for resuming:`n" + ($failures -join "`n"))
  }
} finally {
  foreach ($job in $jobs) {
    Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
  }
  if ($lock) { $lock.Dispose() }
}

Write-Host ''
Write-Host 'Model and separate T5 successfully downloaded and verified.' -ForegroundColor Green
Write-Host 'Restart ComfyUI on the NVIDIA Windows PC. Then restart RealMotion and choose LTX 2B FP8.'
Write-Host 'This GPU has 6GB VRAM. Actual inference compatibility is not yet verified; errors may occur.'
