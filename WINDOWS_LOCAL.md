# RibhLab RealMotion — Windows NVIDIA 100% local (Darija)

RealMotion now uses **your NVIDIA GPU**. GitHub is for storing and updating the source code only. **No Replicate, no Vercel, no paid-per-video credits, no cloud GPU.** All private photos and rendered videos remain on the Windows computer.

## What is one-time vs offline?

The **first installation** requires an Internet connection to download Python packages, ComfyUI and AI model weights. Afterwards, video inference, local speech (Piper or Windows voice), and MP4 assembly can work **without Internet** if every required model is already installed. The local FastAPI server binds to 127.0.0.1 by default, not the public Internet.

> This is an experimental MVP. The code/logic can be tested without a GPU, but a real video render has **not yet been validated end-to-end** on your computer. The 14B talking model needs substantially more VRAM than 5B motion, and natural Moroccan Darija pronunciation and stable identity are not guaranteed.

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

## Step 3 — download Wan 2.2 weights once

Use the official ComfyUI Wan 2.2 tutorial and model links:
https://docs.comfy.org/tutorials/video/wan/wan2_2

Place files in **ComfyUI/ComfyUI/models/** as follows:

| Model | Folder under ComfyUI/models/ | Purpose |
| --- | --- | --- |
| `wan2.2_ti2v_5B_fp16.safetensors` | `diffusion_models/` | Video motion |
| `wan2.2_vae.safetensors` | `vae/` | Video motion |
| `umt5_xxl_fp8_e4m3fn_scaled.safetensors` | `text_encoders/` | Shared text encoder |
| `wan2.2_s2v_14B_fp8_scaled.safetensors` | `diffusion_models/` | Optional audio-driven talking |
| `wan_2.1_vae.safetensors` | `vae/` | Optional audio-driven talking |
| `wav2vec2_large_english_fp16.safetensors` | `audio_encoders/` | Optional audio-driven talking |

Download only **the first three** to test video motion. They total many gigabytes; leave ample disk space. Do not download the 14B model unless your GPU and disk space can support it. All model licenses belong to the respective publishers.

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

The default storyboard already has Moroccan Arabic dialogue. To generate its **synthetic voice offline** using free Piper Arabic models, run this once from the project directory **after** starting the launcher at least once:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\windows\setup_voice.ps1
```

This downloads the Piper runtime and the `ar_JO-kareem-medium.onnx` Arabic model and config from the original publisher, verifies SHA-256, and saves them under `models/`. On later runs it generates speech **locally**, with no API key. That voice is Jordanian Arabic rather than Moroccan Darija and may pronounce some Darija phrases imperfectly. You can alternatively upload a recorded audio file to each talking scene. If Piper is absent, the program uses Windows SAPI voices available on the computer (quality varies and Arabic might not be installed). Speech-to-video still requires the separate 14B Wan model and an adequate GPU.

Voice model: https://huggingface.co/rhasspy/piper-voices/tree/main/ar/ar_JO/kareem/medium

## Step 6 — upload only your four hero images

Open **http://127.0.0.1:8000** on the Windows machine. Upload the four portraits, use the existing 6 × 5 second 30-second storyboard, optionally edit scenes, and start rendering. Your images, dialogue and renders are stored under `local_data/` on your own disk. They are excluded by `.gitignore`, so they are **not uploaded to GitHub**.

**Important:** The GitHub Pages link is only the **download portal**. GitHub Pages has no access to your NVIDIA GPU. Opening `127.0.0.1:8000` on your phone opens the phone itself, not your computer. Use the browser on the same Windows PC for the default secure configuration. No public ports, tunnels or external services are enabled.

If generation fails, read the error in the studio and the ComfyUI window. The code never silently swaps real AI motion for a slideshow.
