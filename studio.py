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
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

FPS = 16
NEGATIVE = (
    "static still image, frozen pose, poor quality, distorted anatomy, "
    "deformed hands, extra fingers, face morphing, identity drift, "
    "flicker, unnatural eyes, captions, watermark"
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


class ComfyClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8188") -> None:
        self.base = base_url.rstrip('/')
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
        response = self.client.post('/prompt', json={"prompt": graph, "client_id": "ribhlab-realmotion"})
        if response.status_code >= 400:
            raise ComfyError(f"ComfyUI rejected the graph ({response.status_code}): {response.text[:1800]}")
        data = response.json()
        if data.get('node_errors'):
            raise ComfyError(f"ComfyUI graph errors: {json.dumps(data['node_errors'])[:1700]}")
        return str(data['prompt_id'])

    def wait_and_download(self, prompt_id: str, destination: Path, *, timeout: int = 3600) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            response = self.client.get(f"/history/{prompt_id}")
            response.raise_for_status()
            history = response.json().get(prompt_id)
            if history:
                status = history.get("status", {})
                if status.get('status_str') == 'error':
                    raise ComfyError(f"Generation failed: {str(status.get('messages'))[:1200]}")
                for output in history.get('outputs', {}).values():
                    # New SaveVideo may return 'videos'; previous ComfyUI versions use 'gifs'.
                    for key in ('videos', 'gifs', 'images'):
                        for item in output.get(key, []):
                            name = item.get('filename', '')
                            if not name.lower().endswith(('.mp4', '.webm', '.mov', '.mkv', '.gif')):
                                continue
                            file_resp = self.client.get('/view', params={
                                'filename': name, 'type': item.get('type', 'output'),
                                'subfolder': item.get('subfolder', '')
                            }, timeout=300)
                            file_resp.raise_for_status()
                            destination.write_bytes(file_resp.content)
                            return
                # Important: do not silently pretend that an image or an empty history is a video.
                if status.get('completed') or status.get('status_str') == 'success':
                    raise ComfyError('ComfyUI finished but SaveVideo did not return a downloadable video')
            time.sleep(3)
        raise ComfyError(f"Generation did not complete in {timeout}s; task id: {prompt_id}")


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
