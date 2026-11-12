# RibhLab RealMotion — Windows NVIDIA 100% local (Darija)

RealMotion now uses **your NVIDIA GPU**. GitHub is for storing and updating the source code only. **No Replicate, no Vercel, no paid-per-video credits, no cloud GPU.** All private photos and rendered videos remain on the Windows computer.

## What is one-time vs offline?

The **first installation** requires an Internet connection to download Python packages, ComfyUI and AI model weights. Afterwards, video inference, local speech (Piper or Windows voice), and MP4 assembly can work **without Internet** if every required model is already installed. The local FastAPI server binds to 127.0.0.1 by default, not the public Internet.

> This is an experimental MVP. The code/logic can be tested without a GPU, but a real video render has **not yet been validated end-to-end** on your computer. The local test combines Wan 5B Q2 motion and a Piper speech soundtrack; it does not synchronize lips. Natural Darija pronunciation and facial identity are not guaranteed.

## Step 1 — hardware check

On Windows PowerShell:
```powershell
nvidia-smi
```

Check the GPU name and total VRAM. The ComfyUI Wan2.2 5B image-to-video workflow can work with **roughly 8 GB VRAM using offloading**, depending on CUDA/driver/system RAM, resolution and background applications. Talking S2V 14B is heavier and may require a high-VRAM GPU. If yours has only 6 GB or less, test a lower-memory workflow before assuming the default model will run.

## Step 2 — install prerequisites once

PowerShell:
```powershell
winget install --id Python.Python.3.11 -e
winget install --id Git.Git -e
winget install --id Gyan.FFmpeg -e
```
Reopen PowerShell after installation. Confirm `py -3.11 --version`, `ffmpeg -version` and `nvidia-smi`.

Install the **official ComfyUI Portable for NVIDIA**:
https://docs.comfy.org/installation/comfyui_portable_windows

Extract to `C:\AI\ComfyUI_windows_portable` if possible. The launcher also searches common Desktop, Documents and Downloads locations. Otherwise set `REALMOTION_COMFYUI_HOME` to your ComfyUI Portable directory before starting. Example (in PowerShell, current session only):

```powershell
$env:REALMOTION_COMFYUI_HOME = 'D:\AI\ComfyUI_windows_portable'
```

ComfyUI must be updated enough to include Wan2.2 core nodes `Wan22ImageToVideoLatent` and `WanSoundImageToVideo`.

## Step 3 — one-time download for Wan 5B Q2 GGUF (6 GB GPU test)

After downloading the project ZIP and launching `Start-RealMotion.bat` once, double-click `Install-Wan-Motion-Models.bat` and type `YES`. It installs exactly:

- `Wan2.2-TI2V-5B-Q2_K.gguf` (~1.85 GB) → `ComfyUI/models/unet/`
- `wan2.2_vae.safetensors` (~1.41 GB) → `ComfyUI/models/vae/`
- `umt5_xxl_fp8_e4m3fn_scaled.safetensors` (~6.74 GB) → `ComfyUI/models/text_encoders/`

The downloader verifies SHA256 hashes from the model publishers and can be rerun when interrupted. Do **not** use the earlier large FP16 model installation instructions. You already installed ComfyUI-GGUF on your NVIDIA Portable environment.

You need Internet for this one-time 10 GB model download, but there is **no paid model inference account or API key**.

## Step 4 — download the app, double click

Download the repository ZIP:
https://github.com/ribhlab/RibhLab-RealMotion/archive/refs/heads/main.zip

Extract it somewhere writable. Double-click **`Start-RealMotion.bat`**. The script:

- checks NVIDIA, FFmpeg and Python;
- installs local app dependencies into `.venv` on first launch;
- detects the ComfyUI Portable folder and launches `run_nvidia_gpu.bat` if needed;
- reports missing Wan model files;
- opens the **real local studio** at http://127.0.0.1:8000.

Keep its terminal open while rendering. The separate ComfyUI console must also stay open. For diagnostics:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\windows\diagnose.ps1
```

## Step 5 — optional offline Arabic voice (for photo-only talking scenes)

The default storyboard already has Moroccan Arabic dialogue. To generate its **synthetic voice offline** using free Piper Arabic models, run **`Install-Offline-Voice.bat`** once (after starting the launcher at least once), or use:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\windows\setup_voice.ps1
```

This downloads the Piper runtime and the `ar_JO-kareem-medium.onnx` Arabic model and config from the original publisher, verifies SHA-256, and saves them under `models/`. On later runs it generates speech **locally**, with no API key. That voice is Jordanian Arabic rather than Moroccan Darija and may pronounce some Darija phrases imperfectly. You can alternatively upload a recorded audio file to each talking scene. If Piper is absent, the program uses Windows SAPI voices available on the computer (quality varies and Arabic might not be installed). The first video+voice test does **not** require Wan S2V 14B: the voice is mixed into Wan 5B motion, without lip synchronization.

Voice model: https://huggingface.co/rhasspy/piper-voices/tree/main/ar/ar_JO/kareem/medium

## Step 6 — upload only your four hero images

Open **http://127.0.0.1:8000** on the Windows machine. For the first video+audio test **upload only the driver's photo** and press **«🎤🎬 جرّب 5 ثواني بالصورة والصوت»**. This uses the existing driver's dialogue as a synthetic Arabic voice, renders a genuine Wan GGUF motion clip, and combines voice + image as one MP4. Lips are NOT synchronized automatically. After this first test succeeds, upload the other three portraits and generate the full 30-second film. Your images, dialogue and renders are stored under `local_data/` on your own disk. They are excluded by `.gitignore`, so they are **not uploaded to GitHub**.

**Important:** The GitHub Pages link is only the **download portal**. GitHub Pages has no access to your NVIDIA GPU. Opening `127.0.0.1:8000` on your phone opens the phone itself, not your computer. Use the browser on the same Windows PC for the default secure configuration. No public ports, tunnels or external services are enabled.

If generation fails, read the error in the studio and the ComfyUI window. The code never silently swaps real AI motion for a slideshow.


## Split RealMotion between two Windows computers (MacBook Boot Camp + NVIDIA PC)

Optional LAN offload supports **Firefly-style Studio clips of 1–10 seconds**.
The NVIDIA PC still performs Wan/ComfyUI AI inference; a second Windows PC
(MacBook Pro Intel i9 / Radeon Pro 560X) performs FFmpeg normalization,
optional local Arabic TTS, and final MP4 muxing. This **does not pool VRAM**,
speed up ComfyUI's diffusion step, enable Radeon CUDA, or guarantee the
6 GB NVIDIA GPU can render Wan successfully. Long-form/storyboard processing
remains on the main PC in this initial LAN worker version.

Both computers must be on the **same trusted private LAN**; use no public port
forwarding, VPN exposure, or Internet hosting. The worker uses a per-installation
secret token but plain HTTP on the local LAN, not TLS.

1. **MacBook running Windows:** Install Python 3.11 and FFmpeg (including
   ffprobe); clone/download the **same updated repo**, then run
   `Start-Remote-Worker.bat`. It installs Python requirements, generates
   `.worker_token` locally, and starts the CPU worker on port 8787. No ComfyUI,
   NVIDIA GPU, or Wan weights needed on this computer. Optional Arabic Piper
   voice can be installed via `Install-Offline-Voice.bat` on this MacBook.
2. In a MacBook PowerShell, find its local IPv4: `ipconfig`. Read your private
   token using `Get-Content .worker_token` **locally**; never paste the
   secret into ChatGPT, GitHub, a screenshot, or a public message.
3. On the MacBook, allow inbound TCP **8787 from LocalSubnet only** on the
   **Private** Windows firewall profile (PowerShell running as admin):
   ```powershell
   New-NetFirewallRule -DisplayName 'RibhLab LAN Worker' -Direction Inbound -Protocol TCP -LocalPort 8787 -RemoteAddress LocalSubnet -Profile Private -Action Allow
   ```
   Confirm your home Wi-Fi or Ethernet is configured as a Private network.
4. On the **NVIDIA PC**, first test reachability from PowerShell:
   ```powershell
   Test-NetConnection 192.168.1.50 -Port 8787
   ```
   Replace `192.168.1.50` with the actual MacBook IPv4. A successful TCP test
   confirms the machines can communicate, not that video rendering works.
5. In the **same NVIDIA PC PowerShell** window used to launch RealMotion:
   ```powershell
   $env:REALMOTION_WORKER_URL = 'http://192.168.1.50:8787'
   $env:REALMOTION_WORKER_TOKEN = '<your private token from the MacBook>'
   cd C:\AI\RibhLab-RealMotion
   .\Start-RealMotion.bat
   ```
   Substitute the real IPv4 and token. This token stays in the local process
   environment; do not put it into a public repository. The launcher inherits
   these variables. Keep ComfyUI running on the NVIDIA computer.

6. Upload a photo to `http://127.0.0.1:8000` on the NVIDIA PC and
   generate a 3-second clip. When its ComfyUI motion finishes, the clip is
   sent to the MacBook worker and the resulting MP4 returned to the main
   PC's local results folder. For speaking narration, include
   `الكلام: النص المنطوق هنا` in the prompt and enable voice.

If the worker is configured but unreachable, RealMotion reports a genuine
error instead of pretending it offloaded successfully. To return to local
processing, stop and restart RealMotion **without** the two worker environment
variables. Do not expose port 8787 on the Internet.


## Debugging and cancelling a stuck generation (new UI)

The Studio now includes a **Cancel generation** button, a stage-based progress
bar, an elapsed timer, a MacBook health indicator, and a copyable **Logs**
panel. ComfyUI websocket events report **actual sampling step counts** when
available; the overall 0–100% percentage is an approximate stage-weighted
display, **not** a precise ETA or a guarantee that the GPU can load Wan.

The main RealMotion process stores logs in
`local_data/job_logs/<job-id>.log`; the browser button copies the current log.
If a job is cancelled during the NVIDIA inference, RealMotion attempts to
remove its queued prompt or interrupt its own active ComfyUI prompt. During
FFmpeg or voice synthesis it cancels at the next safe point; it does **not**
promise instantaneous termination of a running subprocess. The MacBook shows
`received`, `encoding`, `voice`, `mixing`, or `done` only if both
computers use the latest worker code.

### Upgrade both Windows computers

**MacBook first:** In its running worker window press Ctrl+C. In a separate
PowerShell window, update its copy of the repo:

```powershell
git -C "C:\Users\ram\RibhLab-RealMotion" pull --ff-only origin main
```

Restart the worker by double-clicking
`C:\Users\ram\RibhLab-RealMotion\Start-Remote-Worker.bat`.
The local `.worker_token` secret stays unchanged and must **never** be pasted
into a chat, screenshot, log, or committed to Git.

**NVIDIA PC:** If an earlier generation is still executing, use ComfyUI's
native Interrupt (only when it is *your* running job); then stop the old
RealMotion window using Ctrl+C. Pull:

```powershell
git -C "C:\AI\RibhLab-RealMotion" pull --ff-only origin main
```

Start RealMotion with its existing local MacBook pairing environment in the
same PowerShell session. If you opened a new PowerShell, re-enter the worker
URL and token locally, without sharing the token online:

```powershell
$env:REALMOTION_WORKER_URL='http://192.168.1.2:8787'
$secret=Read-Host 'MacBook worker token' -AsSecureString
$env:REALMOTION_WORKER_TOKEN=([System.Net.NetworkCredential]::new('',$secret)).Password
& 'C:\AI\RibhLab-RealMotion\Start-RealMotion.bat'
```

If the MacBook IP changed, replace 192.168.1.2 with its current private IPv4.
Hard-refresh the Studio browser tab (Ctrl+Shift+R). The diagnostic panel will
show whether the worker is connected and authenticated; a successful
`TcpTestSucceeded` alone does not prove the token is correct.

Make the first test a **3-second video with voice OFF**, then try Arabic voice.
For Arabic speech on the MacBook, install its optional Piper voice there; an
English-only Windows SAPI installation may otherwise mispronounce Arabic. This
lightweight workflow overlays a soundtrack and **does not lip-sync mouth
movements**, even if the prompt asks for lip synchronization.



## RealMotion Studio Pro — new three-pane interface and quality modes

This UI uses a **Firefly-inspired creative-workbench structure**, not Adobe branding
or any representation that Adobe's cloud model is used. The right-side inspector
shows real MacBook status, cancellation, progress and copyable logs. The main
canvas previews the entire reference image with `object-fit: contain`. The
settings pane offers real, wired controls:

- **Wan 2.2 AI Motion:** actual image-to-video inference on NVIDIA. The
  current Q2 GGUF is designed for 6 GB experimental use; it will not match the
  quality or compute budget of Adobe Firefly cloud video generation. Camera
  presets are *text hints* and do not guarantee exact camera movement.
- **Stable Food — source preserving:** transparent procedural steam over
  the original image, rendered using Pillow/FFmpeg on the local computer. It
  keeps tagine ingredients stable because it does not regenerate them. It is
  **not neural image-to-video**; walking, speaking, physical interactions and
  real lip-sync are not provided by this mode.
- Automatic **landscape 1280x720, portrait 720x1280 or square 960x960**
  finishing. Wan uses lower resolution latents matching the source orientation:
  landscape 512x288, portrait 288x512, square 384x384. Upscaling improves
  container resolution, **not** the original AI model's real details.
- Camera direction can be used with Wan as a prompt modifier. Disabled in
  Stable Food mode (it deliberately keeps the shot fixed).
- 3/5/8-second clips, optional voice soundtrack, 10-minute experimental
  multi-shot AI mode (first reference sets the output orientation).

The MacBook must be updated too because its processing endpoint now accepts
`resolution` to finish landscape/square videos without forcing 720x1280.
Stop the previous server before updating to avoid port 8787 conflicts.

### One-time upgrade from both Windows computers

First update/restart the MacBook worker (its personal secret file remains
unchanged), then update/restart the NVIDIA host:

```powershell
# MacBook, after Ctrl+C in its worker window:
git -C "C:\Users\ram\RibhLab-RealMotion" pull --ff-only origin main
& 'C:\Users\ram\RibhLab-RealMotion\Start-Remote-Worker.bat'
```

```powershell
# NVIDIA host, after stopping the old main app window:
git -C "C:\AI\RibhLab-RealMotion" pull --ff-only origin main
# Configure REALMOTION_WORKER_URL and REALMOTION_WORKER_TOKEN in this session.
& 'C:\AI\RibhLab-RealMotion\Start-RealMotion.bat'
```

Hard-refresh Chrome at http://127.0.0.1:8000 (Ctrl+Shift+R) to load
`firefly-studio-2` UI assets. Choose Stable Food for the tagine clip and
Wan AI for facial or body motion. Never paste the MacBook token into chat/logs.

