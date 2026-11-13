# RealMotion — True lip sync with MuseTalk 1.5 (local NVIDIA)

## What this feature actually does

RealMotion now offers **real speech-driven mouth motion**, not merely overlaying voice onto the video.

1. Generate 3–5 seconds of actual video from an image using local **Wan 2.2** or **LTX 2B**.
2. Synthesize an original generic Arabic voice **locally** using Piper or a Windows SAPI voice.
3. Ask ComfyUI to release cached GPU VRAM before the separate process.
4. Run **MuseTalk 1.5** on the generated MP4 and the voice in a **separate local Python 3.10 environment**, with `--use_float16 --batch_size 1` for smaller memory usage.
5. Verify that MuseTalk actually produced an MP4, add the speech track, save the output. If MuseTalk fails, the task reports an error and does **not** claim that the lips moved.

The 6 GB GTX 1660 SUPER is **experimental** for this setup. The MuseTalk authors tested fp16 on a 4 GB RTX 3050 Ti laptop, but different GPU architectures, available RAM, installed face detectors and video quality can change requirements. GPU success is **not yet verified** on your machine.

No Vercel, Replicate, cloud video model or API key is needed. Installing dependencies and weights needs Internet once. Actual inference is local, with Hugging Face and Transformers forced into offline mode. Images and audio stay on the PC.

## Install on Windows

Prerequisites: NVIDIA drivers, FFmpeg, Git, local RealMotion/ComfyUI already working, 15+ GB free disk recommended for models and installation overhead. Use the NVIDIA PC for MuseTalk; a MacBook postproduction worker **does not add VRAM**.

For the first installation, **double-click**:

```text
Install-LipSync.bat
```

The script:

- checks `py -3.10` (separate Python 3.10; install using `winget install --id Python.Python.3.10 -e`);
- clones the official [MuseTalk repository](https://github.com/TMElyralab/MuseTalk) to `external/MuseTalk/`;
- installs a separate `external/MuseTalk/.venv` for MuseTalk's older pinned PyTorch, CUDA, MMLab and face-processing packages;
- downloads official MuseTalk 1.5, Whisper, VAE, DWPose and face-parsing weights;
- never modifies ComfyUI's Python or RealMotion's main `.venv`.

**Windows limitation:** some MuseTalk packages such as `mmcv==2.0.1` require a compatible prebuilt CUDA wheel, or Microsoft C++ Build Tools to compile. If the installer stops there, you must resolve the CUDA/PyTorch/mmcv compatibility on your machine; the app does not pretend that the installation succeeded. MuseTalk's official README was the reference for package versions. This is not a tested one-click guarantee.

Manual PowerShell setup/retry:
```powershell
cd C:\AI\RibhLab-RealMotion
powershell -NoProfile -ExecutionPolicy Bypass -File .\windows\setup_lipsync.ps1
```

To perform code/dependency setup without weight downloads:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\windows\setup_lipsync.ps1 -SkipWeights
```

The optional environment variables are `REALMOTION_MUSETALK_DIR` (MuseTalk checkout) and `REALMOTION_MUSETALK_PYTHON` (its isolated interpreter).

## Try your first real lip-sync scene

Start `Start-RealMotion.bat` on your NVIDIA PC. Open the localhost URL printed by the launcher. Upload **one front-facing portrait**, ideally with the person’s face visible; use a motion prompt that keeps the face visible:

```text
A medium close-up portrait of the same person, facing camera, stable face and natural head movement. الكلام: السلام عليكم، كيف دايرين اليوم؟
```

Select Wan or LTX, **3 seconds**, enable **تعليق صوتي محلي**, then enable **🎤 تحريك الشفاه الحقيقي · MuseTalk 1.5**. The status label should say that MuseTalk is installed. Generate and inspect the MP4.

If you want audio overlay only, leave the lip-sync switch off. If you enable lip sync but it is not installed, the app rejects the request instead of creating an unchanged mouth video.

### Four-character storyboard API

Project speaking scenes also accept `"lip_sync": true` on any `"mode": "talk"` scene. Motion scenes remain unchanged. MuseTalk is applied to the *already generated* speaking shot, with that character's dialogue/recording. No need to run heavy Wan S2V 14B. The final shot then goes through local FFmpeg and 30-second concatenation.

### Important limitations and licensing

- MuseTalk works with a **visible face**. Side views, occlusions, high motion, poorly lit faces, cartoon masks and very tiny faces may fail or look wrong.
- The default Piper Arabic voice is Jordanian Arabic, not a natural Moroccan child voice; exact Darija pronunciation and lip alignment aren't guaranteed. We do **not** clone children's or other people's voices.
- The 6 GB card may take substantial time or produce CUDA out-of-memory errors, especially if ComfyUI has cached large models. The app requests a cache release first.
- For short clips (1–10 seconds), MuseTalk can edit mouths. **10-minute mode** and **Stable Food 2.5D** do not enable lip sync in this version.
- MuseTalk source is MIT and its authors explicitly permit commercial model use, but **third-party components carry their own licenses**. Audit each model before commercial distribution. Wav2Lip is *not* used, as its open code has non-commercial restrictions.
- Photos/voices/videos of children should be used with permission. No public image hosting is required.

Official: https://github.com/TMElyralab/MuseTalk
