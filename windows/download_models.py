"""Download official Wan2.2 5B ComfyUI model files once (no GPU inference API).

Called by windows/install_models.ps1. Hugging Face transfers may need Internet
on the first run; all later video renders happen locally using model weights.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from huggingface_hub import hf_hub_download

FILES = (
    ("Comfy-Org/Wan_2.2_ComfyUI_Repackaged",
     "split_files/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors",
     "diffusion_models/wan2.2_ti2v_5B_fp16.safetensors", 8_000_000_000),
    ("Comfy-Org/Wan_2.2_ComfyUI_Repackaged",
     "split_files/vae/wan2.2_vae.safetensors",
     "vae/wan2.2_vae.safetensors", 1_000_000_000),
    ("Comfy-Org/Wan_2.1_ComfyUI_repackaged",
     "split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors",
     "text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors", 5_000_000_000),
)


def download_all(root: Path) -> None:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"ComfyUI models directory does not exist: {root}")
    staging = root / "_realm_download_staging"
    for i, (repo, name, relative, min_bytes) in enumerate(FILES, 1):
        dest = root / relative
        if dest.is_file() and dest.stat().st_size >= min_bytes:
            print(f"[{i}/{len(FILES)}] Already installed: {relative}")
            continue
        print(f"[{i}/{len(FILES)}] Downloading official: {repo}/{name}", flush=True)
        downloaded = Path(hf_hub_download(
            repo_id=repo, filename=name, local_dir=staging
        ))
        if downloaded.stat().st_size < min_bytes:
            raise RuntimeError(f"Downloaded file size is unexpectedly small: {downloaded}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Same filesystem: rename instead of copying another 9 GB.
        os.replace(downloaded, dest)
        print(f"Installed to {dest}", flush=True)
    print("All three Wan 2.2 5B motion files are installed.", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("models_dir", type=Path)
    args = parser.parse_args()
    download_all(args.models_dir)


if __name__ == "__main__":
    main()
