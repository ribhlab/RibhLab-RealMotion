"""LAN-only postprocessing worker for RibhLab RealMotion.

Run on a second Windows PC (e.g. Intel MacBook under Boot Camp).
It does not run ComfyUI or require an NVIDIA GPU. Keep port 8787 private
to the trusted local network, and share the secret only between the PCs.
"""
from __future__ import annotations

import asyncio
import hmac
import os
import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from studio import add_speech_to_clip, normalize_clip, synthesize_speech

app = FastAPI(title="RibhLab RealMotion LAN Worker", docs_url=None, redoc_url=None)
MAX_VIDEO_BYTES = 512 * 1024 * 1024


def authorize(presented: str | None) -> None:
    expected = os.environ.get("REALMOTION_WORKER_TOKEN", "")
    if len(expected) < 32:
        raise HTTPException(503, "Worker secret has not been configured")
    if not presented or not hmac.compare_digest(presented, expected):
        raise HTTPException(401, "Unauthorized LAN worker request")


@app.get("/health")
def health(x_realmotion_token: str | None = Header(default=None)):
    authorize(x_realmotion_token)
    return {"status": "ok", "role": "audio_and_postprocessing", "gpu": "not_required"}


@app.post("/process")
def process(
    video: UploadFile = File(...),
    seconds: int = Form(..., ge=1, le=10),
    narration: str = Form(default="", max_length=12000),
    x_realmotion_token: str | None = Header(default=None),
):
    authorize(x_realmotion_token)
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise HTTPException(503, "FFmpeg and ffprobe must be installed on the worker")
    workdir = Path(tempfile.mkdtemp(prefix="realm_lan_"))
    try:
        raw = workdir / "raw.mp4"
        total = 0
        with raw.open("wb") as sink:
            while chunk := video.file.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_VIDEO_BYTES:
                    raise HTTPException(413, "Video is larger than the 512 MB LAN worker limit")
                sink.write(chunk)
        if total < 1024:
            raise HTTPException(422, "Video file is empty or incomplete")
        normalized = workdir / "normalized.mp4"
        finished = workdir / "finished.mp4"
        normalize_clip(raw, normalized, seconds, resolution="720:1280")
        if narration.strip():
            speech = workdir / "narration.wav"
            asyncio.run(synthesize_speech(narration.strip(), speech, "ar"))
            add_speech_to_clip(normalized, speech, finished, seconds)
        else:
            shutil.copyfile(normalized, finished)
        if not finished.is_file() or finished.stat().st_size < 1024:
            raise HTTPException(500, "The worker could not produce an MP4")
        return FileResponse(
            finished,
            media_type="video/mp4",
            filename="RibhLab-Processed.mp4",
            background=BackgroundTask(shutil.rmtree, workdir, ignore_errors=True),
        )
    except HTTPException:
        shutil.rmtree(workdir, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(workdir, ignore_errors=True)
        raise HTTPException(500, f"LAN worker postprocessing failed: {str(exc)[:500]}") from exc
