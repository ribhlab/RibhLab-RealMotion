"""Checks for true source orientation and honest high-fidelity food mode."""
from __future__ import annotations

import uuid
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import app as server
import stable_motion


def image(path, dimensions):
    Image.new("RGB", dimensions, color=(130, 88, 43)).save(path)
    return path


@pytest.mark.parametrize("dimensions, expected_export, expected_latent", [
    ((1672, 941), (1280, 720), (512, 288)),
    ((800, 1200), (720, 1280), (288, 512)),
    ((900, 900), (960, 960), (384, 384)),
])
def test_source_aspect_is_preserved(tmp_path, dimensions, expected_export, expected_latent):
    source = image(tmp_path / "reference.jpg", dimensions)
    assert stable_motion.choose_output_size(source) == expected_export
    assert stable_motion.choose_wan_size(source) == expected_latent
    background = stable_motion.source_canvas(source, expected_export)
    assert background.size == expected_export
    assert background.getbbox() is not None


def test_steam_is_translucent_and_changes_over_time():
    a = stable_motion.steam_layer(640, 360, 0.)
    b = stable_motion.steam_layer(640, 360, 1.4)
    assert a.size == (640, 360) and b.size == (640, 360)
    assert a.getbbox() and b.getbbox()
    assert a.tobytes() != b.tobytes()
    assert a.getchannel('A').getextrema()[1] < 100


def test_stable_food_queue_uses_explicit_render_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(server, 'DATA', tmp_path)
    with server._lock:
        server._jobs.clear()
        server._job_logs.clear()
        server._job_cancel.clear()
    client = TestClient(server.app)
    pic = BytesIO()
    Image.new('RGB', (128, 70)).save(pic, 'PNG')
    upload = client.post('/api/studio/assets', files={
        'file': ('food.png', pic.getvalue(), 'image/png')})
    assert upload.status_code == 201, upload.text
    scheduled = []
    monkeypatch.setattr(server.executor, 'submit', lambda *a: scheduled.append(a))
    payload = {
        'asset_id': upload.json()['id'],
        'prompt': 'Natural steam on a Moroccan tagine',
        'seconds': 3,
        'render_mode': 'stable_food',
        'with_voice': False
    }
    res = client.post('/api/studio/generate', json=payload)
    assert res.status_code == 202, res.text
    assert res.json()['render_mode'] == 'stable_food'
    assert res.json()['mode'] == 'studio'
    assert len(scheduled) == 1
    invalid = client.post('/api/studio/generate', json={**payload, 'seconds': 600})
    assert invalid.status_code == 422


def test_firefly_style_ui_contains_real_options():
    response = TestClient(server.app).get('/')
    assert response.status_code == 200
    for element in ('renderMode', 'cameraMotion', 'duration', 'withVoice',
                    'prompt', 'chooseMain', 'previewImg', 'generate', 'copyLogs',
                    'cancelGeneration', 'aspectInfo'):
        assert 'id="' + element + '"' in response.text
    assert 'value="stable_food"' in response.text
    assert 'value="wan_ai"' in response.text
