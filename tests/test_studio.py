from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from fastapi.testclient import TestClient

from studio import image_to_video_graph, speech_to_video_graph, normalize_clip, concatenate_clips
import app as server


def test_wan_i2v_graph_links():
    graph = image_to_video_graph('portrait.jpg', 'A person moves and waves.', 5, 'realm/test', seed=7)
    assert graph['8']['class_type'] == 'Wan22ImageToVideoLatent'
    assert graph['8']['inputs']['length'] == 81
    assert graph['9']['inputs']['seed'] == 7
    assert graph['12']['class_type'] == 'SaveVideo'


def test_wan_s2v_graph_wires_audio():
    graph = speech_to_video_graph('portrait.jpg', 'spoken.wav', 'A person speaks naturally.', 5, 'realm/talk', seed=7)
    assert graph['11']['class_type'] == 'WanSoundImageToVideo'
    assert graph['7']['inputs']['audio'] == ['5', 0]
    assert graph['14']['inputs']['audio'] == ['5', 0]


def test_scene_limit():
    with pytest.raises(ValueError):
        image_to_video_graph('x.png', 'hello', 31, 'x')


def test_project_and_storyboard(tmp_path, monkeypatch):
    monkeypatch.setattr(server, 'DATA', tmp_path)
    client = TestClient(server.app)
    resp = client.post('/api/projects')
    assert resp.status_code == 201
    proj = resp.json()
    assert len(proj['scenes']) == 6
    assert sum(s['seconds'] for s in proj['scenes']) == 30
    assert client.get('/api/projects/'+proj['id']).status_code == 200
    assert client.put(f"/api/projects/{proj['id']}/storyboard",json={'scenes':proj['scenes']}).status_code == 200
    assert client.put(f"/api/projects/{proj['id']}/storyboard",json={'scenes':[proj['scenes'][0]]}).status_code == 422
    assert client.post(f"/api/projects/{proj['id']}/render").status_code == 422
    assert client.get('/api/projects/../video').status_code in (404, 422)


def test_upload_image(tmp_path, monkeypatch):
    from PIL import Image
    from io import BytesIO
    monkeypatch.setattr(server, 'DATA', tmp_path)
    client = TestClient(server.app)
    pid = client.post('/api/projects').json()['id']
    b = BytesIO();Image.new('RGB',(64,64),(20,50,60)).save(b,'PNG')
    assert client.post(f'/api/projects/{pid}/characters/spider/image',files={'file':('child.png',b.getvalue(),'image/png')}).status_code == 200
    assert client.get(f'/api/projects/{pid}/characters/spider/image').status_code == 200


def test_ffmpeg_concat(tmp_path):
    import shutil, subprocess
    if not shutil.which('ffmpeg'):
        pytest.skip('ffmpeg not installed')
    src = tmp_path/'raw.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=blue:s=64x64:r=16',
                    '-t','1','-c:v','libx264',str(src)],check=True)
    clips=[]
    for i in range(2):
        dst=tmp_path/f'n{i}.mp4'
        normalize_clip(src,dst,1,resolution='128:192')
        clips.append(dst)
    target=tmp_path/'final.mp4'
    concatenate_clips(clips,target,tmp_path)
    assert target.exists() and target.stat().st_size>1000
