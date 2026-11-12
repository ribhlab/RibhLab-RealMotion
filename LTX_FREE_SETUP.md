# RibhLab RealMotion — LTX 2B FP8 (100% local / no paid API)

This is an **optional experimental GPU image-to-video renderer**, not a claim
to match Adobe Firefly. It runs on your own NVIDIA computer through ComfyUI.
It is distinct from both Wan Q2 and the Stable Food 2.5D effect. No account,
credit card, API token or paid inference service is used.

## Hardware limitations (important)

- The installed GTX 1660 SUPER has **6 GB VRAM**, and does **not** have native
  FP8 compute acceleration. LTX-2B-FP8 compatibility on this particular machine
  **has not been verified by an end-to-end GPU video test**.
- The separate T5-XXL FP8 encoder is needed: **Wan's UMT5 is not a substitute**.
  The LTX checkpoint is ~4.46 GB, T5 ~4.89 GB; allow at least 12 GB of free
  local disk space. The application asks ComfyUI to place the text encoder on
  CPU, so system RAM / CPU memory offloading may be the bottleneck.
- 512x288 landscape, 288x512 portrait, or 384x384 square are conservative
  starting dimensions. Source orientation is preserved. These are **latent
  sizes**: encoding the final MP4 at 720p **does not restore source detail**.
- A 3-second first test is advised. If ComfyUI reports an actual out-of-memory
  or unsupported FP8 operation, stop; do not repeatedly rerun it. Lowering the
  latent to 384x224 landscape / 224x384 portrait (multiple-of-32) can reduce
  memory, but quality suffers. No automatic fake 'success' fallback is used.

## 1. Install the required files (explicit, free downloads)

Use PowerShell **on the NVIDIA Windows computer**, not CMD, not the MacBook.
Stop ComfyUI/RealMotion first to avoid stale model lists. You already have the
repo at `C:\AI\RibhLab-RealMotion`.

```powershell
git -C "C:\AI\RibhLab-RealMotion" pull --ff-only origin main
& "C:\AI\RibhLab-RealMotion\windows\setup_ltx_free.ps1"
```

If PowerShell blocks this local script, run it in the same session without
changing system-wide policy:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\AI\RibhLab-RealMotion\windows\setup_ltx_free.ps1"
```

The script installs these exact files **only when you explicitly execute it**:

| Local path under ComfyUI/models | Official source | SHA256 |
| --- | --- | --- |
| `checkpoints/ltxv-2b-0.9.8-distilled-fp8.safetensors` | [Lightricks LTX-Video model](https://huggingface.co/Lightricks/LTX-Video/blob/main/ltxv-2b-0.9.8-distilled-fp8.safetensors) | `d6d8fa8ed3a98346787c2503ac80fb5d7cebcf80e356b79a2ba361fbadf97e15` |
| `text_encoders/t5xxl_fp8_e4m3fn.safetensors` | [Comfy-Org T5-XXL](https://huggingface.co/Comfy-Org/stable-diffusion-3.5/blob/main/text_encoders/t5xxl_fp8_e4m3fn.safetensors) | `7d330da4816157540d6bb7838bf63a0f02f573fc48ca4d8de34bb0cbfd514f09` |

Downloads are resumable with curl and only **activated after checksum verification**.
A failed partial download remains as a `.part` file; rerun the same command.
The script does not replace your original Wan model or other files.
Avoid starting several ComfyUI GPU processes at once.

## 2. Restart and confirm availability

1. Launch ComfyUI with your original `run_nvidia_gpu.bat` (or normal
   RealMotion launcher). Its API should respond at `http://127.0.0.1:8188`.
2. Launch RealMotion with `Start-RealMotion.bat`.
3. Hard refresh `http://127.0.0.1:8000` with Ctrl+Shift+R.
4. Select **LTX 2B FP8 · مجاني · AI Motion**. RealMotion calls
   `GET /api/engines/ltx/status` on your local app: if any node, model, or
   text encoder is absent it clearly reports exactly what's missing and
   disables Generate. This endpoint performs no generation or paid request.
5. Choose 3s, no voice, and try the tagine reference. Copy Logs if it fails.

The graph uses these **official ComfyUI core LTXV nodes**, as represented in
`comfyanonymous/ComfyUI_examples/ltxv/ltxv_image_to_video.json`:

`CheckpointLoaderSimple`, `CLIPLoader(type=ltxv,device=cpu)`,
`CLIPTextEncode`, `LoadImage`, `LTXVImgToVideo`,
`LTXVConditioning`, `LTXVScheduler`, `KSamplerSelect`,
`SamplerCustom`, `VAEDecode`, `CreateVideo`, and `SaveVideo`.
Sampling defaults to 8 steps, CFG 1 (distilled), 24fps and an 8N+1 frame
count. No LTX API partner nodes and no commercial video providers are used.

### 3. What still requires real hardware testing?

Unit/API tests prove graph wiring, model readiness logic and Studio
integration, but **do not prove 6GB VRAM compatibility or Firefly quality**.
If the ComfyUI backend rejects this FP8 checkpoint or CUDA runs out of memory,
the error will be explicit. Do not download other random models or pay for
anything based on this setup alone.

MacBook Worker is optional for final MP4/audio postprocessing. Keep the
NVIDIA GPU running for the real diffusion stages. This change does not turn
the MacBook Radeon/CPU into a CUDA device.
