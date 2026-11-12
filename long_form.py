"""Local 10-minute AI film assembly from 120 *genuinely generated* 5-second shots.

No cloud GPU, no synthetic slideshow fallback, no deceptive claim that one Wan
inference produces 10 minutes. Large projects are checkpointed per shot; a
second request with identical sources/prompt resumes existing valid clips.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Callable

from studio import (
    ComfyClient, ComfyError, image_to_video_graph, normalize_clip,
    concatenate_clips, add_speech_to_clip, synthesize_speech
)

LONG_SECONDS = 600
SHOT_SECONDS = 5
SHOT_COUNT = LONG_SECONDS // SHOT_SECONDS
MAX_REFERENCES = 40
CAMERA_DIRECTIONS = (
    "Slow cinematic dolly-in, stable subject identity, natural motion.",
    "Gentle orbiting camera, lively natural motion and consistent scene.",
    "Cinematic tracking from left to right, subtle subject action.",
    "Slow pull-back camera, realistic motion and consistent lighting.",
    "Smooth low-angle tracking shot, realistic environmental movement.",
    "High-angle reveal, smooth moving camera and believable animation.",
    "Medium close-up with subtle character motion, stable details.",
    "Slow sidewards pan, natural physics and unchanged subject identity."
)


def plan_shots(prompt: str, references: list[Path]) -> list[dict]:
    if not references or len(references) > MAX_REFERENCES:
        raise ValueError("Long film needs 1 to 40 uploaded reference assets")
    if len(prompt.strip()) < 8:
        raise ValueError("Write a descriptive prompt for the film")
    blocks = [
        s.strip() for s in re.split(r'\n\s*\n|[.;]\s+(?=[A-Z])', prompt)
        if len(s.strip()) >= 8
    ]
    if not blocks:
        blocks = [prompt.strip()]
    result = []
    for i in range(SHOT_COUNT):
        result.append({
            'index': i,
            'reference': references[i % len(references)],
            'prompt': blocks[i % len(blocks)] + " " +
                      CAMERA_DIRECTIONS[(i // len(references)) % len(CAMERA_DIRECTIONS)],
            'seconds': SHOT_SECONDS
        })
    return result


def _fingerprint(refs: list[Path], prompt: str, narration: str) -> str:
    key = {
        'v': 1, 'refs': [str(p.resolve()) for p in refs],
        'prompt': prompt, 'narration': narration,
        'width': os.getenv("WAN_WIDTH", "288"),
        'height': os.getenv("WAN_HEIGHT", "512"),
        'model': os.getenv("WAN_I2V_MODEL", "Wan2.2-TI2V-5B-Q2_K.gguf")
    }
    return hashlib.sha256(
        json.dumps(key, ensure_ascii=False, sort_keys=True).encode('utf-8')
    ).hexdigest()[:24]


def _speech_chunks(text: str, max_chars: int = 380) -> list[str]:
    words = text.split()
    chunks: list[str] = []
    current = ''
    for word in words:
        if len(word) > max_chars:
            if current:
                chunks.append(current)
                current = ''
            for i in range(0, len(word), max_chars):
                chunks.append(word[i:i+max_chars])
            continue
        if current and len(current) + 1 + len(word) > max_chars:
            chunks.append(current)
            current = word
        else:
            current = (current + ' ' + word).strip()
    if current:
        chunks.append(current)
    return chunks


def _full_voiceover(text: str, folder: Path, progress: Callable[[str, float], None]) -> Path:
    """Generate voiceover chunks and join them without a cloud service."""
    chunks = _speech_chunks(text)
    if not chunks:
        raise ValueError("Arabic narration text is empty")
    wavs: list[Path] = []
    for index, chunk in enumerate(chunks):
        wav = folder / f"voice_{index:04d}.wav"
        if not wav.is_file() or wav.stat().st_size < 100:
            asyncio.run(synthesize_speech(chunk, wav, 'ar'))
        wavs.append(wav)
        progress(f"Arabic voice: chunk {index+1}/{len(chunks)}",
                 0.93 + 0.04*(index+1)/len(chunks))
    # All speech segments are PCM WAV; concat and convert to one WAV stream.
    list_file = folder / "voice_list.txt"
    list_file.write_text(
        ''.join("file '" + p.as_posix().replace("'", "'\\''") + "'\n" for p in wavs),
        encoding="utf-8")
    merged = folder / "voiceover.wav"
    subprocess.run(
        ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
         '-f', 'concat', '-safe', '0', '-i', str(list_file),
         '-ar', '22050', '-ac', '1', '-c:a', 'pcm_s16le', str(merged)],
        check=True, timeout=900, capture_output=True)
    return merged


def render_ten_minute_film(
    references: list[Path], prompt: str, narration: str,
    output: Path, root: Path, update: Callable[[str, float], None]
) -> str:
    """Generate 120 real Wan scenes, then assemble ten minutes of film.

    Each successfully generated shot is kept on disk to resume the same
    project after interruptions. Requires a functioning Wan GGUF install.
    Performance on a GTX 1660 SUPER 6 GB is experimental and unverified.
    """
    for p in references:
        if not p.is_file():
            raise ComfyError(f"Uploaded source is missing: {p.name}")
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        raise ComfyError("FFmpeg and FFprobe are required")
    shots = plan_shots(prompt, references)
    folder = root / 'longform' / _fingerprint(references, prompt, narration)
    folder.mkdir(parents=True, exist_ok=True)
    width = int(os.getenv('WAN_WIDTH', '288'))
    height = int(os.getenv('WAN_HEIGHT', '512'))
    if min(width, height) < 128 or width % 16 or height % 16:
        raise ValueError("WAN_WIDTH and WAN_HEIGHT must be multiples of 16")
    outputs: list[Path] = []
    with ComfyClient(os.getenv('COMFYUI_URL', 'http://127.0.0.1:8188')) as comfy:
        comfy.health()
        names: dict[Path, str] = {}
        for i, shot in enumerate(shots):
            completed = folder / f"scene_{i:03d}.mp4"
            if completed.is_file() and completed.stat().st_size > 2048:
                outputs.append(completed)
                update(f"Reusing shot {i+1}/{SHOT_COUNT}", 0.90*(i+1)/SHOT_COUNT)
                continue
            photo = shot['reference']
            if photo not in names:
                names[photo] = comfy.upload(photo)
            update(f"AI video scene {i+1}/{SHOT_COUNT}", 0.90*i/SHOT_COUNT)
            graph = image_to_video_graph(
                names[photo], shot['prompt'], SHOT_SECONDS,
                f"realmotion/tenmin_{folder.name}_{i:03d}",
                width=width, height=height)
            pid = comfy.submit(graph)
            raw = folder / f"raw_{i:03d}.mp4"
            comfy.wait_and_download(pid, raw, timeout=7200)
            tmp = folder / f"scene_{i:03d}.tmp.mp4"
            try:
                normalize_clip(raw, tmp, SHOT_SECONDS, resolution='720:1280')
                if tmp.stat().st_size < 2048:
                    raise ComfyError(f"Rendered scene {i+1} was too small")
                os.replace(tmp, completed)
                outputs.append(completed)
                raw.unlink(missing_ok=True)
            finally:
                tmp.unlink(missing_ok=True)
            update(f"Finished AI scene {i+1}/{SHOT_COUNT}", 0.90*(i+1)/SHOT_COUNT)

    update("Joining 120 AI video scenes into a ten-minute film", .91)
    silent = folder / 'film_silent.mp4'
    concatenate_clips(outputs, silent, folder)
    output.parent.mkdir(parents=True, exist_ok=True)
    if narration.strip():
        voice = _full_voiceover(narration, folder, update)
        update("Mixing Moroccan Arabic voiceover into MP4", .98)
        add_speech_to_clip(silent, voice, output, LONG_SECONDS)
    else:
        shutil.copyfile(silent, output)
    if not output.is_file() or output.stat().st_size < 5000:
        raise ComfyError("Long-form MP4 was not created")
    update("Ten-minute MP4 finished", 1.)
    return str(output)
