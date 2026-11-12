"""LAN worker tests run without NVIDIA, Wan models, Piper, or a network."""
import shutil

from fastapi.testclient import TestClient

import remote_worker
from studio import _process_studio_on_lan


def test_lan_worker_authentication(monkeypatch):
    monkeypatch.setenv("REALMOTION_WORKER_TOKEN", "a" * 64)
    client = TestClient(remote_worker.app)
    assert client.get("/health").status_code == 401
    assert client.get("/health", headers={"X-RealMotion-Token": "wrong"}).status_code == 401
    assert client.get("/health", headers={"X-RealMotion-Token": "a" * 64}).json()["role"] == "audio_and_postprocessing"


def test_worker_processes_mp4_without_voice(monkeypatch):
    monkeypatch.setenv("REALMOTION_WORKER_TOKEN", "a" * 64)
    monkeypatch.setattr(remote_worker.shutil, "which", lambda exe: "/fake/ffmpeg")
    monkeypatch.setattr(
        remote_worker, "normalize_clip",
        lambda source, target, seconds, resolution: shutil.copyfile(source, target)
    )
    client = TestClient(remote_worker.app)
    payload = b"synthetic test bytes " * 120
    response = client.post(
        "/process",
        headers={"X-RealMotion-Token": "a" * 64},
        data={"seconds": "5", "narration": ""},
        files={"video": ("clip.mp4", payload, "video/mp4")},
    )
    assert response.status_code == 200
    assert response.content == payload


def test_lan_offload_is_opt_in(tmp_path, monkeypatch):
    monkeypatch.delenv("REALMOTION_WORKER_URL", raising=False)
    assert not _process_studio_on_lan(
        tmp_path / "raw.mp4", tmp_path / "out.mp4", 5, "", lambda *a: None
    )
