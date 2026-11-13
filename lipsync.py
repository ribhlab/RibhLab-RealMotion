"""Local MuseTalk 1.5 lip synchronization (NVIDIA, no video cloud API).

MuseTalk owns its inference code and model weights, installed separately.
This adapter accepts already-generated MP4 plus speech WAV/MP3 and creates a
real mouth-synchronized MP4; it never claims that audio overlay is lip sync.
Main FastAPI environment does not import torch/mmcv from MuseTalk.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Callable

BASE = Path(__file__).resolve().parent
DEFAULT_ROOT = BASE / "external" / "MuseTalk"
REQUIRED_FILES = [
    "scripts/inference.py",
    "models/musetalkV15/musetalk.json",
    "models/musetalkV15/unet.pth",
    "models/sd-vae/config.json",
    "models/sd-vae/diffusion_pytorch_model.bin",
    "models/whisper/config.json",
    "models/whisper/pytorch_model.bin",
    "models/whisper/preprocessor_config.json",
    "models/dwpose/dw-ll_ucoco_384.pth",
    "models/face-parse-bisent/79999_iter.pth",
    "models/face-parse-bisent/resnet18-5c106cde.pth",
]
MIN_BYTES = {
    "models/musetalkV15/unet.pth": 100_000_000,
    "models/sd-vae/diffusion_pytorch_model.bin": 100_000_000,
    "models/whisper/pytorch_model.bin": 50_000_000,
    "models/dwpose/dw-ll_ucoco_384.pth": 10_000_000,
    "models/face-parse-bisent/79999_iter.pth": 10_000_000,
}


class LipSyncError(RuntimeError):
    pass


def get_root() -> Path:
    return Path(os.environ.get("REALMOTION_MUSETALK_DIR", str(DEFAULT_ROOT))).expanduser().resolve()


def get_python(root: Path) -> Path:
    # MuseTalk has distinct pinned packages, so NEVER use main .venv.
    custom = os.environ.get("REALMOTION_MUSETALK_PYTHON")
    if custom:
        return Path(custom).expanduser().resolve()
    return root / (".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python")


def check_lipsync_ready() -> dict:
    """Inspection only. A 'ready' result does not certify GPU compatibility."""
    root = get_root()
    missing = []
    py = get_python(root)
    if not py.is_file():
        missing.append("MuseTalk separate Python environment: " + str(py))
    for rel in REQUIRED_FILES:
        path = root / rel
        if not path.is_file() or path.stat().st_size < MIN_BYTES.get(rel, 1):
            missing.append(rel)
    for exe in ("ffmpeg", "ffprobe"):
        if not shutil.which(exe):
            missing.append(exe + " on PATH")
    return {
        "engine": "musetalk_v15",
        "ready": not missing,
        "installed": root.is_dir(),
        "missing": missing,
        "gpu_tested": False,
        "license_note": "MuseTalk MIT/code, model allows commercial use; other weights retain their licenses",
    }


def _run(cmd: list[str], *, cwd: Path | None = None, timeout: int = 90) -> None:
    try:
        subprocess.run(cmd, cwd=cwd, timeout=timeout,
                       check=True, capture_output=True, text=True)
    except subprocess.TimeoutExpired as exc:
        raise LipSyncError("Local FFmpeg timed out during lip sync preparation") from exc
    except subprocess.CalledProcessError as exc:
        raise LipSyncError("Local FFmpeg failed: " + (exc.stderr or "")[-650:]) from exc


def _run_inference(
    args: list[str], *, root: Path, timeout: int,
    cancel_event: threading.Event | None = None,
) -> None:
    # Avoid any hidden downloads during inference: all weights must exist locally.
    env = os.environ.copy()
    env.update({
        "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
        "DIFFUSERS_OFFLINE": "1", "HF_DATASETS_OFFLINE": "1",
        "PYTHONUNBUFFERED": "1",
    })
    with subprocess.Popen(
        args, cwd=root, env=env, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, errors="replace",
    ) as process:
        # Pipe readers must be consumed continuously to avoid deadlocks.
        # A worker thread keeps a bounded tail of lines for actionable errors.
        tail = []
        def reader():
            if process.stdout is not None:
                for line in process.stdout:
                    tail.append(line.rstrip())
                    if len(tail) > 35:
                        del tail[:-35]
        reader_thread = threading.Thread(target=reader, daemon=True)
        reader_thread.start()
        started = time.monotonic()
        while process.poll() is None:
            if cancel_event is not None and cancel_event.is_set():
                _terminate_tree(process)
                raise LipSyncError("Lip sync generation cancelled")
            if time.monotonic() - started > timeout:
                _terminate_tree(process)
                raise LipSyncError("MuseTalk exceeded the local time limit; check RAM / VRAM")
            time.sleep(0.3)
        reader_thread.join(timeout=4)
        if process.returncode != 0:
            raise LipSyncError(
                f"MuseTalk exited with code {process.returncode}. "
                + "\n".join(tail[-12:])[-1350:]
            )


def _terminate_tree(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True, check=False, timeout=12,
        )
    else:
        process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()


def render_lipsync(
    source_video: Path, voice_audio: Path, destination: Path, *,
    seconds: int, progress: Callable[[str], None] | None = None,
    cancel_event: threading.Event | None = None,
    workdir: Path | None = None,
    timeout: int = 3600,
) -> Path:
    """Synchronize visible mouth with audio via MuseTalk 1.5 (batch=1 fp16).

    This is NOT audio overlay; the generated face pixels are re-rendered.
    Real face presence, detection, Arabic pronunciation and output quality
    depend on MuseTalk and the underlying footage.
    """
    source_video, voice_audio, destination = map(
        lambda p: Path(p).resolve(), (source_video, voice_audio, destination)
    )
    if seconds < 1 or seconds > 15:
        raise LipSyncError("Short lip sync scenes must last between 1 and 15 seconds")
    if not source_video.is_file() or not voice_audio.is_file():
        raise LipSyncError("Both the generated video and actual speech audio must exist")
    status = check_lipsync_ready()
    if not status["ready"]:
        raise LipSyncError(
            "MuseTalk 1.5 is not installed. Run Install-LipSync.bat once. Missing: "
            + ", ".join(status["missing"][:6])
        )
    if cancel_event is not None and cancel_event.is_set():
        raise LipSyncError("Lip sync generation cancelled")
    root = get_root()
    parent = Path(workdir).resolve() if workdir else destination.parent / "lipsync_tmp"
    job = parent / ("job_" + uuid.uuid4().hex[:12])
    job.mkdir(parents=True, exist_ok=False)
    prepared_video = job / "source.mp4"
    prepared_audio = job / "voice.wav"
    output_dir = job / "results"
    output_dir.mkdir()
    if progress:
        progress("Preparing 25fps video and voice for MuseTalk lip sync")
    # Work around MuseTalk's frame extraction and subprocess quoting issues.
    # Normalize input to 25fps and ensure output audio has exact clip duration.
    _run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(source_video), "-an", "-vf", "fps=25,format=yuv420p",
        "-t", str(seconds), "-c:v", "libx264", "-preset", "veryfast",
        str(prepared_video),
    ], timeout=180)
    _run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(voice_audio), "-af", "apad", "-t", str(seconds),
        "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(prepared_audio),
    ], timeout=90)
    # OmegaConf YAML loader accepts JSON, avoiding an extra YAML dependency here.
    tasks = job / "tasks.json"
    tasks.write_text(json.dumps({
        "task_0": {"video_path": str(prepared_video),
                   "audio_path": str(prepared_audio),
                   "result_name": "synchronized.mp4"}
    }, ensure_ascii=False), encoding="utf-8")
    exe = get_python(root)
    args = [
        str(exe), "-m", "scripts.inference", "--inference_config", str(tasks),
        "--result_dir", str(output_dir),
        "--unet_model_path", "models/musetalkV15/unet.pth",
        "--unet_config", "models/musetalkV15/musetalk.json",
        "--whisper_dir", "models/whisper", "--version", "v15",
        "--ffmpeg_path", str(Path(shutil.which("ffmpeg")).parent),
        "--use_float16", "--batch_size", "1", "--fps", "25",
        "--output_vid_name", "synchronized.mp4",
    ]
    if progress:
        progress("MuseTalk 1.5: generating real speech-synced mouth motion on NVIDIA")
    _run_inference(args, root=root, timeout=timeout, cancel_event=cancel_event)
    generated = output_dir / "v15" / "synchronized.mp4"
    if not generated.is_file() or generated.stat().st_size < 1024:
        raise LipSyncError(
            "MuseTalk did not output a synchronized MP4. "
            "Check MuseTalk/face detection logs and use a front-facing portrait."
        )
    if cancel_event is not None and cancel_event.is_set():
        raise LipSyncError("Lip sync generation cancelled")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if progress:
        progress("Combining true mouth-synced frames with original speech in MP4")
    # MuseTalk uses an external ffmpeg shell command. We explicitly remux
    # the known speech track; never trust the generated output to carry audio.
    _run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(generated), "-i", str(prepared_audio),
        "-map", "0:v:0", "-map", "1:a:0", "-t", str(seconds),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
        str(destination),
    ], timeout=240)
    if not destination.is_file() or destination.stat().st_size < 1024:
        raise LipSyncError("Lip sync export did not create a real MP4")
    if os.environ.get("REALMOTION_KEEP_LIPSYNC_WORK", "").lower() not in ("1", "true"):
        shutil.rmtree(job, ignore_errors=True)
    return destination
