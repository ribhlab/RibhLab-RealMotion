"""RibhLab RealMotion: local-first storyboard and ComfyUI render orchestration."""
from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
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
_job_cancel: dict[str, threading.Event] = {}
_job_logs: dict[str, list[str]] = {}


def _job_log(job_id: str, message: str, *, progress: float | None = None,
             phase: str | None = None) -> None:
    """Timestamped diagnostics without passwords or private source prompts."""
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return
        previous = job.get('message')
        if progress is not None:
            job['progress'] = round(max(0, min(100, float(progress))), 1)
        if phase is not None:
            job['phase'] = phase
        job['message'] = message
        job['updated_at'] = datetime.now(timezone.utc).isoformat()
        if previous == message and progress is None:
            return
        stamp = datetime.now(timezone.utc).strftime('%H:%M:%S UTC')
        line = f"[{stamp}] {message}"
        if progress is not None:
            line += f" | stage={job.get('phase', '?')} | overall={job['progress']:.1f}%"
        items = _job_logs.setdefault(job_id, [])
        items.append(line)
        if len(items) > 400:
            del items[:-400]
        try:
            folder = DATA / 'job_logs'
            folder.mkdir(exist_ok=True, parents=True)
            with (folder / f'{job_id}.log').open('a', encoding='utf-8') as fp:
                fp.write(line + '\n')
        except OSError:
            pass


def _job_update(job_id: str, message: str, fraction: float) -> None:
    if _job_cancel.get(job_id, threading.Event()).is_set():
        from studio import GenerationCancelled
        raise GenerationCancelled('User cancelled the job')
    low = message.lower()
    phase = ('macbook' if 'macbook' in low else
             'voice' if 'voice' in low or 'speech' in low else
             'export' if 'mp4' in low or 'encod' in low else
             'gpu' if any(w in low for w in ('comfy', 'motion', 'sampl', 'decode', 'gpu', 'queue')) else
             'preparing')
    _job_log(job_id, message, progress=100 * fraction, phase=phase)


def _job_finished(job_id: str, status: str, message: str, **fields) -> None:
    with _lock:
        job = _jobs[job_id]
        if _job_cancel.get(job_id, threading.Event()).is_set():
            status = 'cancelled'
            message = 'Cancelled by user'
        job.update(status=status, **(fields if status == 'done' else {}))
    _job_log(job_id, message, progress=100 if status == 'done' else None, phase=status)


@app.get('/api/jobs/{job_id}/logs')
def get_job_logs(job_id: uuid.UUID):
    from fastapi.responses import PlainTextResponse
    key = str(job_id)
    with _lock:
        if key not in _jobs:
            raise HTTPException(404, 'Unknown job')
        lines = '\n'.join(_job_logs.get(key, []))
    return PlainTextResponse(lines + ('\n' if lines else ''))


@app.post('/api/jobs/{job_id}/cancel')
def cancel_job(job_id: uuid.UUID):
    key = str(job_id)
    with _lock:
        job = _jobs.get(key)
        if job is None:
            raise HTTPException(404, 'Unknown job')
        if job['status'] in ('cancelled', 'done', 'failed'):
            return job.copy()
        if job.get('mode') not in ('studio', 'longform'):
            raise HTTPException(409, 'Cancel is currently supported for Studio jobs')
        event = _job_cancel.setdefault(key, threading.Event())
        event.set()
        job['status'] = 'cancelling'
    _job_log(key, 'Cancel requested; stopping at the next safe point', phase='cancelling')
    return _jobs[key].copy()


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
    import httpx

    url = os.environ.get('COMFYUI_URL', 'http://127.0.0.1:8188')
    gpu = 'offline'
    devices = []
    try:
        with ComfyClient(url) as comfy:
            result = comfy.health()
        gpu = 'connected'
        devices = [
            {'name': d.get('name') or d.get('device_name') or 'GPU',
             'vram_gb': round((d.get('vram_total') or 0) / (1024**3), 1)}
            for d in result.get('devices') or []
        ]
    except (Exception):
        pass
    worker_url = os.environ.get('REALMOTION_WORKER_URL', '').strip().rstrip('/')
    token = os.environ.get('REALMOTION_WORKER_TOKEN', '').strip()
    worker = 'not_configured'
    if worker_url:
        if len(token) < 32:
            worker = 'token_missing'
        else:
            try:
                r = httpx.get(worker_url + '/health',
                              headers={'X-RealMotion-Token': token},
                              timeout=3, follow_redirects=False)
                worker = ('connected' if r.status_code == 200
                          else 'authentication_failed' if r.status_code in (401, 403)
                          else f'http_{r.status_code}')
            except httpx.HTTPError:
                worker = 'unreachable'
    return {'server': 'ok', 'mode': 'local', 'comfyui': gpu,
            'devices': devices, 'macbook': worker}


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
        if any(job['status'] in ('queued', 'running') and job.get('project_id') == project_id for job in _jobs.values()):
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


def _worker(job_id: str, project_id: str, preview: bool = False):
    with _lock:
        _jobs[job_id].update(status='running', message='Connecting to ComfyUI')
    try:
        project = load_project(project_id)
        root = directory(project_id)

        def update(message, fraction):
            with _lock:
                _jobs[job_id].update(message=message, progress=round(100 * fraction, 1))

        render_project(project, root, update, preview=preview)
        with _lock:
            _jobs[job_id].update(status='done', progress=100, message='Video ready',
                                 video_url=(f'/api/projects/{project_id}/preview.mp4' if preview else f'/api/projects/{project_id}/video'))
    except Exception as exc:
        with _lock:
            _jobs[job_id].update(status='failed', message=str(exc)[:2500])


def _queue_video_render(project_id: str, *, preview: bool = False):
    project = load_project(project_id)
    if preview:
        candidate = next((s for s in project['scenes']
                          if s['mode'] == 'talk' and s['character'] in project['characters']), None)
        if candidate is None:
            raise HTTPException(422, "Upload the driver's portrait to preview video+audio")
        scenes = [candidate]
    else:
        scenes = project['scenes']
        missing = sorted({s['character'] for s in scenes} - project['characters'].keys())
        if missing:
            raise HTTPException(422, f'Missing character images: {", ".join(missing)}')
    for scene in scenes:
        if scene.get('audio_file') and not (directory(project_id) / 'audio' / scene['audio_file']).is_file():
            raise HTTPException(422, 'Audio file is missing')
    with _lock:
        if any(j['status'] in ('running', 'queued') and j.get('project_id') == project_id for j in _jobs.values()):
            raise HTTPException(409, 'Render is already running')
        job_id = str(uuid.uuid4())
        _jobs[job_id] = {'id': job_id, 'project_id': project_id, 'status': 'queued',
                         'progress': 0, 'message': 'Queued',
                         'mode': 'preview' if preview else 'full'}
        executor.submit(_worker, job_id, project_id, preview)
    return _jobs[job_id]


@app.post('/api/projects/{project_id}/render', status_code=202)
def start_render(project_id: str):
    return _queue_video_render(project_id)


@app.post('/api/projects/{project_id}/preview', status_code=202)
def preview_with_audio(project_id: str):
    return _queue_video_render(project_id, preview=True)


@app.get('/api/jobs/{job_id}')
def get_job(job_id: str):
    with _lock:
        if job_id not in _jobs:
            raise HTTPException(404, 'Unknown job')
        return _jobs[job_id].copy()


@app.get('/api/projects/{project_id}/preview.mp4')
def preview_video(project_id: str):
    video = directory(project_id) / 'preview.mp4'
    if not video.is_file():
        raise HTTPException(404, 'Preview is not ready')
    return FileResponse(video, media_type='video/mp4',
                        filename='RealMotion-Preview-Voice-5s.mp4')


@app.get('/api/projects/{project_id}/video')
def get_video(project_id: str):
    video = directory(project_id) / 'final.mp4'
    if not video.is_file():
        raise HTTPException(404, 'Video is not ready')
    return FileResponse(video, media_type='video/mp4', filename='RealMotion-Heroes-30s.mp4')


# ---------------------------------------------------------------------------
# Simple creative studio API: a reference image/video + a prompt at the bottom.
# Video upload is intentionally treated as a FIRST-FRAME reference; this Wan
# 5B GGUF setup is not a video-to-video editing model.
# ---------------------------------------------------------------------------
STUDIO_ASSET_LIMIT = 100 * 1024 * 1024
STUDIO_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
STUDIO_VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".m4v"}


class StudioRequest(BaseModel):
    asset_id: uuid.UUID
    asset_ids: list[uuid.UUID] = Field(default_factory=list, max_length=40)
    prompt: str = Field(min_length=8, max_length=12000)
    seconds: int = Field(default=5, ge=1, le=600)
    with_voice: bool = True
    render_mode: Literal["wan_ai", "ltx_2b", "stable_food"] = "wan_ai"
    steam_x: float = Field(default=.50, ge=0., le=1.)
    steam_y: float = Field(default=.65, ge=0., le=1.)
    steam_strength: float = Field(default=.85, ge=.1, le=2.)

    @field_validator('seconds')
    @classmethod
    def studio_duration_supported(cls, value: int) -> int:
        if value not in (*range(1, 11), 600):
            raise ValueError('Choose 1–10 seconds or the 10-minute film mode')
        return value


def _studio_folder(asset_id: uuid.UUID) -> Path:
    return DATA / "studio_assets" / str(asset_id)


def _save_studio_result(job_id: str, reference_id: uuid.UUID,
                        render_mode: str, seconds: int) -> None:
    """Persist minimal job metadata so successful videos survive app restarts."""
    result_dir = DATA / 'studio_results' / job_id
    video = result_dir / 'result.mp4'
    if not video.is_file():
        raise RuntimeError('Cannot record a completed Studio job without result.mp4')
    metadata = {
        'id': job_id,
        'asset_id': str(reference_id),
        'render_mode': render_mode,
        'seconds': seconds,
        'saved_at': datetime.now(timezone.utc).isoformat(),
    }
    try:
        (result_dir / 'result_meta.json').write_text(
            json.dumps(metadata, ensure_ascii=False), encoding='utf-8')
    except OSError as exc:
        _job_log(job_id, f'Warning: could not save history metadata: {exc}')


@app.get('/api/studio/history')
def studio_history():
    """Return recently produced local MP4 files, including previous launches."""
    folder = DATA / 'studio_results'
    if not folder.is_dir():
        return {'items': []}
    found = []
    for video in folder.glob('*/result.mp4'):
        if not video.is_file() or video.stat().st_size < 1024:
            continue
        try:
            job_id = str(uuid.UUID(video.parent.name))
        except ValueError:
            continue
        meta_file = video.parent / 'result_meta.json'
        meta = {}
        if meta_file.is_file():
            try:
                meta = json.loads(meta_file.read_text(encoding='utf-8'))
            except (OSError, ValueError, TypeError):
                pass
        item = {
            'id': job_id,
            'video_url': f'/api/studio/jobs/{job_id}/video',
            'render_mode': (meta.get('render_mode') if meta.get('render_mode')
                            in ('wan_ai', 'stable_food', 'longform') else 'unknown'),
            'seconds': meta.get('seconds'),
            'created_at': meta.get('saved_at'),
            'size_mb': round(video.stat().st_size / (1024 * 1024), 2),
            '_sort': video.stat().st_mtime,
        }
        try:
            reference_id = uuid.UUID(str(meta.get('asset_id', '')))
            if (_studio_folder(reference_id) / 'reference.jpg').is_file():
                item['preview_url'] = f'/api/studio/assets/{reference_id}/preview'
        except ValueError:
            pass
        found.append(item)
    found.sort(key=lambda item: item.pop('_sort'), reverse=True)
    return {'items': found[:16]}


@app.post('/api/studio/assets', status_code=201)
async def studio_upload(file: UploadFile = File(...)):
    import subprocess
    name = Path(file.filename or "").name
    extension = Path(name).suffix.lower()
    if extension not in STUDIO_IMAGE_EXTENSIONS | STUDIO_VIDEO_EXTENSIONS:
        raise HTTPException(415, 'Only JPG, PNG, WEBP, MP4, WEBM, MOV, M4V are supported')
    data = await file.read(STUDIO_ASSET_LIMIT + 1)
    if not data or len(data) > STUDIO_ASSET_LIMIT:
        raise HTTPException(413, "File is empty or over 100 MB")
    asset_id = uuid.uuid4()
    folder = _studio_folder(asset_id)
    folder.mkdir(parents=True, exist_ok=False)
    reference = folder / 'reference.jpg'
    kind = 'image' if extension in STUDIO_IMAGE_EXTENSIONS else 'video'
    try:
        if kind == 'image':
            from io import BytesIO
            with Image.open(BytesIO(data)) as img:
                img.verify()
            with Image.open(BytesIO(data)) as img:
                if img.width * img.height > 30_000_000:
                    raise HTTPException(413, "Image exceeds 30 megapixels")
                img.convert('RGB').save(reference, 'JPEG', quality=94)
        else:
            source = folder / ('source' + extension)
            source.write_bytes(data)
            # Extract only the first frame: a valid I2V reference, NOT video editing.
            completed = subprocess.run(
                ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                 '-i', str(source), '-frames:v', '1', str(reference)],
                capture_output=True, timeout=40, check=False)
            if completed.returncode != 0 or not reference.is_file():
                raise HTTPException(415, 'Cannot read video frames from this file')
            with Image.open(reference) as img:
                if img.width * img.height > 30_000_000:
                    raise HTTPException(413, "Video frame is too large")
        (folder / 'meta.json').write_text(
            json.dumps({'name': name, 'kind': kind}, ensure_ascii=False),
            encoding='utf-8')
    except HTTPException:
        import shutil
        shutil.rmtree(folder, ignore_errors=True)
        raise
    except (OSError, UnidentifiedImageError, subprocess.TimeoutExpired) as exc:
        import shutil
        shutil.rmtree(folder, ignore_errors=True)
        raise HTTPException(415, f'Cannot read source media: {str(exc)[:180]}') from exc

    return {'id': str(asset_id), 'name': name, 'kind': kind,
            'reference_mode': 'first_frame' if kind == 'video' else 'image',
            'preview_url': f'/api/studio/assets/{asset_id}/preview'}


@app.get('/api/studio/assets/{asset_id}/preview')
def studio_reference_preview(asset_id: uuid.UUID):
    reference = _studio_folder(asset_id) / 'reference.jpg'
    if not reference.is_file():
        raise HTTPException(404, 'Reference was not found')
    return FileResponse(reference, media_type='image/jpeg')


def _studio_worker(job_id: str, asset_id: uuid.UUID,
                   prompt: str, seconds: int, narration: str):
    import re
    from studio import render_single_studio_video, render_source_preserving_food
    folder = _studio_folder(asset_id)
    if _job_cancel.get(job_id, threading.Event()).is_set():
        _job_finished(job_id, 'cancelled', 'Cancelled before starting')
        return
    with _lock:
        _jobs[job_id]['status'] = 'running'
    _job_log(job_id, 'Preparing Studio request', progress=1, phase='preparing')
    try:
        out_dir = DATA / 'studio_results' / job_id
        out_dir.mkdir(parents=True, exist_ok=True)

        def update(message, fraction):
            _job_update(job_id, message, fraction)

        # Accept optional spoken phrase in the SAME prompt input.
        # Example: A person waves. الكلام: السلام عليكم
        speech = re.search(r'(?:الكلام|الحوار|يقول|تقول)\s*[:：]\s*(.+)', prompt,
                           flags=re.IGNORECASE | re.DOTALL)
        video_prompt = prompt[:speech.start()].strip() if speech and prompt[:speech.start()].strip() else prompt
        voiced_text = speech.group(1).strip() if speech and narration else ''
        with _lock:
            render_mode = _jobs[job_id].get('render_mode', 'wan_ai')
        if render_mode == 'stable_food':
            _job_log(job_id, 'Source-preserving 2.5D food mode; no diffusion or scene regeneration',
                     progress=2, phase='preparing')
            with _lock:
                config = {k: _jobs[job_id].get(k) for k in
                          ('steam_x', 'steam_y', 'steam_strength')}
            config = {k: v for k, v in config.items() if v is not None}
            render_source_preserving_food(
                folder / 'reference.jpg', seconds,
                out_dir / 'result.mp4', update, narration=voiced_text,
                cancel_event=_job_cancel.setdefault(job_id, threading.Event()),
                **config)
        else:
            if render_mode == "ltx_2b":
                _job_log(job_id, 'Free local LTX 2B FP8 on NVIDIA; native ComfyUI graph',
                         progress=2, phase='preparing')
            render_single_studio_video(
                folder / 'reference.jpg', video_prompt, seconds,
                out_dir / 'result.mp4', update, narration=voiced_text,
                cancel_event=_job_cancel.setdefault(job_id, threading.Event()),
                engine=render_mode)
        _save_studio_result(job_id, asset_id, render_mode, seconds)
        _job_finished(job_id, 'done', 'Your MP4 is ready',
                      video_url=f'/api/studio/jobs/{job_id}/video')
    except Exception as exc:
        from studio import GenerationCancelled
        if isinstance(exc, GenerationCancelled):
            _job_finished(job_id, 'cancelled', 'Cancelled by user')
        else:
            _job_finished(job_id, 'failed', f'{type(exc).__name__}: {str(exc)[:1450]}')


def _studio_long_worker(job_id: str, asset_ids: list[uuid.UUID],
                        prompt: str, narration_enabled: bool):
    import re
    from long_form import render_ten_minute_film

    if _job_cancel.get(job_id, threading.Event()).is_set():
        _job_finished(job_id, 'cancelled', 'Cancelled before starting')
        return
    with _lock:
        _jobs[job_id]['status'] = 'running'
    _job_log(job_id, 'Preparing ten-minute AI film', progress=1, phase='preparing')
    try:
        refs = [_studio_folder(asset_id) / 'reference.jpg'
                for asset_id in asset_ids]
        speech = re.search(r'(?:الكلام|الحوار|التعليق الصوتي)\s*[:：]\s*(.+)',
                           prompt, flags=re.IGNORECASE | re.DOTALL)
        visual = prompt[:speech.start()].strip() if speech else prompt
        narration = speech.group(1).strip() if speech and narration_enabled else ''
        if len(visual) < 8:
            raise ValueError('Please describe the visual style and scenes before the narration')
        result_dir = DATA / 'studio_results' / job_id

        def update(message, fraction):
            _job_update(job_id, message, fraction)

        render_ten_minute_film(
            refs, visual, narration, result_dir / 'result.mp4',
            DATA, update, cancel_event=_job_cancel.setdefault(job_id, threading.Event()))
        _save_studio_result(job_id, asset_ids[0], 'longform', 600)
        _job_finished(job_id, 'done', 'Ten-minute MP4 created',
                      video_url=f'/api/studio/jobs/{job_id}/video')
    except Exception as exc:
        from studio import GenerationCancelled
        if isinstance(exc, GenerationCancelled):
            _job_finished(job_id, 'cancelled', 'Cancelled by user')
        else:
            _job_finished(job_id, 'failed', f'{type(exc).__name__}: {str(exc)[:1450]}')


@app.post('/api/studio/generate', status_code=202)
def studio_generate(body: StudioRequest):
    asset = _studio_folder(body.asset_id)
    if not (asset / 'reference.jpg').is_file():
        raise HTTPException(404, "Upload a photo or video first")
    long_mode = body.seconds == 600
    if long_mode and body.render_mode != 'wan_ai':
        raise HTTPException(422, '10-minute film is supported for Wan only; choose a short clip for LTX or Stable Food')
    ids = list(dict.fromkeys(body.asset_ids or [body.asset_id]))
    if long_mode:
        if body.asset_id not in ids:
            ids.insert(0, body.asset_id)
        if len(ids) > 40:
            raise HTTPException(422, 'Use no more than 40 reference files')
        if not all((_studio_folder(key) / 'reference.jpg').is_file() for key in ids):
            raise HTTPException(422, 'A reference image or video was not found')
    with _lock:
        if any(j['status'] in ('queued', 'running', 'cancelling') for j in _jobs.values()):
            raise HTTPException(409, 'Another generation is still running')
        job_id = str(uuid.uuid4())
        _jobs[job_id] = {
            'id': job_id, 'status': 'queued', 'progress': 0, 'phase': 'queued',
            'message': ('120 real AI scenes queued — checkpointed' if long_mode
                        else ('Source-preserving food render queued' if body.render_mode == 'stable_food'
                      else 'Free LTX 2B GPU render queued' if body.render_mode == 'ltx_2b'
                      else 'Queued on local GPU')),
            'mode': 'longform' if long_mode else 'studio',
            'render_mode': body.render_mode,
            'steam_x': body.steam_x,
            'steam_y': body.steam_y,
            'steam_strength': body.steam_strength,
            'created_at': datetime.now(timezone.utc).isoformat()}
        _job_cancel[job_id] = threading.Event()
        _job_logs[job_id] = []
        _job_log(job_id,
                 ('Source-preserving food mode: stable image + transparent steam'
                  if body.render_mode == 'stable_food'
                  else 'LTX 2B FP8: free NVIDIA image-to-video, no cloud' if body.render_mode == 'ltx_2b'
                  else 'Wan AI image-to-video: NVIDIA + optional MacBook processing'),
                 progress=0, phase='queued')
        if long_mode:
            executor.submit(_studio_long_worker, job_id, ids, body.prompt.strip(),
                            body.with_voice)
        else:
            executor.submit(_studio_worker, job_id, body.asset_id, body.prompt.strip(),
                            body.seconds, body.prompt.strip() if body.with_voice else '')
        return _jobs[job_id].copy()


@app.get('/api/studio/jobs/{job_id}/video')
def studio_generated_video(job_id: uuid.UUID):
    video = DATA / 'studio_results' / str(job_id) / 'result.mp4'
    if not video.is_file():
        raise HTTPException(404, "Generated video not ready")
    return FileResponse(video, media_type='video/mp4',
                        filename='RibhLab-RealMotion.mp4')
