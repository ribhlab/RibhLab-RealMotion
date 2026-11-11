"""Download precisely the 3 verified Wan 2.2 5B GGUF files required by local preview.

Unlike the original FP16 5B weights, this script targets Q2_K for 6 GB VRAM
experiments. Downloading weights does not send any personal images to the cloud.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path

from huggingface_hub import hf_hub_download

FILES = (
    ("QuantStack/Wan2.2-TI2V-5B-GGUF",
     "Wan2.2-TI2V-5B-Q2_K.gguf",
     "unet/Wan2.2-TI2V-5B-Q2_K.gguf", 1_500_000_000,
     "bebb995b18adf2357366e2a62ecc8a020f759418c0d62987df88bb58aed135e2"),
    ("Comfy-Org/Wan_2.2_ComfyUI_Repackaged",
     "split_files/vae/wan2.2_vae.safetensors",
     "vae/wan2.2_vae.safetensors", 1_000_000_000,
     "e40321bd36b9709991dae2530eb4ac303dd168276980d3e9bc4b6e2b75fed156"),
    ("Comfy-Org/Wan_2.2_ComfyUI_Repackaged",
     "split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors",
     "text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors", 6_000_000_000,
     "c3355d30191f1f066b26d93fba017ae9809dce6c627dda5f6a66eaa651204f68"),
)


def verified(path: Path, min_bytes: int, expected_sha: str) -> bool:
    if not path.is_file() or path.stat().st_size < min_bytes:
        return False
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest().lower() == expected_sha


def download_all(root: Path) -> None:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"ComfyUI models directory does not exist: {root}")
    staging = root / "_realm_download_staging"
    for i, (repo, filename, relative, min_bytes, sha) in enumerate(FILES, 1):
        output = root / relative
        if verified(output, min_bytes, sha):
            print(f"[{i}/{len(FILES)}] Already verified: {relative}", flush=True)
            continue
        print(f"[{i}/{len(FILES)}] Downloading {repo}/{filename}", flush=True)
        file = Path(hf_hub_download(repo_id=repo, filename=filename, local_dir=staging))
        if not verified(file, min_bytes, sha):
            raise RuntimeError(f"SHA256 mismatch: {filename} — refusing to install corrupted weights")
        output.parent.mkdir(parents=True, exist_ok=True)
        os.replace(file, output)
        print(f"Verified and installed: {output}", flush=True)
    print("Wan 2.2 Q2 GGUF, Wan VAE and FP8 text encoder are all installed.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("models_dir", type=Path)
    download_all(parser.parse_args().models_dir)
