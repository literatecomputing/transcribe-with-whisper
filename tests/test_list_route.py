import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient


def make_app_with_temp_dir(tmpdir: Path):
    os.environ['SKIP_HF_STARTUP_CHECK'] = '1'
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


def test_list_renders_and_has_expected_actions(tmp_path: Path):
    # Create fake files
    html = tmp_path / 'sample.html'
    mp4 = tmp_path / 'sample.mp4'
    docx = tmp_path / 'sample.docx'
    vtt_dir = tmp_path / 'sample'
    vtt_dir.mkdir(parents=True, exist_ok=True)
    (vtt_dir / '0.vtt').write_text('WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHello\n')
    for p in [html, mp4, docx]:
        p.write_text('x')

    app = make_app_with_temp_dir(tmp_path)
    client = TestClient(app)
    resp = client.get('/list')
    assert resp.status_code == 200
    text = resp.text

    # View link should exist for HTML
    assert 'href="/files/sample.html"' in text

    # Edit link should be absent (we removed /edit)
    assert '/edit/sample.html' not in text

    # Re-run form should appear for media
    assert 'action="/rerun"' in text and 'name="filename" value="sample.mp4"' in text

    # DOCX download should be strong-tagged
    assert '<strong>📄 Download DOCX</strong>' in text
