"""Free, local LTX 2B image-to-video integration (no paid cloud inference)."""
from __future__ import annotations

from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import app as server
from studio import (
    LTX_CHECKPOINT, LTX_TEXT_ENCODER, LTX_REQUIRED_NODES,
    ltx_image_to_video_graph, check_ltx_ready,
)


def test_ltx_graph_follows_native_comfy_i2v():
    graph = ltx_image_to_video_graph(
        "tagine.jpg", "Steam gently rises from food.", 3,
        "realmotion/unit_test", width=512, height=288, seed=42
    )
    assert graph["1"]["class_type"] == "CheckpointLoaderSimple"
    assert graph["1"]["inputs"]["ckpt_name"] == LTX_CHECKPOINT
    assert graph["2"]["inputs"]["type"] == "ltxv"
    assert graph["2"]["inputs"]["device"] == "cpu"
    assert graph["2"]["inputs"]["clip_name"] == LTX_TEXT_ENCODER
    assert graph["6"]["class_type"] == "LTXVImgToVideo"
    assert graph["6"]["inputs"]["image"] == ["3", 0]
    assert graph["6"]["inputs"]["length"] == 73
    assert graph["7"]["inputs"]["frame_rate"] == 24
    assert graph["8"]["inputs"]["steps"] == 8
    assert graph["10"]["class_type"] == "SamplerCustom"
    assert graph["10"]["inputs"]["cfg"] == 1.0
    assert graph["10"]["inputs"]["noise_seed"] == 42
    assert graph["13"]["class_type"] == "SaveVideo"
    assert not any("api" in str(v).lower() and "LtxApi" in str(v)
                   for v in graph.values())


@pytest.mark.parametrize("dims", [(511, 288), (320, 280), (96, 128)])
def test_ltx_rejects_incompatible_latent_dims(dims):
    with pytest.raises(ValueError):
        ltx_image_to_video_graph("x.jpg", "hello", 3, "realmotion/test",
                                 width=dims[0], height=dims[1])


@pytest.mark.parametrize("seconds", [0, 11, 600])
def test_ltx_rejects_invalid_short_clip(seconds):
    with pytest.raises(ValueError):
        ltx_image_to_video_graph("x.jpg", "hello", seconds, "test")


def test_ltx_preflight_identifies_missing_models_and_nodes():
    info = {k: {"input": {"required": {}}} for k in LTX_REQUIRED_NODES}
    info["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"] = [["something_else.safetensors"]]
    info["CLIPLoader"]["input"]["required"]["clip_name"] = [["umt5.safetensors"]]
    info["CLIPLoader"]["input"]["required"]["type"] = [["wan", "ltxv"]]
    missing = check_ltx_ready(info)
    assert any(LTX_CHECKPOINT in m for m in missing)
    assert any(LTX_TEXT_ENCODER in m for m in missing)
    info["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"] = [[LTX_CHECKPOINT]]
    info["CLIPLoader"]["input"]["required"]["clip_name"] = [[LTX_TEXT_ENCODER]]
    assert check_ltx_ready(info) == []
    info.pop("LTXVScheduler")
    assert "LTXVScheduler" in check_ltx_ready(info)


def test_ltx_queue_is_real_studio_job_without_gpu_side_effects(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DATA", tmp_path)
    with server._lock:
        server._jobs.clear()
        server._job_logs.clear()
        server._job_cancel.clear()
    client = TestClient(server.app)
    photo = BytesIO()
    Image.new("RGB", (128, 72)).save(photo, format="PNG")
    upload = client.post(
        "/api/studio/assets",
        files={"file": ("food.png", photo.getvalue(), "image/png")},
    )
    assert upload.status_code == 201, upload.text
    scheduled = []
    monkeypatch.setattr(server.executor, "submit", lambda *args: scheduled.append(args))
    request = {
        "asset_id": upload.json()["id"],
        "prompt": "Delicate steam rises from a Moroccan tagine.",
        "seconds": 3,
        "with_voice": False,
        "render_mode": "ltx_2b",
    }
    response = client.post("/api/studio/generate", json=request)
    assert response.status_code == 202, response.text
    assert response.json()["render_mode"] == "ltx_2b"
    assert len(scheduled) == 1
    blocked = client.post("/api/studio/generate", json={**request, "seconds": 600})
    assert blocked.status_code == 422


def test_ltx_mode_is_visible_in_studio():
    res = TestClient(server.app).get("/")
    assert res.status_code == 200
    assert 'value="ltx_2b"' in res.text
    assert 'id="ltxReady"' in res.text
