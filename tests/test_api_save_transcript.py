import os
import sys
from pathlib import Path

import webvtt
from fastapi.testclient import TestClient


def make_app_with_temp_dir(tmpdir: Path):
    os.environ['SKIP_HF_STARTUP_CHECK'] = '1'
    os.environ['TRANSCRIPTION_DIR'] = str(tmpdir)
    if 'transcribe_with_whisper.server_app' in sys.modules:
        del sys.modules['transcribe_with_whisper.server_app']
    sys.path.insert(0, os.getcwd())
    import importlib
    mod = importlib.import_module('transcribe_with_whisper.server_app')
    mod.TRANSCRIPTION_DIR = Path(tmpdir)
    mod.app.mount('/files', mod.StaticFiles(directory=str(mod.TRANSCRIPTION_DIR)), name='files')
    return mod.app


def test_api_save_transcript_writes_vtts(tmp_path: Path):
    """Test that /api/save-transcript endpoint saves segments to VTT files"""
    app = make_app_with_temp_dir(tmp_path)
    client = TestClient(app)

    basename = 'rewrite'
    segments = [
        {"speaker": "Speaker 1", "start_time": "00:00:01.000", "end_time": "00:00:02.000", "text": "alpha"},
        {"speaker": "Speaker 2", "start_time": "00:00:03.000", "end_time": "00:00:04.000", "text": "bravo"},
        {"speaker": "Speaker 1", "start_time": "00:00:05.000", "end_time": "00:00:06.000", "text": "charlie"},
    ]

    resp = client.post(f"/api/save-transcript/{basename}", json={"segments": segments})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("success") is True

    vtt_dir = tmp_path / basename
    v0 = vtt_dir / '0.vtt'
    v1 = vtt_dir / '1.vtt'
    assert v0.exists() and v1.exists()

    caps0 = list(webvtt.read(str(v0)))
    caps1 = list(webvtt.read(str(v1)))

    # Speaker 1 entries go to 0.vtt (first seen), Speaker 2 to 1.vtt
    texts0 = [c.text.strip() for c in caps0]
    texts1 = [c.text.strip() for c in caps1]
    assert texts0 == ["alpha", "charlie"]
    assert texts1 == ["bravo"]
