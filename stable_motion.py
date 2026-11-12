"""Source-preserving 2.5D food animation (NOT diffusion-generated motion).

Keeps photographed food fixed except for downscaling and a subtle translucent
steam overlay. Uses only Pillow, FFmpeg and CPU; never pretends to be Wan AI.
"""
from __future__ import annotations

import math
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw, ImageFilter, ImageOps


class StableMotionCancelled(RuntimeError):
    pass


def choose_output_size(source: Path) -> tuple[int, int]:
    """Pick a standard canvas without forcing landscape photos to portrait."""
    with Image.open(source) as image:
        w, h = ImageOps.exif_transpose(image).size
    if w <= 0 or h <= 0:
        raise ValueError('Source image has invalid dimensions')
    ratio = w / h
    if ratio > 1.12:
        return (1280, 720)
    if ratio < 0.89:
        return (720, 1280)
    return (960, 960)


def choose_wan_size(source: Path) -> tuple[int, int]:
    """Conservative 6 GB-VRAM latent canvas; model memory use is unverified."""
    w, h = choose_output_size(source)
    if w > h:
        return (512, 288)
    if h > w:
        return (288, 512)
    return (384, 384)


def source_canvas(source: Path, size: tuple[int, int]) -> Image.Image:
    with Image.open(source) as img:
        photo = ImageOps.exif_transpose(img).convert('RGB')
    blurred = ImageOps.fit(photo, size, method=Image.Resampling.LANCZOS)
    blurred = blurred.filter(ImageFilter.GaussianBlur(30))
    blurred = Image.blend(blurred, Image.new('RGB', size, (19, 19, 22)), .19)
    fitted = ImageOps.contain(photo, size, method=Image.Resampling.LANCZOS)
    blurred.paste(fitted, ((size[0] - fitted.width) // 2,
                           (size[1] - fitted.height) // 2))
    return blurred


def steam_layer(width: int, height: int, seconds: float,
                *, strength: float = .65) -> Image.Image:
    """Animate transparent soft steam; food itself is never regenerated."""
    sw, sh = max(1, width // 4), max(1, height // 4)
    steam = Image.new('RGBA', (sw, sh), (0, 0, 0, 0))
    draw = ImageDraw.Draw(steam, 'RGBA')
    cx, cy = sw * .52, sh * .57
    for i in range(12):
        age = (seconds * .25 + i / 12) % 1.0
        drift = math.sin(seconds * .95 + i * 1.9)
        x = cx + (i % 4 - 1.5) * sw * .035 + drift * sw * .022
        y = cy - age * sh * .39
        radius_x = sw * (.012 + .025 * age)
        radius_y = sh * (.035 + .025 * age)
        fade = max(0., math.sin(math.pi * age)) ** .8
        alpha = round(19 * strength * fade)
        if alpha:
            draw.ellipse((x-radius_x, y-radius_y, x+radius_x, y+radius_y),
                         fill=(238, 238, 229, alpha))
    steam = steam.filter(ImageFilter.GaussianBlur(max(2, sw // 55)))
    return steam.resize((width, height), Image.Resampling.BILINEAR)


def render_stable_food_video(source: Path, destination: Path, seconds: int,
                             update: Callable[[str, float], None],
                             cancel_event: threading.Event | None = None) -> str:
    """High-fidelity atmospheric motion for a STILL, not AI object animation."""
    if not 1 <= seconds <= 10:
        raise ValueError('Food stabilization supports only 1 to 10 seconds')
    if not source.is_file():
        raise FileNotFoundError(source)
    if not shutil.which('ffmpeg'):
        raise RuntimeError('FFmpeg is required for stable food video encoding')
    size = choose_output_size(source)
    base = source_canvas(source, size).convert('RGBA')
    destination.parent.mkdir(parents=True, exist_ok=True)
    fps, count = 24, seconds * 24
    args = [
        'ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'rawvideo',
        '-pix_fmt', 'rgb24', '-s', f'{size[0]}x{size[1]}', '-r', str(fps),
        '-i', 'pipe:0', '-an', '-c:v', 'libx264', '-preset', 'veryfast',
        '-crf', '18', '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
        str(destination)
    ]
    update(f'Stable food: preserving source pixels at {size[0]}x{size[1]}', .08)
    process = subprocess.Popen(args, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for frame_index in range(count):
            if cancel_event is not None and cancel_event.is_set():
                raise StableMotionCancelled('Source-preserving animation cancelled')
            overlay = steam_layer(*size, frame_index/fps)
            frame = Image.alpha_composite(base, overlay).convert('RGB')
            process.stdin.write(frame.tobytes())
            if frame_index % max(1, fps//2) == 0:
                update(f'Stable food: adding delicate steam {frame_index+1}/{count}',
                       .10 + .61 * (frame_index+1)/count)
        process.stdin.close()
        if process.wait(timeout=180) != 0:
            raise RuntimeError('FFmpeg failed: ' + process.stderr.read().decode('utf-8', errors='replace')[-500:])
        if not destination.is_file() or destination.stat().st_size < 10_000:
            raise RuntimeError('Source-preserving MP4 was not produced')
        update('Stable food: source-preserving MP4 ready for finishing', .77)
        return str(destination)
    except Exception:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)
        destination.unlink(missing_ok=True)
        raise
    finally:
        if process.stdin and not process.stdin.closed:
            process.stdin.close()
        if process.stderr:
            process.stderr.close()
