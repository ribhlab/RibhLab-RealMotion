"""Tests for planned 600-second / 120-scene local film production."""
from __future__ import annotations
import uuid
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

import app as server
import long_form


def test_ten_minute_shot_plan_is_real_duration():
    refs=[Path('/tmp/image-one.jpg'),Path('/tmp/image-two.jpg')]
    p=long_form.plan_shots('Cinematic camera movement around a Moroccan restaurant.', refs)
    assert len(p)==120
    assert sum(i['seconds'] for i in p)==600
    assert p[0]['reference']==refs[0]
    assert p[1]['reference']==refs[1]
    assert p[119]['seconds']==5
    assert all('cinematic' in shot['prompt'].lower() for shot in p)


def test_long_voice_chunks_do_not_lose_words():
    src=' '.join(['مرحبا', 'بالمغرب', 'الأصيل']*500)
    parts=long_form._speech_chunks(src,max_chars=180)
    assert len(parts)>10
    assert all(len(x)<=180 for x in parts)
    assert ' '.join(parts)==src


def test_ten_minute_endpoint_queues_multiple_uploaded_images(tmp_path, monkeypatch):
    monkeypatch.setattr(server, 'DATA', tmp_path)
    with server._lock:
        server._jobs.clear()
    api=TestClient(server.app)
    ids=[]
    for color in [(10,30,70),(50,80,120)]:
        buffer=BytesIO()
        Image.new('RGB',(64,64),color).save(buffer,'PNG')
        response=api.post('/api/studio/assets',
                          files={'file':('shot.png',buffer.getvalue(),'image/png')})
        assert response.status_code==201,response.text
        ids.append(response.json()['id'])
    calls=[]
    monkeypatch.setattr(server.executor,'submit',lambda *args: calls.append(args))
    result=api.post('/api/studio/generate',json={
        'asset_id':ids[0], 'asset_ids':ids,
        'prompt':'Film showing delicious Moroccan meals. الكلام: مرحبا بالزوار',
        'seconds':600,'with_voice':True})
    assert result.status_code==202,result.text
    assert result.json()['mode']=='longform'
    assert len(calls)==1
    assert len(calls[0][2])==2
    assert calls[0][3].startswith('Film showing')


def test_arabic_voice_marker_is_separated_for_long_film(tmp_path,monkeypatch):
    monkeypatch.setattr(server,'DATA',tmp_path)
    ids=[uuid.uuid4()]
    folder=server._studio_folder(ids[0])
    folder.mkdir(parents=True)
    Image.new('RGB',(64,64)).save(folder/'reference.jpg')
    job_id=str(uuid.uuid4())
    with server._lock:
        server._jobs[job_id]={'status':'queued','progress':0,'message':''}
    captured=[]
    def render(refs, visual, narration, output, root, update):
        captured.append((visual,narration))
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_bytes(b'DUMMY FILE FOR UNIT TEST ONLY')
        update('done',1)
    monkeypatch.setattr(long_form,'render_ten_minute_film',render)
    server._studio_long_worker(
        job_id,ids,'Cinematic Moroccan food. الكلام: بالصحة والراحة',
        True)
    assert captured == [('Cinematic Moroccan food.','بالصحة والراحة')]
    assert server._jobs[job_id]['status']=='done'


def test_studio_duration_rejects_unplanned_intermediate_lengths():
    result=TestClient(server.app).post('/api/studio/generate',json={
        'asset_id':str(uuid.uuid4()),'prompt':'Generate cinematic AI video',
        'seconds':180})
    assert result.status_code==422
