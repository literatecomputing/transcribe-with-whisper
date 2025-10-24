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


def write_vtt(path: Path, entries):
    lines = ["WEBVTT", ""]
    for start, end, text in entries:
        lines.append(f"{start} --> {end}")
        lines.append(text)
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def test_edits_nearest_start_within_tolerance(tmp_path: Path):
    # Create VTTs with starts slightly offset to test nearest-start matching
    base = tmp_path / 'talk'
    base.mkdir(parents=True, exist_ok=True)
    vttA = base / '0.vtt'
    vttB = base / '1.vtt'

    write_vtt(vttA, [("00:00:10.000", "00:00:11.000", "A one"), ("00:00:14.000", "00:00:15.000", "A two")])
    write_vtt(vttB, [("00:00:12.000", "00:00:13.000", "B one")])

    app = make_app_with_temp_dir(tmp_path)
    client = TestClient(app)

    # Change targets time 12.05s (closest to B one at 12.000 within 3s tolerance)
    change = {"start": "00:00:12.050", "end": "00:00:12.900", "text": "Edited B one", "vttFile": "1.vtt", "captionIdx": "0"}
    resp = client.post("/save_transcript_edits/talk", json={"changes": [change]})
    assert resp.status_code == 200
    t1_caps = list(webvtt.read(str(base / '1.vtt')))
    assert t1_caps and t1_caps[0].text.strip() == "Edited B one"
