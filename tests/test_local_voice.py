"""Local-only speech tests: no Internet or provider credentials are required."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import studio


def test_voice_selects_local_piper_first(tmp_path, monkeypatch):
    calls = []
    def piper(text: str, target: Path) -> bool:
        calls.append(('piper', text))
        target.write_bytes(b'RIFFlocal-wav')
        return True
    def sapi(text: str, target: Path) -> bool:
        calls.append(('sapi', text))
        return False
    monkeypatch.setattr(studio, '_local_piper_voice', piper)
    monkeypatch.setattr(studio, '_windows_sapi_voice', sapi)
    dst = tmp_path / 'voice.wav'
    asyncio.run(studio.synthesize_speech('مرحبا', dst, 'local'))
    assert dst.exists()
    assert calls == [('piper', 'مرحبا')]


def test_voice_falls_back_only_to_local_sapi(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(studio, '_local_piper_voice', lambda *_: False)
    def sapi(text, target):
        calls.append('sapi')
        target.write_bytes(b'RIFFlocal-wav')
        return True
    monkeypatch.setattr(studio, '_windows_sapi_voice', sapi)
    asyncio.run(studio.synthesize_speech('hello', tmp_path / 'x.wav', 'local'))
    assert calls == ['sapi']


def test_missing_local_voice_fails_without_cloud(tmp_path, monkeypatch):
    monkeypatch.setattr(studio, '_local_piper_voice', lambda *_: False)
    monkeypatch.setattr(studio, '_windows_sapi_voice', lambda *_: False)
    with pytest.raises(studio.ComfyError, match='Offline Arabic voice'):
        asyncio.run(studio.synthesize_speech('مرحبا', tmp_path / 'x.wav', 'local'))


def test_local_setup_has_no_paid_api_dependency():
    requirements = (Path(__file__).resolve().parent.parent / 'requirements.txt').read_text()
    assert 'edge-tts' not in requirements
    assert 'replicate' not in requirements.lower()
    assert 'vercel' not in requirements.lower()
