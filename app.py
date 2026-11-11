"""RibhLab RealMotion: local-first storyboard and ComfyUI render orchestration."""
from __future__ import annotations

import json
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field, model_validator, field_validator

from studio import render_project

BASE = Path(__file__).resolve().parent
DATA = Path(os.getenv('REALMOTION_DATA_DIR', str(BASE / 'local_data'))).resolve()
DATA.mkdir(parents=True, exist_ok=True)
app = FastAPI(title='RibhLab RealMotion', version='0.1.0', docs_url='/api/docs')
app.mount('/static', StaticFiles(directory=BASE / 'static'), name='static')
executor = ThreadPoolExecutor(max_workers=1)
_lock = threading.RLock()
_jobs: dict[str, dict] = {}
ROLES = ('driver', 'unicorn', 'spider', 'batman')
MAX_UPLOAD = 20 * 1024 * 1024


class Scene(BaseModel):
    character: Literal['driver', 'unicorn', 'spider', 'batman']
    mode: Literal['move', 'talk'] = 'move'
    seconds: int = Field(ge=1, le=15)
    prompt: str = Field(min_length=12, max_length=1800)
    dialogue: str = Field(default='', max_length=800)
    voice: str = Field(default='ar-MA-JamalNeural', min_length=5, max_length=80)
    audio_file: str | None = None

    @field_validator('audio_file')
    @classmethod
    def validate_audio_file(cls, value):
        import re
        if value is not None and not re.fullmatch(r'audio-[0-9a-f]{16}\.(?:mp3|wav|m4a|ogg)', value):
            raise ValueError('Audio filename is not a valid uploaded asset')
        return value


class Storyboard(BaseModel):
    scenes: list[Scene] = Field(min_length=1, max_length=12)

    @model_validator(mode='after')
    def validate_total(self):
        if sum(scene.seconds for scene in self.scenes) != 30:
            raise ValueError('Total duration must be exactly 30 seconds')
        return self


DEFAULT_SCENES = [
    dict(character='driver', mode='move', seconds=5,
         prompt='Cinematic live-action. The same child in a navy formal suit sits securely in a parked yellow sports car with a seat belt, grins and waves. The car is stationary while the camera circles. Preserve his exact face, natural physics.'),
    dict(character='unicorn', mode='move', seconds=5,
         prompt='Magical live-action fantasy, the same girl with a pastel unicorn princess dress smiles and playfully waves from a stationary pink toy race car in a fairy-tale garden. Preserve her identity, realistic motion.'),
    dict(character='spider', mode='move', seconds=5,
         prompt='The same child wearing a red and blue superhero suit playfully jumps onto a safe soft playground mat, makes a web-throwing gesture and laughs; realistic smooth body movement, his face unchanged.'),
    dict(character='batman', mode='move', seconds=5,
         prompt='The same smiling child in a black bat-inspired superhero costume drives a small stationary toy batmobile simulator; moving lights and a gentle camera push, realistic joyful expression, consistent face.'),
    dict(character='driver', mode='talk', seconds=5,
         prompt='Close-up of the same child in the yellow sports car, facing camera and speaking clearly with natural expressive mouth and head motion, believable lip synchronization, face stays consistent.',
         dialogue='يلا صحابي، شكون مستعد لسباق الأبطال؟'),
    dict(character='unicorn', mode='talk', seconds=5,
         prompt='Close-up of the same unicorn princess on a glowing fantasy race track, speaking excitedly with facial expressions and natural lip synchronization, keep her likeness.',
         dialogue='أنا مستعدة! يلا نلعبو كاملين!'),
]


def directory(project_id: str) -> Path:
    try:
        uuid.UUID(project_id)
    except (ValueError, TypeError):
        raise HTTPException(404, 'Unknown project')
    folder = DATA / project_id
    if not (folder / 'project.json').is_file():
        raise HTTPException(404, 'Unknown project')
    return folder


def load_project(project_id: str) -> dict:
    return json.loads((directory(project_id) / 'project.json').read_text(encoding='utf-8'))


def save_project(folder: Path, project: dict) -> None:
    temp = folder / 'project.json.tmp'
    temp.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(folder / 'project.json')


def public_project(project: dict) -> dict:
    return {**project, 'has_video': (DATA / project['id'] / 'final.mp4').is_file()}


@app.get('/', response_class=HTMLResponse)
def index():
    return (BASE / 'static' / 'index.html').read_text(encoding='utf-8')


@app.get('/api/health')
def health():
    from studio import ComfyClient
    url = os.environ.get('COMFYUI_URL', 'http://127.0.0.1:8188')
    try:
        with ComfyClient(url) as comfy:
            result = comfy.health()
        devices = result.get('devices') or []
        return {'server': 'ok', 'comfyui': 'connected', 'devices': [d.get('name', '') for d in devices]}
    except Exception:
        return {'server': 'ok', 'comfyui': 'offline', 'devices': []}


@app.post('/api/projects', status_code=201)
def create_project():
    project_id = str(uuid.uuid4())
    folder = DATA / project_id
    (folder / 'images').mkdir(parents=True)
    (folder / 'audio').mkdir()
    project = {'id': project_id, 'name': 'Heroes – 30 seconds',
               'characters': {}, 'scenes': DEFAULT_SCENES, 'created_at': __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()}
    save_project(folder, project)
    return public_project(project)


@app.get('/api/projects/{project_id}')
def get_project(project_id: str):
    return public_project(load_project(project_id))


@app.put('/api/projects/{project_id}/storyboard')
def update_storyboard(project_id: str, body: Storyboard):
    with _lock:
        folder = directory(project_id)
        project = load_project(project_id)
        if any(job['status'] in ('queued', 'running') and job['project_id'] == project_id for job in _jobs.values()):
            raise HTTPException(409, 'Cannot edit while rendering')
        project['scenes'] = [scene.model_dump() for scene in body.scenes]
        save_project(folder, project)
        return public_project(project)


@app.post('/api/projects/{project_id}/characters/{role}/image')
async def upload_character(project_id: str, role: str, file: UploadFile = File(...)):
    if role not in ROLES:
        raise HTTPException(400, f'Role must be one of {ROLES}')
    data = await file.read(MAX_UPLOAD + 1)
    if not data or len(data) > MAX_UPLOAD:
        raise HTTPException(413, 'Image exceeds 20 MB')
    from io import BytesIO
    try:
        with Image.open(BytesIO(data)) as probe:
            probe.verify()
        with Image.open(BytesIO(data)) as image:
            if image.width * image.height > 30_000_000:
                raise HTTPException(413, 'Image has too many pixels')
            converted = image.convert('RGB')
    except (UnidentifiedImageError, OSError):
        raise HTTPException(415, 'Only valid images are supported')
    with _lock:
        folder = directory(project_id)
        filename = f'{role}-{uuid.uuid4().hex[:12]}.jpg'
        converted.save(folder / 'images' / filename, 'JPEG', quality=93)
        project = load_project(project_id)
        project['characters'][role] = filename
        save_project(folder, project)
    return {'ok': True, 'role': role, 'image_url': f'/api/projects/{project_id}/characters/{role}/image'}


@app.get('/api/projects/{project_id}/characters/{role}/image')
def view_character(project_id: str, role: str):
    project = load_project(project_id)
    filename = project['characters'].get(role)
    if not filename or role not in ROLES:
        raise HTTPException(404, 'No character image')
    return FileResponse(directory(project_id) / 'images' / filename, media_type='image/jpeg')


@app.post('/api/projects/{project_id}/audio')
async def upload_audio(project_id: str, file: UploadFile = File(...)):
    if Path(file.filename or '').suffix.lower() not in ('.mp3', '.wav', '.m4a', '.ogg'):
        raise HTTPException(415, 'Supported formats: MP3, WAV, M4A, OGG')
    data = await file.read(MAX_UPLOAD + 1)
    if not data or len(data) > MAX_UPLOAD:
        raise HTTPException(413, 'Audio exceeds 20 MB')
    with _lock:
        folder = directory(project_id)
        filename = f'audio-{uuid.uuid4().hex[:16]}' + Path(file.filename).suffix.lower()
        (folder / 'audio' / filename).write_bytes(data)
    return {'audio_file': filename}


def _worker(job_id: str, project_id: str):
    with _lock:
        _jobs[job_id].update(status='running', message='Connecting to ComfyUI')
    try:
        project = load_project(project_id)
        root = directory(project_id)

        def update(message, fraction):
            with _lock:
                _jobs[job_id].update(message=message, progress=round(100 * fraction, 1))

        render_project(project, root, update)
        with _lock:
            _jobs[job_id].update(status='done', progress=100, message='Video ready',
                                 video_url=f'/api/projects/{project_id}/video')
    except Exception as exc:
        with _lock:
            _jobs[job_id].update(status='failed', message=str(exc)[:2500])


@app.post('/api/projects/{project_id}/render', status_code=202)
def start_render(project_id: str):
    project = load_project(project_id)
    missing = sorted({s['character'] for s in project['scenes']} - project['characters'].keys())
    if missing:
        raise HTTPException(422, f'Missing character images: {", ".join(missing)}')
    for scene in project['scenes']:
        if scene.get('audio_file') and not (directory(project_id) / 'audio' / scene['audio_file']).is_file():
            raise HTTPException(422, 'Audio file is missing')
    with _lock:
        if any(j['status'] in ('running', 'queued') and j['project_id'] == project_id for j in _jobs.values()):
            raise HTTPException(409, 'Render is already running')
        job_id = str(uuid.uuid4())
        _jobs[job_id] = {'id': job_id, 'project_id': project_id, 'status': 'queued',
                         'progress': 0, 'message': 'Queued'}
        executor.submit(_worker, job_id, project_id)
    return _jobs[job_id]


@app.get('/api/jobs/{job_id}')
def get_job(job_id: str):
    with _lock:
        if job_id not in _jobs:
            raise HTTPException(404, 'Unknown job')
        return _jobs[job_id].copy()


@app.get('/api/projects/{project_id}/video')
def get_video(project_id: str):
    video = directory(project_id) / 'final.mp4'
    if not video.is_file():
        raise HTTPException(404, 'Video is not ready')
    return FileResponse(video, media_type='video/mp4', filename='RealMotion-Heroes-30s.mp4')
