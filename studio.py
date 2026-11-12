"""RealMotion's ComfyUI graph builder and deterministic video assembler.

No fabricated clip fallback: rendering requires a live local ComfyUI with Wan models.
Images and audio are stored locally and are never committed to the Git repository.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

from stable_motion import choose_output_size, choose_wan_size

FPS = 16
NEGATIVE = (
    "poor quality, unnatural geometry, warped objects, melting textures, "
    "distorted anatomy, deformed hands, extra fingers, face morphing, "
    "identity drift, flicker, temporal inconsistencies, duplicate objects, "
    "unnatural eyes, captions, text artifacts, watermark"
)


def node(kind: str, **inputs: Any) -> dict[str, Any]:
    return {"class_type": kind, "inputs": inputs}


def image_to_video_graph(image_name: str, prompt: str, seconds: int, filename_prefix: str,
                         *, width: int = 512, height: int = 768, seed: int | None = None) -> dict[str, Any]:
    """Native ComfyUI Wan2.2 TI2V 5B workflow in API format (not GUI JSON).

    The official ComfyUI template uses these exact core node classes.
    Model filenames are configurable with environment variables.
    """
    if seconds < 1 or seconds > 15:
        raise ValueError("Each AI shot must be between 1 and 15 seconds")
    seed = seed if seed is not None else int.from_bytes(os.urandom(4), 'big')
    length = seconds * FPS + 1
    filename = os.getenv("WAN_I2V_MODEL", "Wan2.2-TI2V-5B-Q2_K.gguf")
    loader = (node("UnetLoaderGGUF", unet_name=filename) if filename.lower().endswith(".gguf")
              else node("UNETLoader", unet_name=filename, weight_dtype="default"))
    return {
        "1": loader,
        "2": node("CLIPLoader", clip_name=os.getenv("WAN_TEXT_ENCODER", "umt5_xxl_fp8_e4m3fn_scaled.safetensors"), type="wan", device="default"),
        "3": node("VAELoader", vae_name=os.getenv("WAN_I2V_VAE", "wan2.2_vae.safetensors")),
        "4": node("LoadImage", image=image_name),
        "5": node("CLIPTextEncode", clip=["2", 0], text=prompt),
        "6": node("CLIPTextEncode", clip=["2", 0], text=NEGATIVE),
        "7": node("ModelSamplingSD3", model=["1", 0], shift=8),
        "8": node("Wan22ImageToVideoLatent", vae=["3", 0], start_image=["4", 0],
                  width=width, height=height, length=length, batch_size=1),
        "9": node("KSampler", model=["7", 0], positive=["5", 0], negative=["6", 0],
                  latent_image=["8", 0], seed=seed, steps=20, cfg=5, sampler_name="uni_pc",
                  scheduler="simple", denoise=1.0),
        "10": node("VAEDecode", samples=["9", 0], vae=["3", 0]),
        "11": node("CreateVideo", images=["10", 0], fps=FPS),
        "12": node("SaveVideo", video=["11", 0], filename_prefix=filename_prefix,
                   format="auto", **{"format.codec": "auto"}),
    }


def speech_to_video_graph(image_name: str, audio_name: str, prompt: str, seconds: int,
                          filename_prefix: str, *, width: int = 512, height: int = 768,
                          seed: int | None = None) -> dict[str, Any]:
    """Wan2.2-S2V 14B audio-driven video. Requires optional S2V model files.

    The basic 20-step graph uses the official WanSoundImageToVideo / AudioEncoder
    nodes (not a lip-sync approximation). For production, pick appropriate
    dimensions and speech-aware audio, and verify the model's allowed frame count.
    """
    if seconds < 1 or seconds > 15:
        raise ValueError("Each speech shot must be between 1 and 15 seconds")
    seed = seed if seed is not None else int.from_bytes(os.urandom(4), 'big')
    length = seconds * FPS + 1
    return {
        "1": node("UNETLoader", unet_name=os.getenv("WAN_S2V_MODEL", "wan2.2_s2v_14B_fp8_scaled.safetensors"), weight_dtype="default"),
        "2": node("CLIPLoader", clip_name=os.getenv("WAN_TEXT_ENCODER", "umt5_xxl_fp8_e4m3fn_scaled.safetensors"), type="wan", device="default"),
        "3": node("VAELoader", vae_name=os.getenv("WAN_S2V_VAE", "wan_2.1_vae.safetensors")),
        "4": node("AudioEncoderLoader", audio_encoder_name=os.getenv("WAN_AUDIO_ENCODER", "wav2vec2_large_english_fp16.safetensors")),
        "5": node("LoadAudio", audio=audio_name),
        "6": node("LoadImage", image=image_name),
        "7": node("AudioEncoderEncode", audio_encoder=["4", 0], audio=["5", 0]),
        "8": node("CLIPTextEncode", clip=["2", 0], text=prompt),
        "9": node("CLIPTextEncode", clip=["2", 0], text=NEGATIVE),
        "10": node("ModelSamplingSD3", model=["1", 0], shift=8),
        "11": node("WanSoundImageToVideo", positive=["8", 0], negative=["9", 0],
                   vae=["3", 0], audio_encoder_output=["7", 0], ref_image=["6", 0],
                   width=width, height=height, length=length, batch_size=1),
        "12": node("KSampler", model=["10", 0], positive=["11", 0], negative=["11", 1],
                   latent_image=["11", 2], seed=seed, steps=20, cfg=6,
                   sampler_name="uni_pc", scheduler="simple", denoise=1.0),
        "13": node("VAEDecode", samples=["12", 0], vae=["3", 0]),
        "14": node("CreateVideo", images=["13", 0], fps=FPS, audio=["5", 0]),
        "15": node("SaveVideo", video=["14", 0], filename_prefix=filename_prefix,
                   format="auto", **{"format.codec": "auto"}),
    }


class ComfyError(RuntimeError):
    pass


class GenerationCancelled(ComfyError):
    """User explicitly cancelled GPU processing or postproduction."""
    pass


class ComfyClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8188") -> None:
        self.base = base_url.rstrip('/')
        self.client_id = "ribhlab-" + uuid.uuid4().hex
        self.client = httpx.Client(base_url=self.base, timeout=httpx.Timeout(45.0, connect=10.0), follow_redirects=False)

    def __enter__(self) -> "ComfyClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.client.close()

    def health(self) -> dict[str, Any]:
        response = self.client.get("/system_stats")
        response.raise_for_status()
        return response.json()

    def upload(self, path: Path) -> str:
        # ComfyUI accepts audio and image inputs via its /upload/image endpoint.
        with path.open('rb') as fp:
            response = self.client.post('/upload/image', files={"image": (path.name, fp)},
                                        data={"type": "input", "overwrite": "false"})
        response.raise_for_status()
        data = response.json()
        return f"{data.get('subfolder', '')}/{data['name']}".lstrip('/')

    def submit(self, graph: dict[str, Any]) -> str:
        response = self.client.post('/prompt', json={"prompt": graph, "client_id": self.client_id})
        if response.status_code >= 400:
            raise ComfyError(f"ComfyUI rejected the graph ({response.status_code}): {response.text[:1800]}")
        data = response.json()
        if data.get('node_errors'):
            raise ComfyError(f"ComfyUI graph errors: {json.dumps(data['node_errors'])[:1700]}")
        return str(data['prompt_id'])

    def cancel(self, prompt_id: str) -> None:
        """Delete our queued prompt; interrupt only if our prompt is running."""
        try:
            response = self.client.get('/queue', timeout=5)
            response.raise_for_status()
            queue = response.json()
            pending = any(len(item) > 1 and str(item[1]) == prompt_id
                          for item in queue.get('queue_pending', []))
            running = any(len(item) > 1 and str(item[1]) == prompt_id
                          for item in queue.get('queue_running', []))
            if pending:
                self.client.post('/queue', json={'delete': [prompt_id]}, timeout=5).raise_for_status()
            if running:
                self.client.post('/interrupt', timeout=5).raise_for_status()
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise ComfyError(f'Could not send cancellation to ComfyUI: {exc}') from exc

    def wait_and_download(self, prompt_id: str, destination: Path, *,
                          timeout: int = 3600, on_progress: Any = None,
                          cancel_event: threading.Event | None = None) -> None:
        """Live GPU sampler steps via ComfyUI websocket; HTTP history is authoritative.

        A missing websocket does not fabricate step counts: fallback reports
        queue/running state and checks for a real history output.
        """
        deadline = time.monotonic() + timeout
        stop_ws = threading.Event()
        ws_error: list[str] = []

        def listen() -> None:
            try:
                from websockets.sync.client import connect
                ws_url = self.base.replace('http://', 'ws://', 1).replace(
                    'https://', 'wss://', 1)
                with connect(ws_url + '/ws?clientId=' + self.client_id,
                             open_timeout=5, close_timeout=2) as websocket:
                    while not stop_ws.is_set():
                        try:
                            message = websocket.recv(timeout=1)
                        except TimeoutError:
                            continue
                        if not isinstance(message, str):
                            continue
                        try:
                            event = json.loads(message)
                        except ValueError:
                            continue
                        kind = event.get('type')
                        data = event.get('data') or {}
                        if str(data.get('prompt_id', '')) != prompt_id:
                            continue
                        if kind == 'progress' and on_progress:
                            value, maximum = int(data.get('value') or 0), int(data.get('max') or 0)
                            if maximum > 0:
                                on_progress('sampling', value, maximum)
                        elif kind == 'executing' and on_progress and data.get('node') is not None:
                            on_progress('node:' + str(data['node']), 0, 0)
            except Exception as exc:
                ws_error.append(type(exc).__name__)

        thread = threading.Thread(target=listen, daemon=True, name='realmotion-gpu-progress')
        thread.start()
        last_queue = ''
        last_queue_check = 0.0
        try:
            while time.monotonic() < deadline:
                if cancel_event is not None and cancel_event.is_set():
                    self.cancel(prompt_id)
                    raise GenerationCancelled('GPU generation cancelled by user')
                response = self.client.get(f'/history/{prompt_id}', timeout=15)
                response.raise_for_status()
                history = response.json().get(prompt_id)
                if history:
                    status = history.get('status', {})
                    if status.get('status_str') == 'error':
                        raise ComfyError(f"ComfyUI generation failed: {str(status.get('messages'))[:1800]}")
                    for output in history.get('outputs', {}).values():
                        for key in ('videos', 'gifs', 'images'):
                            for item in output.get(key, []):
                                name = item.get('filename', '')
                                if not name.lower().endswith(('.mp4', '.webm', '.mov', '.mkv', '.gif')):
                                    continue
                                if on_progress:
                                    on_progress('download', 1, 1)
                                file_resp = self.client.get('/view', params={
                                    'filename': name, 'type': item.get('type', 'output'),
                                    'subfolder': item.get('subfolder', '')
                                }, timeout=300)
                                file_resp.raise_for_status()
                                if cancel_event is not None and cancel_event.is_set():
                                    raise GenerationCancelled('Cancelled before downloading final AI video')
                                destination.write_bytes(file_resp.content)
                                return
                    if status.get('completed') or status.get('status_str') == 'success':
                        raise ComfyError('ComfyUI completed but SaveVideo returned no downloadable MP4')
                now = time.monotonic()
                if now - last_queue_check >= 8 and on_progress:
                    last_queue_check = now
                    try:
                        snapshot = self.client.get('/queue', timeout=8).json()
                        pending = any(len(item) > 1 and str(item[1]) == prompt_id
                                      for item in snapshot.get('queue_pending', []))
                        running = any(len(item) > 1 and str(item[1]) == prompt_id
                                      for item in snapshot.get('queue_running', []))
                        label = 'queued' if pending else ('running' if running else '')
                        if label and label != last_queue:
                            last_queue = label
                            on_progress(label, 0, 0)
                    except (httpx.HTTPError, ValueError, TypeError):
                        pass
                # Responsive cancellation without a busy loop.
                if cancel_event is not None:
                    cancel_event.wait(1.0)
                else:
                    time.sleep(1.0)
            raise ComfyError(f'AI generation timed out after {timeout}s; prompt id {prompt_id}. Review ComfyUI console.')
        finally:
            stop_ws.set()
            thread.join(timeout=2)


def normalize_clip(source: Path, target: Path, seconds: int, resolution: str = '720:1280') -> None:
    """Normalize timing, fps, dimensions and audio before deterministic concat."""
    width, height = resolution.split(':')
    args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-filter_complex", f"[0:v]fps=24,tpad=stop_mode=clone:stop_duration={seconds},scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p[v]",
            "-map", "[v]", "-map", "0:a?", "-map", "1:a", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
            "-c:a", "aac", "-ar", "44100", "-ac", "2", "-t", str(seconds), "-shortest", "-movflags", "+faststart", str(target)]
    # Replace the audio mapping with a single AAC track (use real audio if present).
    probe = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'a',
                            '-show_entries', 'stream=index', '-of', 'csv=p=0', str(source)],
                           capture_output=True, text=True, timeout=20, check=True)
    if probe.stdout.strip():
        args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
                "-vf", f"fps=24,tpad=stop_mode=clone:stop_duration={seconds},scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-c:a", "aac",
                "-ar", "44100", "-ac", "2", "-t", str(seconds),
                "-af", "apad", "-movflags", "+faststart", str(target)]
    else:
        args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
                "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                "-vf", f"fps=24,tpad=stop_mode=clone:stop_duration={seconds},scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p",
                "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "veryfast",
                "-crf", "22", "-c:a", "aac", "-t", str(seconds),
                "-movflags", "+faststart", str(target)]
    subprocess.run(args, check=True, capture_output=True, text=True, timeout=180)


def add_speech_to_clip(video: Path, speech: Path, output: Path, seconds: int) -> None:
    """Mux offline speech into a real AI video with one AAC audio track.

    This adds a voice soundtrack; it does NOT perform lip synchronization.
    """
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-i", str(video), "-i", str(speech),
         "-map", "0:v:0", "-map", "1:a:0",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
         "-ar", "44100", "-ac", "2",
         "-af", "apad", "-t", str(seconds), "-movflags", "+faststart",
         str(output)],
        check=True, capture_output=True, text=True, timeout=180
    )


def concatenate_clips(clips: list[Path], target: Path, workdir: Path) -> None:
    if not clips:
        raise ValueError('No clips to concatenate')
    manifest = workdir / 'concat.txt'
    manifest.write_text(''.join(f"file '{p.as_posix()}'\n" for p in clips), encoding='utf-8')
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
                    "-i", str(manifest), "-c", "copy", "-movflags", "+faststart", str(target)],
                   check=True, capture_output=True, text=True, timeout=180)


def _local_piper_voice(text: str, target: Path) -> bool:
    """Generate speech entirely offline when a Piper voice is installed."""
    import sys
    voice = Path(os.getenv("PIPER_MODEL_PATH", str(Path(__file__).resolve().parent / "models" / "ar_JO-kareem-medium.onnx")))
    cli = shutil.which("piper")
    if not cli and sys.platform == "win32":
        local = Path(sys.executable).parent / "piper.exe"
        if local.is_file():
            cli = str(local)
    if not voice.is_file() or not cli:
        return False
    config = Path(str(voice) + ".json")
    if not config.is_file():
        raise ComfyError(f"Missing Piper voice config: {config}")
    try:
        subprocess.run([cli, "--model", str(voice), "--output_file", str(target)],
                       input=text, capture_output=True, text=True, encoding="utf-8",
                       check=True, timeout=120)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ComfyError(f"Offline Piper synthesis failed: {str(exc)[:350]}") from exc
    if not target.is_file() or target.stat().st_size < 200:
        raise ComfyError("Piper did not create an audio file")
    return True


def _windows_sapi_voice(text: str, target: Path) -> bool:
    """Fallback to the installed Windows SAPI voices, with no cloud requests.

    Quality and Arabic-language support depend on voices installed in Windows.
    """
    import base64
    import sys
    if sys.platform != "win32":
        return False
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$ar = @($s.GetInstalledVoices() | Where-Object { "
        "$_.VoiceInfo.Culture.Name -like 'ar-*' }); "
        "if ($ar.Count -gt 0) { $s.SelectVoice($ar[0].VoiceInfo.Name) }; "
        "$s.SetOutputToWaveFile('" + str(target).replace("'", "''") + "'); "
        "$s.Speak([System.IO.File]::ReadAllText('" +
        str(target.with_suffix('.txt')).replace("'", "''") + "', [System.Text.Encoding]::UTF8)); "
        "$s.Dispose();"
    )
    txt = target.with_suffix('.txt')
    txt.write_text(text, encoding="utf-8")
    try:
        encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
        subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive",
                        "-EncodedCommand", encoded], capture_output=True,
                       check=True, timeout=90)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ComfyError("Windows offline speech failed. Install Piper Arabic voice or upload a recording.") from exc
    finally:
        txt.unlink(missing_ok=True)
    return target.is_file() and target.stat().st_size > 200


async def synthesize_speech(text: str, target: Path, voice: str) -> None:
    """Offline-only default: Piper Arabic voice, then Windows SAPI fallback.

    Never contacts any online speech API. No imitation of real children's voices.
    """
    if _local_piper_voice(text, target):
        return
    if _windows_sapi_voice(text, target):
        return
    raise ComfyError(
        "Offline Arabic voice is missing. Run windows/setup_voice.ps1 once, "
        "or upload your own WAV/MP3 audio for the speaking shot."
    )

def prepare_audio(src: Path, target: Path, seconds: int) -> None:
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(src),
                    '-af', 'apad', '-t', str(seconds), '-ac', '1', '-ar', '16000', str(target)],
                   capture_output=True, check=True, timeout=120)


def render_project(project: dict[str, Any], root: Path, update: Any, *, preview: bool = False) -> str:
    """Render Wan 5B GGUF motion and local Arabic speech into one MP4.

    For a GTX 1660 SUPER 6 GB, the first proof-of-concept is one 5s talking
    scene with a local voice soundtrack. True phoneme-to-lip sync is NOT part
    of this lightweight workflow and remains a separate GPU-intensive feature.
    """
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise ComfyError("ffmpeg and ffprobe must be installed on the host")
    all_scenes = project["scenes"]
    if sum(s["seconds"] for s in all_scenes) != 30:
        raise ValueError("Storyboard must add up to exactly 30 seconds")
    if preview:
        chosen = next((s for s in all_scenes
                       if s["mode"] == "talk" and s["character"] in project["characters"]), None)
        if chosen is None:
            raise ComfyError("For the audio+video test, upload the driver's picture first")
        scenes = [chosen]
    else:
        scenes = all_scenes
    workdir = root / ("preview_render" if preview else "render")
    workdir.mkdir(parents=True, exist_ok=True)
    clips: list[Path] = []
    url = os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188")
    # Lower native resolution reduces temporary VRAM use; this is a first test,
    # not an assurance that the 5B model fits 6 GB under all configurations.
    width = int(os.getenv("WAN_WIDTH", "288"))
    height = int(os.getenv("WAN_HEIGHT", "512"))
    if width < 128 or height < 128 or width % 16 or height % 16:
        raise ValueError("WAN_WIDTH and WAN_HEIGHT must be >=128 and multiples of 16")
    with ComfyClient(url) as comfy:
        try:
            comfy.health()
        except (httpx.HTTPError, ValueError) as exc:
            raise ComfyError(f"Cannot reach local ComfyUI at {url}: {exc}") from exc
        for index, scene in enumerate(scenes):
            key = scene["character"]
            picture = project["characters"].get(key)
            if not picture or "/" in picture or "\\" in picture:
                raise ComfyError(f"Missing or unsafe image filename for {key}")
            update(f"Preparing AI shot {index + 1}/{len(scenes)}", index / len(scenes))
            image_name = comfy.upload(root / "images" / picture)
            graph = image_to_video_graph(
                image_name, scene["prompt"], scene["seconds"],
                f"realmotion/{'preview_' if preview else ''}shot_{index:02d}",
                width=width, height=height)
            update(f"Generating real motion {index + 1}/{len(scenes)}", (index + .1) / len(scenes))
            job = comfy.submit(graph)
            raw = workdir / f"shot-{index}-raw.mp4"
            comfy.wait_and_download(job, raw)
            silent = workdir / f"shot-{index}-base.mp4"
            normalize_clip(raw, silent, scene["seconds"])
            final = workdir / f"shot-{index}.mp4"
            if scene["mode"] == "talk":
                if scene.get("audio_file"):
                    audio = root / "audio" / scene["audio_file"]
                elif scene.get("dialogue"):
                    audio = workdir / f"speech-{index}.wav"
                    update(f"Synthesizing offline Arabic voice {index + 1}/{len(scenes)}",
                           (index + .7) / len(scenes))
                    asyncio.run(synthesize_speech(
                        scene["dialogue"], audio, scene.get("voice", "")))
                else:
                    raise ComfyError("A speaking scene needs dialogue or an uploaded recording")
                if not audio.is_file():
                    raise ComfyError("Speech audio file missing after local synthesis")
                add_speech_to_clip(silent, audio, final, scene["seconds"])
            else:
                shutil.copyfile(silent, final)
            clips.append(final)
            update(f"Completed shot {index + 1}/{len(scenes)}", (index + 1) / len(scenes))
    update("Combining video and audio", .99)
    output = root / ("preview.mp4" if preview else "final.mp4")
    concatenate_clips(clips, output, workdir)
    return str(output)



def _process_studio_on_lan(raw: Path, output: Path, seconds: int,
                           narration: str, update: Any,
                           cancel_event: threading.Event | None = None,
                           resolution: str = "720:1280") -> bool:
    """Offload genuine FFmpeg/TTS work to authenticated MacBook LAN worker.

    A sidecar monitor polls the MacBook stage endpoint while the main request
    uploads/downloads MP4; progress is event/stage based, not a fake timer.
    """
    worker = os.environ.get("REALMOTION_WORKER_URL", "").strip().rstrip("/")
    if not worker:
        return False
    if resolution not in ("1280:720", "720:1280", "960:960"):
        raise ComfyError(f'Unsupported output canvas: {resolution}')
    token = os.environ.get("REALMOTION_WORKER_TOKEN", "").strip()
    if len(token) < 32:
        raise ComfyError('MacBook worker token is missing or too short')
    if not worker.startswith('http://') or not worker.endswith(':8787'):
        raise ComfyError('REALMOTION_WORKER_URL must be http://<MacBook-LAN-IP>:8787')
    headers = {'X-RealMotion-Token': token}
    worker_id = str(uuid.uuid4())
    stop_monitor = threading.Event()
    note_seen = set()
    progress_map = {'received': .81, 'encoding': .86, 'voice': .91,
                    'mixing': .95, 'done': .98, 'failed': .84, 'cancelled': .84}

    def monitor() -> None:
        # Separate connection; monitor remains responsive while /process runs.
        cancel_sent = False
        try:
            with httpx.Client(timeout=5, follow_redirects=False) as watcher:
                while not stop_monitor.is_set():
                    try:
                        response = watcher.get(worker + '/status/' + worker_id,
                                               headers=headers)
                        if response.status_code == 200:
                            state = response.json()
                            note = str(state.get('message', 'MacBook working'))
                            phase = str(state.get('phase', 'received'))
                            if (phase, note) not in note_seen:
                                note_seen.add((phase, note))
                                update('MacBook: ' + note, progress_map.get(phase, .83))
                        if (cancel_event is not None and cancel_event.is_set()
                                and not cancel_sent and response.status_code == 200):
                            cancel_sent = True
                            watcher.post(worker + '/cancel/' + worker_id, headers=headers)
                    except (httpx.HTTPError, ValueError, GenerationCancelled):
                        pass
                    stop_monitor.wait(1.2)
        except Exception:
            pass

    if cancel_event is not None and cancel_event.is_set():
        raise GenerationCancelled('Cancelled before MacBook processing')
    update('Checking MacBook worker authentication', .78)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with httpx.Client(timeout=httpx.Timeout(900.0, connect=10.0),
                          follow_redirects=False) as client:
            health = client.get(worker + '/health', headers=headers, timeout=8)
            if health.status_code != 200:
                raise ComfyError(
                    f'MacBook worker authentication/connection failed ({health.status_code}). '
                    'Verify worker token locally on NVIDIA and MacBook.')
            update('MacBook worker authenticated — sending AI video', .79)
            thread = threading.Thread(target=monitor, daemon=True, name='realm-macbook-monitor')
            thread.start()
            try:
                with raw.open('rb') as source:
                    with client.stream(
                        'POST', worker + '/process',
                        headers=headers,
                        files={'video': ('raw.mp4', source, 'video/mp4')},
                        data={'seconds': str(seconds), 'narration': narration.strip(),
                              'job_id': worker_id, 'resolution': resolution},
                    ) as response:
                        if response.status_code != 200:
                            detail = b''.join(response.iter_bytes())[:800].decode(
                                'utf-8', errors='replace')
                            if cancel_event is not None and cancel_event.is_set():
                                raise GenerationCancelled('MacBook job cancelled by user')
                            raise ComfyError(
                                f'MacBook failed video/audio processing ({response.status_code}): {detail}')
                        if cancel_event is not None and cancel_event.is_set():
                            raise GenerationCancelled('Cancelled before MacBook MP4 download')
                        update('MacBook finished processing — receiving MP4', .98)
                        with output.open('wb') as result:
                            for chunk in response.iter_bytes():
                                if cancel_event is not None and cancel_event.is_set():
                                    raise GenerationCancelled('Cancelled during MacBook MP4 transfer')
                                result.write(chunk)
            finally:
                stop_monitor.set()
                thread.join(timeout=3)
    except httpx.HTTPError as exc:
        raise ComfyError(f'MacBook worker network error at {worker}: {exc}') from exc
    if not output.is_file() or output.stat().st_size < 1024:
        raise ComfyError('MacBook worker did not return an MP4')
    update('MacBook returned final MP4 with audio processing complete', .99)
    return True


def render_single_studio_video(
    image: Path, prompt: str, duration: int, output: Path,
    update: Any, *, narration: str = "",
    cancel_event: threading.Event | None = None
) -> str:
    """Single-reference Firefly-style local clip. This is image-to-video, not V2V.

    A previously uploaded video supplies its *first frame* as an image seed.
    Piper/Windows speech is muxed as a soundtrack if narration is non-empty.
    Lip synchronization is not part of the light GGUF model.
    """
    if not 1 <= duration <= 10:
        raise ValueError("Duration must be between 1 and 10 seconds")
    if not image.is_file():
        raise ComfyError("Source image is missing")
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise ComfyError("FFmpeg/FFprobe is required to export MP4 with audio")
    output.parent.mkdir(parents=True, exist_ok=True)
    tag = uuid.uuid4().hex[:12]
    workdir = output.parent / f"work_{tag}"
    workdir.mkdir(parents=True, exist_ok=True)
    output_size = choose_output_size(image)
    resolution = f"{output_size[0]}:{output_size[1]}"
    width, height = choose_wan_size(image)
    custom_width = os.getenv("WAN_WIDTH")
    custom_height = os.getenv("WAN_HEIGHT")
    if bool(custom_width) != bool(custom_height):
        raise ValueError('Set both WAN_WIDTH and WAN_HEIGHT or neither')
    if custom_width and custom_height:
        width, height = int(custom_width), int(custom_height)
    if min(width, height) < 128 or width % 16 or height % 16:
        raise ValueError("WAN_WIDTH and WAN_HEIGHT must be multiples of 16 and >= 128")
    if abs(width / height - output_size[0] / output_size[1]) > .15:
        raise ValueError('Wan latent orientation conflicts with the source photo; '
                         'unset WAN_WIDTH/WAN_HEIGHT for automatic aspect correction')
    update(f"Photo layout {output_size[0]}x{output_size[1]} | Wan latent "
           f"{width}x{height} | model {os.getenv('WAN_I2V_MODEL','Wan2.2-TI2V-5B-Q2_K.gguf')}", .02)

    if cancel_event is not None and cancel_event.is_set():
        raise GenerationCancelled('Cancelled before starting GPU')
    update("Connecting to local NVIDIA / ComfyUI", 0.05)
    with ComfyClient(os.getenv("COMFYUI_URL", "http://127.0.0.1:8188")) as comfy:
        comfy.health()
        uploaded_name = comfy.upload(image)
        graph = image_to_video_graph(
            uploaded_name, prompt, duration, f"realmotion/studio_{tag}",
            width=width, height=height)
        update("GPU: sending your reference image and Wan graph", 0.12)
        job_id = comfy.submit(graph)
        update("GPU: ComfyUI accepted AI generation " + job_id[:8], 0.14)
        raw = workdir / "raw.mp4"

        def gpu_progress(kind: str, value: int, maximum: int) -> None:
            if kind == 'sampling' and maximum > 0:
                update(f"GPU sampling (real steps): {value}/{maximum}",
                       .17 + .52 * min(1., value / maximum))
            elif kind == 'queued':
                update('GPU: Wan job waiting in ComfyUI queue', .14)
            elif kind == 'running':
                update('GPU: loading Wan model / processing', .16)
            elif kind == 'node:10':
                update('GPU: decoding generated video frames', .72)
            elif kind in ('node:11', 'node:12'):
                update('GPU: saving AI video', .75)
            elif kind == 'download':
                update('GPU: downloading completed AI clip', .77)

        comfy.wait_and_download(job_id, raw, on_progress=gpu_progress,
                                cancel_event=cancel_event)

    if cancel_event is not None and cancel_event.is_set():
        raise GenerationCancelled('Cancelled after GPU generation')
    if not _process_studio_on_lan(raw, output, duration, narration, update,
                                  cancel_event=cancel_event, resolution=resolution):
        update("Encoding MP4 locally", 0.78)
        normalized = workdir / "video.mp4"
        normalize_clip(raw, normalized, duration, resolution=resolution)
        if cancel_event is not None and cancel_event.is_set():
            raise GenerationCancelled('Cancelled after local encoding')
        if narration.strip():
            update("Creating offline voice narration", 0.87)
            speech = workdir / "narration.wav"
            asyncio.run(synthesize_speech(narration.strip(), speech, "ar"))
            if cancel_event is not None and cancel_event.is_set():
                raise GenerationCancelled('Cancelled after voice synthesis')
            update("Mixing local voice with MP4", .95)
            add_speech_to_clip(normalized, speech, output, duration)
        else:
            shutil.copyfile(normalized, output)
    if cancel_event is not None and cancel_event.is_set():
        output.unlink(missing_ok=True)
        raise GenerationCancelled('Cancelled before finishing the MP4')
    if not output.is_file() or output.stat().st_size < 1024:
        raise ComfyError("Output MP4 was not produced")
    update("MP4 is ready", 1.0)
    return str(output)


def render_source_preserving_food(
    image: Path, duration: int, output: Path, update: Any,
    *, narration: str = "", cancel_event: threading.Event | None = None
) -> str:
    """Visibly labelled 2.5D/steam mode. This does not invoke a diffusion model.

    Preserves image details/landscape aspect. MacBook postprocess receives actual
    output orientation; it can also synthesize the optional Arabic narration.
    """
    from stable_motion import render_stable_food_video, StableMotionCancelled

    if not image.is_file():
        raise ComfyError('Source reference image missing')
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise ComfyError('FFmpeg and FFprobe are required')
    output.parent.mkdir(parents=True, exist_ok=True)
    width, height = choose_output_size(image)
    resolution = f"{width}:{height}"
    raw = output.parent / f"stable_{uuid.uuid4().hex[:12]}.mp4"
    try:
        try:
            render_stable_food_video(image, raw, duration, update,
                                     cancel_event=cancel_event)
        except StableMotionCancelled as exc:
            raise GenerationCancelled(str(exc)) from exc
        if cancel_event is not None and cancel_event.is_set():
            raise GenerationCancelled('Stable food animation cancelled')
        if not _process_studio_on_lan(raw, output, duration, narration, update,
                                      cancel_event=cancel_event, resolution=resolution):
            update('Stable food: encoding the native image aspect ratio', .83)
            normalized = output.parent / f"stable_normalized_{uuid.uuid4().hex[:12]}.mp4"
            try:
                normalize_clip(raw, normalized, duration, resolution=resolution)
                if cancel_event is not None and cancel_event.is_set():
                    raise GenerationCancelled('Stable food export cancelled')
                if narration.strip():
                    update('Creating optional audio for stable food', .92)
                    wav = output.parent / f"stable_voice_{uuid.uuid4().hex[:12]}.wav"
                    try:
                        asyncio.run(synthesize_speech(narration.strip(), wav, 'ar'))
                        if cancel_event is not None and cancel_event.is_set():
                            raise GenerationCancelled('Stable food voice cancelled')
                        add_speech_to_clip(normalized, wav, output, duration)
                    finally:
                        wav.unlink(missing_ok=True)
                else:
                    shutil.copyfile(normalized, output)
            finally:
                normalized.unlink(missing_ok=True)
        if not output.is_file() or output.stat().st_size < 1024:
            raise ComfyError('Stable food MP4 was not created')
        update(f'Stable food MP4 ready ({width}x{height}), source preserved', 1.0)
        return str(output)
    finally:
        raw.unlink(missing_ok=True)
