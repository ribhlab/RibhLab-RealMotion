"""Simple creative studio endpoints: upload references + single prompt + local job."""
from __future__ import annotations

import subprocess
from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

import app as server
import studio


def test_simple_studio_image_upload_preview_and_generation(tmp_path, monkeypatch):
    monkeypatch.setattr(server, 'DATA', tmp_path)
    with server._lock:
        server._jobs.clear()
    client = TestClient(server.app)
    page = client.get('/')
    assert page.status_code == 200
    assert 'id="prompt"' in page.text
    assert 'id="fileInput"' in page.text
    assert 'id="generate"' in page.text

    image = BytesIO()
    Image.new('RGB', (80, 80), (40, 70, 120)).save(image, 'PNG')
    upload = client.post('/api/studio/assets',
                         files={'file': ('portrait.png', image.getvalue(), 'image/png')})
    assert upload.status_code == 201, upload.text
    body = upload.json()
    assert body['kind'] == 'image'
    assert client.get(body['preview_url']).headers['content-type'] == 'image/jpeg'

    scheduled = []
    monkeypatch.setattr(server.executor, 'submit', lambda *a: scheduled.append(a))
    job = client.post('/api/studio/generate', json={
        'asset_id': body['id'],
        'prompt': 'A cinematic camera moves around the character. الكلام: مرحبا',
        'seconds': 5, 'with_voice': True
    })
    assert job.status_code == 202, job.text
    assert job.json()['mode'] == 'studio'
    assert len(scheduled) == 1
    assert scheduled[0][-1].endswith('الكلام: مرحبا')


def test_studio_video_reference_is_first_frame(tmp_path, monkeypatch):
    monkeypatch.setattr(server, 'DATA', tmp_path)
    video = tmp_path/'sample.mp4'
    subprocess.run([
        'ffmpeg','-hide_banner','-loglevel','error','-y',
        '-f','lavfi','-i','color=c=red:s=128x128:r=4','-t','1',
        '-c:v','mpeg4',str(video)], check=True)
    client = TestClient(server.app)
    up = client.post('/api/studio/assets',
                     files={'file': ('reference.mp4', video.read_bytes(), 'video/mp4')})
    assert up.status_code == 201, up.text
    assert up.json()['kind'] == 'video'
    assert up.json()['reference_mode'] == 'first_frame'
    assert client.get(up.json()['preview_url']).status_code == 200


def test_studio_worker_splits_dialogue_from_motion_prompt(tmp_path, monkeypatch):
    import uuid
    monkeypatch.setattr(server, 'DATA', tmp_path)
    asset_id=uuid.uuid4()
    folder=server._studio_folder(asset_id)
    folder.mkdir(parents=True)
    Image.new('RGB',(32,32)).save(folder/'reference.jpg')
    job_id=str(uuid.uuid4())
    with server._lock:
        server._jobs[job_id]={'id':job_id,'status':'queued','progress':0,'message':''}
    calls=[]
    def fake_render(reference, prompt, seconds, output, update, *, narration='', cancel_event=None):
        calls.append((prompt, narration, seconds))
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_bytes(b'FAKE TEST ONLY')
        update('ready',1)
    monkeypatch.setattr(studio, 'render_single_studio_video', fake_render)
    server._studio_worker(job_id, asset_id,
                          'A friendly character waves. الكلام: السلام عليكم',
                          5, 'A friendly character waves. الكلام: السلام عليكم')
    assert calls==[('A friendly character waves.', 'السلام عليكم',5)]
    assert server._jobs[job_id]['status']=='done'
