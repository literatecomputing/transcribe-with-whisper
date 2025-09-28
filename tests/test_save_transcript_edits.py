import os
import sys
from pathlib import Path
import webvtt

import pytest
from fastapi.testclient import TestClient
import pytest


def make_app_with_temp_dir(tmpdir: Path):
    os.environ['SKIP_HF_STARTUP_CHECK'] = '1'
    os.environ['TRANSCRIPTION_DIR'] = str(tmpdir)
    # Ensure module-level TRANSCRIPTION_DIR reads our env
    # Reload module after adjusting env
    if 'transcribe_with_whisper.server_app' in sys.modules:
        del sys.modules['transcribe_with_whisper.server_app']
    sys.path.insert(0, os.getcwd())
    import importlib
    mod = importlib.import_module('transcribe_with_whisper.server_app')
    # Monkey-patch TRANSCRIPTION_DIR to tmpdir without changing code
    mod.TRANSCRIPTION_DIR = Path(tmpdir)
    mod.app.mount('/files', mod.StaticFiles(directory=str(mod.TRANSCRIPTION_DIR)), name='files')
    return mod.app


def write_vtt(path: Path, entries: list[tuple[str, str, str]]):
    # entries: list of (start, end, text)
    lines = ["WEBVTT", ""]
    for start, end, text in entries:
        lines.append(f"{start} --> {end}")
        lines.append(text)
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


@pytest.mark.xfail(reason="/save_transcript_edits not updating VTT captions as expected in tests; pending app investigation", strict=False)
def test_save_transcript_edits_updates_three_vtts(tmp_path: Path):
    # Arrange: create temp TRANSCRIPTION_DIR with basename 'sample'
    base = tmp_path / 'sample'
    base.mkdir(parents=True, exist_ok=True)

    # Create three VTT files with distinct caption times
    vtt0 = base / '0.vtt'
    vtt1 = base / '1.vtt'
    vtt2 = base / '2.vtt'

    write_vtt(vtt0, [("00:00:00.000", "00:00:01.000", "Hello from 0")])
    write_vtt(vtt1, [("00:00:02.000", "00:00:03.000", "Hello from 1")])
    write_vtt(vtt2, [("00:00:04.000", "00:00:05.000", "Hello from 2")])

    app = make_app_with_temp_dir(tmp_path)
    client = TestClient(app)

    # Act: post changes that target one caption in each vtt file
    changes = [
        {"start": "00:00:00.050", "end": "00:00:00.950", "text": "Edited zero"},
        {"start": "00:00:02.100", "end": "00:00:02.900", "text": "Edited one"},
        {"start": "00:00:04.200", "end": "00:00:04.800", "text": "Edited two"},
    ]

    resp = client.post(f"/save_transcript_edits/sample", json={"changes": changes})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("success") is True
    # Should apply 3/3 changes
    assert data.get("message", "").startswith("Applied 3/3"), data
    # Optional: check unmatched is empty
    assert data.get("unmatched") in ([], None)

    # Assert: read files and verify edits applied
    caps0 = list(webvtt.read(str(vtt0)))
    caps1 = list(webvtt.read(str(vtt1)))
    caps2 = list(webvtt.read(str(vtt2)))
    assert caps0 and caps0[0].text.strip() == "Edited zero"
    assert caps1 and caps1[0].text.strip() == "Edited one"
    assert caps2 and caps2[0].text.strip() == "Edited two"
