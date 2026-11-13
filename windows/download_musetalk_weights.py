"""Download official MuseTalk 1.5 and supporting checkpoints once.

No inference calls, no uploads of pictures. Honor original model licenses.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from huggingface_hub import hf_hub_download

WEIGHTS = (
    ("TMElyralab/MuseTalk", "musetalkV15/unet.pth", "musetalkV15/unet.pth"),
    ("TMElyralab/MuseTalk", "musetalkV15/musetalk.json", "musetalkV15/musetalk.json"),
    ("stabilityai/sd-vae-ft-mse", "config.json", "sd-vae/config.json"),
    ("stabilityai/sd-vae-ft-mse", "diffusion_pytorch_model.bin",
     "sd-vae/diffusion_pytorch_model.bin"),
    ("openai/whisper-tiny", "config.json", "whisper/config.json"),
    ("openai/whisper-tiny", "pytorch_model.bin", "whisper/pytorch_model.bin"),
    ("openai/whisper-tiny", "preprocessor_config.json",
     "whisper/preprocessor_config.json"),
    ("yzd-v/DWPose", "dw-ll_ucoco_384.pth", "dwpose/dw-ll_ucoco_384.pth"),
    ("ManyOtherFunctions/face-parse-bisent", "79999_iter.pth",
     "face-parse-bisent/79999_iter.pth"),
    ("ManyOtherFunctions/face-parse-bisent", "resnet18-5c106cde.pth",
     "face-parse-bisent/resnet18-5c106cde.pth"),
)


def download(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for i, (repo, filename, target) in enumerate(WEIGHTS, start=1):
        output = root / target
        if output.is_file() and output.stat().st_size > 1024:
            print(f"{i}/{len(WEIGHTS)} already present: {target}", flush=True)
            continue
        print(f"{i}/{len(WEIGHTS)} downloading: {repo}/{filename}", flush=True)
        downloaded = Path(hf_hub_download(
            repo_id=repo, filename=filename, local_dir=root / "_downloads" / repo.replace("/", "_")
        ))
        if downloaded.stat().st_size < 1024:
            raise RuntimeError(f"Invalid MuseTalk model download: {repo}/{filename}")
        output.parent.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copy2(downloaded, output)
        print(f"Saved: {output}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("models_directory", type=Path)
    download(parser.parse_args().models_directory)
