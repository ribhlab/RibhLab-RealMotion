"""Verify light Wan 5B GGUF and local audio+video preview (no GPU needed)."""
from __future__ import annotations

import subprocess
import wave
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import app as server
import studio


def test_default_wan_uses_gguf_loader(monkeypatch):
    monkeypatch.delenv("WAN_I2V_MODEL", raising=False)
    graph = studio.image_to_video_graph(
        "portrait.jpg", "A child waves and smiles in a parked miniature car.",
        5, "realmotion/preview", width=288, height=512, seed=7)
    assert graph["1"]["class_type"] == "UnetLoaderGGUF"
    assert graph["1"]["inputs"]["unet_name"] == "Wan2.2-TI2V-5B-Q2_K.gguf"
    assert graph["8"]["inputs"]["length"] == 81
    assert graph["8"]["inputs"]["width"] == 288
    assert graph["8"]["inputs"]["height"] == 512


def test_fp16_legacy_remains_selectable(monkeypatch):
    monkeypatch.setenv("WAN_I2V_MODEL", "wan2.2_ti2v_5B_fp16.safetensors")
    graph = studio.image_to_video_graph(
        "portrait.jpg", "A child waves and smiles in a parked miniature car.",
        5, "realmotion/test")
    assert graph["1"]["class_type"] == "UNETLoader"


def test_preview_needs_only_one_talking_character(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DATA", tmp_path)
    client = TestClient(server.app)
    project = client.post("/api/projects").json()
    pid = project["id"]
    assert client.post(f"/api/projects/{pid}/preview").status_code == 422

    b = BytesIO()
    Image.new("RGB", (64, 64), (100, 100, 100)).save(b, "PNG")
    res = client.post(
        f"/api/projects/{pid}/characters/driver/image",
        files={"file": ("portrait.png", b.getvalue(), "image/png")})
    assert res.status_code == 200
    jobs = []
    monkeypatch.setattr(server.executor, "submit", lambda *a: jobs.append(a))
    preview = client.post(f"/api/projects/{pid}/preview")
    assert preview.status_code == 202
    assert preview.json()["mode"] == "preview"
    assert len(jobs) == 1
    assert jobs[0][-1] is True


def test_ffmpeg_mixes_voice_into_video(tmp_path):
    import shutil
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg is unavailable")
    raw = tmp_path / "raw.mp4"
    subprocess.run([
        "ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
        "color=c=blue:s=128x192:r=16", "-t", "1",
        "-c:v", "libx264", str(raw)
    ], check=True)
    normalized = tmp_path / "normalized.mp4"
    studio.normalize_clip(raw, normalized, 1, resolution="128:192")

    speech = tmp_path / "voice.wav"
    with wave.open(str(speech), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\\x00\\x00" * 16000)
    result = tmp_path / "av.mp4"
    studio.add_speech_to_clip(normalized, speech, result, 1)
    assert result.is_file() and result.stat().st_size > 1000
    output = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
        "-of", "csv=p=0", str(result)], text=True)
    assert "video" in output
    assert "audio" in output
