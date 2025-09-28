import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient


def make_app_with_temp_dir(tmpdir: Path):
    os.environ['SKIP_HF_STARTUP_CHECK'] = '1'
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
    change = {"start": "00:00:12.050", "end": "00:00:12.900", "text": "Edited B one"}
    resp = client.post("/save_transcript_edits/talk", json={"changes": [change]})
    assert resp.status_code == 200
    assert (base / '1.vtt').read_text(encoding='utf-8').find("Edited B one") != -1


def test_multiple_changes_across_tracks(tmp_path: Path):
    base = tmp_path / 'panel'
    base.mkdir(parents=True, exist_ok=True)
    vtt0 = base / '0.vtt'
    vtt1 = base / '1.vtt'
    vtt2 = base / '2.vtt'

    write_vtt(vtt0, [("00:00:01.000", "00:00:02.000", "zero")])
    write_vtt(vtt1, [("00:00:03.000", "00:00:04.000", "one")])
    write_vtt(vtt2, [("00:00:05.000", "00:00:06.000", "two")])

    app = make_app_with_temp_dir(tmp_path)
    client = TestClient(app)

    changes = [
        {"start": "1.1", "end": "1.8", "text": "Z"},
        {"start": 3.1, "end": 3.9, "text": "O"},
        {"start": "00:00:05.100", "end": "00:00:05.800", "text": "T"},
    ]

    resp = client.post("/save_transcript_edits/panel", json={"changes": changes})
    assert resp.status_code == 200
    t0 = (base / '0.vtt').read_text(encoding='utf-8')
    t1 = (base / '1.vtt').read_text(encoding='utf-8')
    t2 = (base / '2.vtt').read_text(encoding='utf-8')

    assert "Z" in t0
    assert "O" in t1
    assert "T" in t2
