# RibhLab RealMotion 🎬

**Open-source, local-first AI video studio for turning character portraits into actual generated motion clips, with audio-driven talking shots and automatic 30-second MP4 assembly.**

RealMotion is **not** a slideshow maker. Every shot is submitted to actual video-generation models running in **ComfyUI**. If ComfyUI, the GPU or the model files are missing, the job reports a real error rather than falsely claiming that still-image transitions are AI animation.

> **Status: development MVP (v0.1).** The UI, upload and storyboard API, native Wan 2.2 graph builders, ComfyUI queueing/download, optional voice generation, MP4 assembly and unit tests are implemented. The complete AI rendering pipeline has **not been executed end-to-end on a model-loaded GPU** in this environment. Face identity, accurate Darija lip-sync and prompt adherence depend on model quality and are **not guaranteed**. We deliberately do not claim otherwise.

## ☁️ Cloud Web App — only upload four photos

**GitHub Pages** is the public UI. A connected **Vercel Node serverless API** can securely call **Replicate** for AI video motion, Arabic speech synthesis and audio-driven lip-sync. End users only upload 4 photos, enter an owner access code and press Generate; a default 6×5-second movie is preconfigured. **A GPU provider account and credit are still required**: GitHub Pages and GitHub Actions do not provide video-generation GPUs.

- **Static frontend:** root `index.html`, `cloud.css`, `cloud.js` (runs from GitHub Pages or Vercel). This does not need Windows, ComfyUI, Python or local NVIDIA.
- **Secure cloud endpoints:** `api/config.js`, `api/start.js`, `api/status.js`, `api/media.js`. Server token is kept as a server-side environment secret, never in `cloud.js`.
- **One-time owner setup:** connect this repo to a Vercel project and configure encrypted environment variables `REPLICATE_API_TOKEN` and `REALMOTION_ACCESS_PIN` (at least 12 characters). Deploy after saving. The public site shows **not connected** until both are set. Do **not** paste these secrets into GitHub or chat.
- **If using the GitHub Pages mirror:** point `window.REALMOTION_API_BASE` to your deployed Vercel app in `cloud.js` or a small inline config *without secrets*, and add `https://ribhlab.github.io` to `REALMOTION_ALLOWED_ORIGINS` if needed. For the simplest one-click setup share the main Vercel URL which serves frontend and backend from the same origin.
- **Charges:** cloud movie rendering is billed by Replicate depending on GPU model and duration. No calls are made until the owner configures tokens and an authorized user explicitly confirms generation. Do not expose the app publicly with a weak shared access code or unbounded provider credit.
- **Video format:** the generated clips are MP4; browser assembly records a real 30-second movie (WebM on most Chrome devices; MP4 where the browser's MediaRecorder supports it). The download format varies by browser. Browser merging takes roughly the actual movie duration and may need desktop memory; individual clips remain available.
- **Limitations:** it is a cloud-ready beta, not an end-to-end validated live GPU service. Facial identity is not locked; a multi-child collage may not be faithfully converted into one coherent shared scene; Arabic/Darija lip synchronization and generated voices may vary. Browser-side job state is not persistent across refreshes.

**Cloud setup walkthrough:** [CLOUD_SETUP.md](CLOUD_SETUP.md). Never publish children's original photos in this public repository; the browser transmits chosen photos only to the cloud video API after pressing Generate.

---

## Features

- Modern Arabic (Darija) web interface optimized for desktop and phones.
- Four configurable characters (yellow-car driver, unicorn, Spider-themed hero, bat-themed hero); **bring your own portraits**.
- Six editable 5-second shots by default, with validation requiring **exactly 30 seconds** in total.
- Two genuine generation modes:
  - **Motion / car scene:** Wan2.2-TI2V-5B native ComfyUI video generation.
  - **Talking / lip movement:** Wan2.2-S2V-14B conditioned on real audio and a portrait. This is a separate, heavier model, not a mouth-opening GIF.
- Optional uploaded dialogue recordings; or optional `edge-tts` neural synthesis for a quick voice draft (needs network and third-party access).
- A sequential job worker, progress endpoint, error reporting, FFmpeg transcoding and final MP4 download.
- Photos/voices and generated clips remain under the local `local_data/` folder, which is excluded from Git.

## Quick start

**Prerequisites:** Python 3.11+, FFmpeg/FFprobe on PATH, and a separately running updated [ComfyUI](https://github.com/Comfy-Org/ComfyUI) with an NVIDIA GPU and the relevant model files. The 5B workflow is the lighter mode (official ComfyUI guidance says it can fit in ~8 GB VRAM with offloading); the **14B S2V talking model requires significantly more resources**. A free GitHub repository does not provide GPU compute.

```bash
git clone https://github.com/ribhlab/RibhLab-RealMotion.git
cd RibhLab-RealMotion
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
# ComfyUI must already be running separately on http://127.0.0.1:8188
uvicorn app:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000**. Upload character images, edit the 30-second storyboard, save it, click **Generate**, and watch the status. API documentation: **http://127.0.0.1:8000/api/docs**.

### Install Wan models in ComfyUI

The app's workflow uses the **official core ComfyUI nodes**, including `Wan22ImageToVideoLatent`, `WanSoundImageToVideo`, `CreateVideo` and `SaveVideo`. Update ComfyUI until they are available.

| Model file (default name) | ComfyUI folder | Needed for |
|---|---|---|
| `wan2.2_ti2v_5B_fp16.safetensors` | `models/diffusion_models` | image-to-video |
| `wan2.2_vae.safetensors` | `models/vae` | image-to-video |
| `umt5_xxl_fp8_e4m3fn_scaled.safetensors` | `models/text_encoders` | both |
| `wan2.2_s2v_14B_fp8_scaled.safetensors` | `models/diffusion_models` | talking |
| `wan_2.1_vae.safetensors` | `models/vae` | talking |
| `wav2vec2_large_english_fp16.safetensors` | `models/audio_encoders` | talking |

Model and workflow references (check download rights and disk space):
- [ComfyUI Wan 2.2 official guide](https://docs.comfy.org/tutorials/video/wan/wan2_2)
- [Wan 2.2 5B native workflow](https://github.com/Comfy-Org/workflow_templates/blob/main/templates/video_wan2_2_5B_ti2v.json)
- [Wan 2.2 S2V audio-driven workflow](https://github.com/Comfy-Org/workflow_templates/blob/main/templates/video_wan2_2_14B_s2v.json)
- [Wan 2.2 model card / licenses](https://huggingface.co/Comfy-Org/Wan-2.2)

The native 5B graph sends one portrait plus a motion prompt to Wan and saves a generated clip. The S2V graph uploads the portrait **and an audio track** to ComfyUI and generates the facial/speech motion. Audio uploads use ComfyUI's generic `/upload/image` API (also used for audio input files in compatible versions).

Model filenames and URL can be changed via the environment variables listed in `.env.example` (environment file is a *template*, not loaded automatically). For example:

```bash
export COMFYUI_URL=http://127.0.0.1:8188
export WAN_I2V_MODEL=wan2.2_ti2v_5B_fp16.safetensors
uvicorn app:app --host 127.0.0.1 --port 8000
```

**Important:** Facial resemblance is probabilistic. Single-portrait I2V does **not** guarantee realistic driving from a portrait taken outside a car; use a starting picture already showing the person in the desired setting for better results. A scene with multiple children interacting needs an appropriate *combined starting reference*, reference-conditioning workflow or manually composed scene; v0.1 does not offer identity locking for several different faces in one shot. S2V audio embedding may be English-biased; Moroccan Arabic results need testing.

### Voices

To avoid another person's actual voice being imitated, RealMotion synthesizes a fresh generic voice through `edge-tts` if the scene has text but no audio file. This service is **online, unofficial and not guaranteed to remain available or cost-free**. Upload a legally obtained voice recording per talking shot to avoid relying on that service. You should have consent to use all photos and audio, especially for children. This local-first app does **not** upload any photographs to GitHub; actual requests go to the **ComfyUI instance that you configure**. Do not expose the server publicly without authentication and HTTPS.

### Architecture

```
Browser (static/index.html + app.js)
    ↕ local FastAPI (app.py)
    ↕ storyboard / local uploads / background job
    ↕ studio.py (ComfyUI client)
        → Wan I2V 5B: portrait + motion description → AI generated MP4
        → Wan S2V 14B: portrait + real audio + prompt → AI generated speaking MP4
    ↕ FFmpeg normalize / concat
    → final.mp4
```

The app runs on `127.0.0.1` by default. Job states are in memory (lost if the process restarts), and the single background worker processes projects sequentially. Future improvements include persistent job storage, optional local speech models, and a visual scene compositor.

## Tests

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Tests validate both ComfyUI graphs, 30-second duration requirements, upload and project endpoints and FFmpeg clip assembly. **Passing tests does not mean a GPU render was performed**: that requires a properly configured ComfyUI and licensed/available model files.

## License

The RealMotion application code is MIT licensed (see `LICENSE`). External models and services retain their own licenses. Do not commit your children's photographs or generated voice clips to a public repo.
