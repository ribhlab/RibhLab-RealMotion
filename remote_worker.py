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
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from studio import add_speech_to_clip, normalize_clip, synthesize_speech

app = FastAPI(title="RibhLab RealMotion LAN Worker", docs_url=None, redoc_url=None)
MAX_VIDEO_BYTES = 512 * 1024 * 1024
_state_lock = threading.RLock()
_active: dict[str, dict] = {}
_cancellation: dict[str, threading.Event] = {}


def _stage(job_id: str, phase: str, note: str) -> None:
    with _state_lock:
        if job_id:
            _active[job_id] = {'phase': phase, 'message': note, 'status': (
                'done' if phase == 'done' else
                'cancelled' if phase == 'cancelled' else
                'failed' if phase == 'failed' else 'running')}


def _check_cancel(job_id: str) -> None:
    if job_id and _cancellation.get(job_id, threading.Event()).is_set():
        _stage(job_id, 'cancelled', 'MacBook processing cancelled')
        raise HTTPException(409, 'MacBook processing cancelled by user')


@app.get('/status/{job_id}')
def worker_status(job_id: uuid.UUID,
                  x_realmotion_token: str | None = Header(default=None)):
    authorize(x_realmotion_token)
    with _state_lock:
        state = _active.get(str(job_id))
    if not state:
        raise HTTPException(404, 'Worker job not found')
    return state


@app.post('/cancel/{job_id}')
def worker_cancel(job_id: uuid.UUID,
                  x_realmotion_token: str | None = Header(default=None)):
    authorize(x_realmotion_token)
    with _state_lock:
        key = str(job_id)
        if key not in _active:
            raise HTTPException(404, 'Worker job not found')
        _cancellation.setdefault(key, threading.Event()).set()
        _active[key]['message'] = 'Cancellation requested; awaiting safe stop'
    return {'status': 'cancelling'}




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
    resolution: str = Form(default="720:1280", pattern=r"^(1280:720|720:1280|960:960)$"),
    job_id: str = Form(default=""),
    x_realmotion_token: str | None = Header(default=None),
):
    authorize(x_realmotion_token)
    if job_id:
        try:
            job_id = str(uuid.UUID(job_id))
        except (TypeError, ValueError):
            raise HTTPException(422, 'Invalid worker job ID')
        with _state_lock:
            if job_id in _active:
                raise HTTPException(409, 'Worker job ID already exists')
            _cancellation[job_id] = threading.Event()
    _stage(job_id, 'received', 'MacBook received video upload request')
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
        _stage(job_id, 'received', f'MacBook received {total // 1024} KB of AI footage')
        _check_cancel(job_id)
        normalized = workdir / "normalized.mp4"
        finished = workdir / "finished.mp4"
        _stage(job_id, 'encoding', 'MacBook FFmpeg encoding MP4')
        normalize_clip(raw, normalized, seconds, resolution=resolution)
        _check_cancel(job_id)
        if narration.strip():
            _stage(job_id, 'voice', 'MacBook synthesizing Arabic narration')
            speech = workdir / "narration.wav"
            asyncio.run(synthesize_speech(narration.strip(), speech, "ar"))
            _check_cancel(job_id)
            _stage(job_id, 'mixing', 'MacBook merging voice and video')
            add_speech_to_clip(normalized, speech, finished, seconds)
        else:
            shutil.copyfile(normalized, finished)
        if not finished.is_file() or finished.stat().st_size < 1024:
            raise HTTPException(500, "The worker could not produce an MP4")
        _check_cancel(job_id)
        _stage(job_id, 'done', 'MacBook final MP4 ready')
        return FileResponse(
            finished,
            media_type="video/mp4",
            filename="RibhLab-Processed.mp4",
            background=BackgroundTask(shutil.rmtree, workdir, ignore_errors=True),
        )
    except HTTPException as exc:
        if exc.status_code != 409:
            _stage(job_id, 'failed', f'MacBook failed: {str(exc.detail)[:250]}')
        shutil.rmtree(workdir, ignore_errors=True)
        raise
    except Exception as exc:
        _stage(job_id, 'failed', f'{type(exc).__name__}: {str(exc)[:250]}')
        shutil.rmtree(workdir, ignore_errors=True)
        raise HTTPException(500, f"LAN worker postprocessing failed: {str(exc)[:500]}") from exc
