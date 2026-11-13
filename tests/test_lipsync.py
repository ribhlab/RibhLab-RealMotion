"""MuseTalk optional true lip-sync contract. No GPU/model downloads in CI."""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi.testclient import TestClient

import app
import lipsync


def test_lipsync_status_is_read_only_and_reports_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("REALMOTION_MUSETALK_DIR", str(tmp_path / "not-installed"))
    monkeypatch.delenv("REALMOTION_MUSETALK_PYTHON", raising=False)
    result = TestClient(app.app).get("/api/engines/lipsync/status")
    assert result.status_code == 200
    body = result.json()
    assert body["engine"] == "musetalk_v15"
    assert body["ready"] is False
    assert any("scripts/inference.py" in s for s in body["missing"])
    assert body["gpu_tested"] is False


def test_lipsync_requires_real_models_not_just_checkout(tmp_path, monkeypatch):
    root = tmp_path / "MuseTalk"
    (root / "scripts").mkdir(parents=True)
    (root / "scripts" / "inference.py").write_text("print('placeholder')")
    monkeypatch.setenv("REALMOTION_MUSETALK_DIR", str(root))
    result = lipsync.check_lipsync_ready()
    assert not result["ready"]
    assert any("unet.pth" in s for s in result["missing"])


def test_studio_request_rejects_unsupported_10min_lipsync(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DATA", tmp_path)
    asset_id = uuid.uuid4()
    folder = tmp_path / "studio_assets" / str(asset_id)
    folder.mkdir(parents=True)
    (folder / "reference.jpg").write_bytes(b"image")
    resp = TestClient(app.app).post("/api/studio/generate", json={
        "asset_id": str(asset_id),
        "prompt": "A person talks to camera. الكلام: السلام عليكم",
        "seconds": 600,
        "render_mode": "wan_ai",
        "with_voice": True,
        "lip_sync": True,
    })
    assert resp.status_code == 422
    assert "lip sync" in resp.json()["detail"].lower()


def test_studio_request_requires_voice_and_spoken_text(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DATA", tmp_path)
    aid = uuid.uuid4()
    folder = tmp_path / "studio_assets" / str(aid)
    folder.mkdir(parents=True)
    (folder / "reference.jpg").write_bytes(b"image")
    client = TestClient(app.app)
    base = {"asset_id": str(aid), "prompt": "Someone waves while facing camera.",
            "seconds": 3, "render_mode": "wan_ai", "lip_sync": True}
    assert client.post("/api/studio/generate", json={**base, "with_voice": False}).status_code == 422
    result = client.post("/api/studio/generate", json={**base, "with_voice": True})
    assert result.status_code == 422
    assert "الكلام" in result.json()["detail"]


def test_studio_lipsync_rejects_incomplete_install(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DATA", tmp_path)
    monkeypatch.setenv("REALMOTION_MUSETALK_DIR", str(tmp_path / "not-installed"))
    aid = uuid.uuid4()
    folder = tmp_path / "studio_assets" / str(aid)
    folder.mkdir(parents=True)
    (folder / "reference.jpg").write_bytes(b"image")
    r = TestClient(app.app).post("/api/studio/generate", json={
        "asset_id": str(aid), "prompt": "A person talks. الكلام: مرحبا",
        "seconds": 3, "render_mode": "wan_ai", "lip_sync": True, "with_voice": True,
    })
    assert r.status_code == 422
    assert "Install-LipSync.bat" in r.json()["detail"]


def test_storyboard_saves_explicit_lipsync_flag(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DATA", tmp_path)
    cli = TestClient(app.app)
    project = cli.post("/api/projects").json()
    scenes = project["scenes"]
    scenes[-1]["lip_sync"] = True
    save = cli.put(f"/api/projects/{project['id']}/storyboard",
                   json={"scenes": scenes})
    assert save.status_code == 200
    assert save.json()["scenes"][-1]["lip_sync"] is True


def test_render_lipsync_rejects_missing_install_before_processing(tmp_path, monkeypatch):
    import pytest
    monkeypatch.setenv("REALMOTION_MUSETALK_DIR", str(tmp_path / "not-installed"))
    video, audio = tmp_path / "input.mp4", tmp_path / "voice.wav"
    video.write_bytes(b"video")
    audio.write_bytes(b"audio")
    with pytest.raises(lipsync.LipSyncError, match="Install-LipSync.bat"):
        lipsync.render_lipsync(video, audio, tmp_path / "output.mp4", seconds=3)


def test_lipsync_inference_constructs_real_musetalk_command(tmp_path, monkeypatch):
    root = tmp_path / "MuseTalk"
    (root / ".venv/Scripts").mkdir(parents=True)
    fake_python = root / ".venv/Scripts/python.exe"
    fake_python.write_bytes(b"fake interpreter")
    monkeypatch.setenv("REALMOTION_MUSETALK_DIR", str(root))
    monkeypatch.setenv("REALMOTION_MUSETALK_PYTHON", str(fake_python))
    monkeypatch.setattr(lipsync, "check_lipsync_ready", lambda: {"ready": True, "missing": []})
    source, voice = tmp_path / "clip.mp4", tmp_path / "voice.wav"
    source.write_bytes(b"source")
    voice.write_bytes(b"voice")
    commands = []
    def fake_ffmpeg(cmd, **kwargs):
        commands.append(cmd)
        Path(cmd[-1]).write_bytes(b"f" * 1800)
    def fake_model(args, *, root, timeout, cancel_event=None):
        commands.append(args)
        out_dir = Path(args[args.index("--result_dir") + 1]) / "v15"
        out_dir.mkdir(parents=True)
        (out_dir / "synchronized.mp4").write_bytes(b"s" * 2100)
    monkeypatch.setattr(lipsync, "_run", fake_ffmpeg)
    monkeypatch.setattr(lipsync, "_run_inference", fake_model)
    monkeypatch.setattr(lipsync.shutil, "which", lambda x: "/usr/bin/ffmpeg" if x in ("ffmpeg", "ffprobe") else None)
    result = lipsync.render_lipsync(
        source, voice, tmp_path / "result.mp4", seconds=3,
        workdir=tmp_path / "jobs")
    assert result.is_file()
    args = next(command for command in commands if "scripts.inference" in command)
    assert "--use_float16" in args
    assert args[args.index("--batch_size") + 1] == "1"
    assert args[args.index("--version") + 1] == "v15"
    assert len(commands) == 4  # normalized video, WAV, real model, real export
