"""Regression tests for local-only Wan Q2 preflight and official SaveVideo shape."""
import pytest
from fastapi.testclient import TestClient

import app
from studio import (
    WAN_REQUIRED_NODES,
    check_wan_ready,
    image_to_video_graph,
    ltx_image_to_video_graph,
    speech_to_video_graph,
)


def _nodes():
    result = {name: {"input": {"required": {}}} for name in WAN_REQUIRED_NODES}
    result["UnetLoaderGGUF"]["input"]["required"]["unet_name"] = [["Wan2.2-TI2V-5B-Q2_K.gguf"]]
    result["VAELoader"]["input"]["required"]["vae_name"] = [["wan2.2_vae.safetensors"]]
    result["CLIPLoader"]["input"]["required"].update({
        "clip_name": [["umt5_xxl_fp8_e4m3fn_scaled.safetensors"]],
        "type": [["wan", "ltxv"]],
    })
    return result


def test_wan_all_requirements_present(monkeypatch):
    monkeypatch.delenv("WAN_I2V_MODEL", raising=False)
    monkeypatch.delenv("WAN_I2V_VAE", raising=False)
    monkeypatch.delenv("WAN_TEXT_ENCODER", raising=False)
    assert check_wan_ready(_nodes()) == []


def test_wan_reports_missing_files_and_gguf(monkeypatch):
    monkeypatch.delenv("WAN_I2V_MODEL", raising=False)
    info = _nodes()
    del info["UnetLoaderGGUF"]
    info["VAELoader"]["input"]["required"]["vae_name"] = [[]]
    missing = check_wan_ready(info)
    assert "UnetLoaderGGUF" in missing
    assert "Wan VAE: wan2.2_vae.safetensors" in missing


def test_wan_rejects_wrong_clip_family():
    info = _nodes()
    info["CLIPLoader"]["input"]["required"]["type"] = [["ltxv"]]
    assert "CLIPLoader type 'wan' (update ComfyUI)" in check_wan_ready(info)


def test_save_video_outputs_mp4_h264():
    graphs = [
        (image_to_video_graph("photo.png", "A child waves.", 3, "x", seed=2), "12"),
        (ltx_image_to_video_graph("photo.png", "A child waves.", 3, "x", seed=2), "13"),
        (speech_to_video_graph("photo.png", "voice.wav", "A child talks.", 3, "x", seed=2), "15"),
    ]
    for graph, id in graphs:
        payload = graph[id]["inputs"]
        assert payload["format"] == "mp4"
        assert payload["codec"] == {"codec": "h264"}
        assert "format.codec" not in payload


def test_preflight_offline_is_actionable(monkeypatch):
    import httpx
    class Unreachable:
        def __init__(self, _url):
            pass
        def __enter__(self):
            raise httpx.ConnectError("ComfyUI offline")
        def __exit__(self, *args):
            return None
    import studio
    monkeypatch.setattr(studio, "ComfyClient", Unreachable)
    response = TestClient(app.app).get("/api/engines/wan/status")
    assert response.status_code == 200
    data = response.json()
    assert data["ready"] is False
    assert "ComfyUI not reachable" in data["missing"][0]
    assert data["cost"] == "free_local"
