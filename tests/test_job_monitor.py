"""Progress monitor/cancel behavior without requiring GPU or real MacBook."""
from __future__ import annotations

import uuid
import threading
import shutil

from fastapi.testclient import TestClient

import app as server
import remote_worker


def test_can_cancel_studio_job_and_copy_log(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DATA", tmp_path)
    job_id = str(uuid.uuid4())
    with server._lock:
        server._jobs[job_id] = {
            "id": job_id, "mode": "studio", "status": "queued",
            "progress": 0, "phase": "queued", "message": "Queued"
        }
        server._job_cancel[job_id] = threading.Event()
    client = TestClient(server.app)
    result = client.post(f"/api/jobs/{job_id}/cancel")
    assert result.status_code == 200
    assert result.json()["status"] == "cancelling"
    assert server._job_cancel[job_id].is_set()
    log = client.get(f"/api/jobs/{job_id}/logs")
    assert log.status_code == 200
    assert "Cancel requested" in log.text
    assert (tmp_path / "job_logs" / (job_id + ".log")).is_file()
    server._job_finished(job_id, "done", "Should not finish", video_url="/fake")
    assert server._jobs[job_id]["status"] == "cancelled"
    assert "video_url" not in server._jobs[job_id]


def test_macbook_worker_reports_real_processing_stages(tmp_path, monkeypatch):
    secret = "w" * 64
    monkeypatch.setenv("REALMOTION_WORKER_TOKEN", secret)
    monkeypatch.setattr(remote_worker.shutil, "which", lambda p: "/fake/ffmpeg")
    stages = []
    original = remote_worker._stage

    def record(job, phase, note):
        stages.append(phase)
        original(job, phase, note)

    monkeypatch.setattr(remote_worker, "_stage", record)
    monkeypatch.setattr(
        remote_worker, "normalize_clip",
        lambda source, target, seconds, resolution: shutil.copyfile(source, target)
    )

    async def fake_speech(text, target, voice):
        target.write_bytes(b"FAKE WAVE TEST DATA")

    monkeypatch.setattr(remote_worker, "synthesize_speech", fake_speech)
    monkeypatch.setattr(
        remote_worker, "add_speech_to_clip",
        lambda video, speech, output, seconds: shutil.copyfile(video, output)
    )
    job_id = str(uuid.uuid4())
    headers = {"X-RealMotion-Token": secret}
    client = TestClient(remote_worker.app)
    result = client.post(
        "/process",
        headers=headers,
        data={"seconds": "3", "narration": "مرحبا", "job_id": job_id},
        files={"video": ("raw.mp4", b"FAKE VIDEO DATA " * 128, "video/mp4")},
    )
    assert result.status_code == 200, result.text
    assert result.content.startswith(b"FAKE VIDEO DATA")
    state = client.get(f"/status/{job_id}", headers=headers)
    assert state.status_code == 200
    assert state.json()["phase"] == "done"
    assert {"encoding", "voice", "mixing", "done"}.issubset(set(stages))
    assert client.get(f"/status/{job_id}").status_code == 401


def test_ui_exposes_controls_for_debugging():
    client = TestClient(server.app)
    response = client.get("/")
    assert response.status_code == 200
    for widget_id in ("cancelGeneration", "jobDashboard", "logsText", "copyLogs",
                      "workerConnection", "debugPanel", "productionStages"):
        assert 'id="' + widget_id + '"' in response.text
