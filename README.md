# RibhLab RealMotion 🎬

**Open-source, local-first AI video studio for turning character portraits into actual generated motion clips, with local synthetic Arabic voice soundtracks and automatic 30-second MP4 assembly.**

RealMotion is **not** a slideshow maker. Every shot is submitted to actual video-generation models running in **ComfyUI**. If ComfyUI, the GPU or the model files are missing, the job reports a real error rather than falsely claiming that still-image transitions are AI animation.

> **Status: development MVP (v0.1).** The UI, upload and storyboard API, Wan 2.2 GGUF (Q2) graph builders, ComfyUI queueing/download, optional voice generation, MP4 assembly and unit tests are implemented. The complete AI rendering pipeline has **not been executed end-to-end on a model-loaded GPU** in this environment. Face identity, accurate Darija lip-sync and prompt adherence depend on model quality and are **not guaranteed**. We deliberately do not claim otherwise.

## ⚡ Local NVIDIA mode — default (no paid API)

RealMotion now runs video generation **on your own Windows NVIDIA GPU** using local ComfyUI and local Wan 2.2 model files. GitHub and GitHub Pages hold the source and the download instructions only; they do not host an inference service.

- **No Replicate, no Vercel, no per-video credits or remote API keys** required by the default local app.
- **Start on Windows:** download the repo ZIP and double-click `Start-RealMotion.bat`.
- **One-time Wan 5B download:** after first launch, double-click `Install-Wan-Motion-Models.bat` to fetch/verify official weights (about 10 GB).
- **Optional one-click offline Arabic voice:** double-click `Install-Offline-Voice.bat`.
- **First video WITH voice:** upload one driver's photo, click **🎤🎬 جرّب 5 ثواني بالصورة والصوت**. Wan Q2 generates real motion, Piper Arabic/Windows SAPI generates spoken audio, and FFmpeg merges both to MP4. This does **not** lip-sync the mouth.
- **Longer movie:** upload four photos, then render six scenes as a 30-second MP4 using the same lightweight audio+video approach.
- **One-time prerequisites:** Python 3.11+, FFmpeg, NVIDIA driver, ComfyUI Portable NVIDIA, downloaded Wan model files.
- **Optional offline speech:** `windows/setup_voice.ps1` installs a local Arabic Piper model once; alternatively Windows SAPI or your own recordings can be used.
- **Local page:** `http://127.0.0.1:8000` on the same computer. The public GitHub Pages is only a download portal, not an upload destination.
- **Privacy:** pictures and generated MP4 files are stored on your computer under `local_data/`, never in public GitHub.
- **Honest limitation:** this is a GPU-dependent development MVP and complete rendering has not been validated end-to-end on the user's GPU. Natural Darija voice, consistent faces, lip sync and multiplayer interactions are not guaranteed.

**Full Windows installation and offline setup:** [WINDOWS_LOCAL.md](WINDOWS_LOCAL.md).

---

## 10-minute local AI film (experimental long-form mode)

Use the Firefly-style studio at `http://127.0.0.1:8000`, upload reference images or videos, write one long prompt and select **10 دقائق · 120 لقطة AI**. The backend performs **120 separate five-second Wan 2.2 Q2 GGUF generations** and joins the real AI-produced clips into a **600-second MP4**. It never labels a still-image slideshow as AI video. Each successful shot is saved to `local_data/longform/`; repeating the request with the same reference files and prompt reuses completed shots, instead of restarting from zero.

You can embed longer Arabic narration in the single prompt after `الكلام:`. A local Piper/Windows TTS voiceover is generated in short segments and mixed over the MP4. **Voice quality in Moroccan Darija and synchronized lips are not guaranteed.** Narration needs enough text to cover ten minutes; a short paragraph will produce a mostly silent film. Video uploads currently contribute **the first frame as a reference**, not their original footage, and scenes may look repetitive if only one reference picture is provided.

**Important hardware limitation:** on GTX 1660 SUPER 6 GB VRAM and 16 GB RAM, 120 AI video generations may take an impractical amount of time and can fail due to VRAM pressure. **Verify one 3-5-second real generation before using this mode.** This is a long-form assembly capability, **not** a guarantee of professional video quality, fast results, or 10-minute single-pass AI inference. Better professional production uses original video footage, a prepared script, and video editing; these hybrid editing workflows are future enhancements.

## Features

- Modern Arabic (Darija) web interface optimized for desktop and phones.
- Four configurable characters (yellow-car driver, unicorn, Spider-themed hero, bat-themed hero); **bring your own portraits**.
- Six editable 5-second shots by default, with validation requiring **exactly 30 seconds** in total.
- Two genuine generation modes:
  - **Motion / car scene:** Wan2.2-TI2V-5B Q2 GGUF on local ComfyUI.
  - **Speaking soundtrack:** genuine AI-generated motion plus an offline Piper/Windows synthetic voice or uploaded recording. This is audio overlay, **not automatically synchronized lips**.
  - **Optional future lip sync:** separate model/processing, not included in the lightweight 6 GB workflow.
- Optional uploaded dialogue recordings; or free **offline** speech synthesis with Piper Arabic or Windows SAPI. No cloud voice API is used.
- A sequential job worker, progress endpoint, error reporting, FFmpeg transcoding and final MP4 download.
- Photos/voices and generated clips remain under the local `local_data/` folder, which is excluded from Git.

## Quick start

**Windows NVIDIA (recommended):** See [WINDOWS_LOCAL.md](WINDOWS_LOCAL.md); double-click `Start-RealMotion.bat` after installing the one-time prerequisites.

**Manual start (advanced):**

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

### Models for GTX 1660 SUPER 6 GB

Use the bundled `Install-Wan-Motion-Models.bat` after first running `Start-RealMotion.bat`. It automatically downloads and SHA256-verifies these three files (~10 GB total):

| File | ComfyUI folder | Purpose |
|---|---|---|
| `Wan2.2-TI2V-5B-Q2_K.gguf` (1.85 GB) | `models/unet/` | Quantized Wan 5B video model |
| `wan2.2_vae.safetensors` (1.41 GB) | `models/vae/` | Video decoding |
| `umt5_xxl_fp8_e4m3fn_scaled.safetensors` (6.74 GB) | `models/text_encoders/` | Prompt encoder; may require RAM offloading |

The `UnetLoaderGGUF` node must be installed from [city96/ComfyUI-GGUF](https://github.com/city96/ComfyUI-GGUF) and the updated ComfyUI core must include `Wan22ImageToVideoLatent`, `CreateVideo`, and `SaveVideo`. Your local GPU configuration may still run out of memory or take substantial time: a 6 GB GTX 1660 SUPER is below typical Wan 5B FP16 recommendations. Default frame size is 288×512 with optional `WAN_WIDTH`/`WAN_HEIGHT` environment overrides (multiples of 16). The result is **not guaranteed** to run successfully until actually tested with model weights.

More information: [official ComfyUI Wan tutorial](https://comfyanonymous.github.io/ComfyUI_examples/wan22/) and [QuantStack Wan 5B GGUF](https://huggingface.co/QuantStack/Wan2.2-TI2V-5B-GGUF).

### Voices — offline by default

Automatic speech uses locally installed **Piper Arabic (`ar_JO-kareem-medium`)** first; on Windows it falls back to installed **Windows SAPI** voices. Run `windows/setup_voice.ps1` once to download the Piper engine and voice data. Existing dialogue is used automatically if present; uploaded audio recordings are supported too. Piper Arabic is Jordanian, not specifically Moroccan, so Darija pronunciation may be imperfect.

Neither audio generation nor video inference needs a cloud API after dependencies and models are downloaded. Consent is still required for photos and recordings of children. The app stays on `127.0.0.1` and should not be exposed publicly without authentication and HTTPS.

### Architecture

```
Browser (static/index.html + app.js)
    ↕ local FastAPI (app.py)
    ↕ storyboard / local uploads / background job
    ↕ studio.py (ComfyUI client)
        → Wan I2V 5B Q2 GGUF: portrait + motion description → AI generated MP4
    ↕ local Piper/Windows voice OR uploaded recording
    ↕ FFmpeg normalize / add speech / concat
    → final.mp4
```

The app runs on `127.0.0.1` by default. Job states are in memory (lost if the process restarts), and the single background worker processes projects sequentially. Future improvements include persistent job storage, more natural local Darija speech, face-identity controls and a visual scene compositor.

## Tests

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Tests validate both ComfyUI graphs, 30-second duration requirements, upload and project endpoints and FFmpeg clip assembly. **Passing tests does not mean a GPU render was performed**: that requires a properly configured ComfyUI and licensed/available model files.

## License

The RealMotion application code is MIT licensed (see `LICENSE`). External models and services retain their own licenses. Do not commit your children's photographs or generated voice clips to a public repo.
