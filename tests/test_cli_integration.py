import html as html_module
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_AUDIO = REPO_ROOT / 'examples' / 'test-audio.mp3'

@pytest.mark.integration
@pytest.mark.skipif(not EXAMPLES_AUDIO.exists(), reason="examples/test-audio.mp3 not present")
def test_cli_processes_example_audio(tmp_path: Path, monkeypatch):
    # Require HF token to run end-to-end; skip if not set
    token = os.getenv('HUGGING_FACE_AUTH_TOKEN')
    if not token:
        pytest.skip('HUGGING_FACE_AUTH_TOKEN not set; skipping integration test')

    # Copy example audio into tmp working dir
    work = tmp_path
    shutil.copy(EXAMPLES_AUDIO, work / EXAMPLES_AUDIO.name)

    # Run the CLI via module to avoid changing code
    cmd = [sys.executable, '-m', 'transcribe_with_whisper.main', EXAMPLES_AUDIO.name]
    # Pass the environment including the HF token to the subprocess
    env = os.environ.copy()
    env['HUGGING_FACE_AUTH_TOKEN'] = token
    proc = subprocess.run(cmd, cwd=str(work), capture_output=True, text=True, env=env)
    assert proc.returncode == 0, f"CLI failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"

    basename = EXAMPLES_AUDIO.stem
    # Check outputs
    html = work / f"{basename}.html"
    vtt_dir = work / basename
    assert html.exists(), "Expected HTML output missing"
    assert vtt_dir.exists(), "Expected VTT directory missing"
    assert any(vtt_dir.glob('*.vtt')), "No VTT files produced"

    # Verify phrase is present in the generated HTML
    phrase = "in the modern tech landscape"
    html_text = html.read_text(encoding="utf-8", errors="ignore")
    assert phrase in html_text, f"Phrase not found in HTML: {phrase!r}"

    # The transcription CLI now creates a DOCX itself; verify it exists and contains the phrase
    docx = work / f"{basename}.docx"
    assert docx.exists(), "Expected DOCX output missing (the CLI should create a .docx file)"
    # Verify phrase within DOCX contents (read document.xml from zip)
    try:
        with zipfile.ZipFile(docx) as zf:
            with zf.open('word/document.xml') as f:
                xml_bytes = f.read()
        xml_text = xml_bytes.decode('utf-8', errors='ignore')
        # strip XML tags and unescape entities to get plain text approximation
        text_only = re.sub(r'<[^>]+>', '', xml_text)
        text_only = html_module.unescape(text_only)
        assert phrase in text_only, f"Phrase not found in DOCX text: {phrase!r}"
    except KeyError:
        pytest.fail('DOCX missing word/document.xml')

    generator_match = re.search(r'<meta name="generator"\s+content="([^"]+)">', html_text)
    assert generator_match, "Generator meta tag missing from CLI HTML output"
    generator_value = generator_match.group(1)
    family, _, version = generator_value.partition(" ")
    assert family == "transcribe-with-whisper", (
        "Expected CLI generator meta to originate from transcribe-with-whisper"
    )
    assert version.strip(), "Generator meta tag should include a version suffix"

    

    # Optionally keep artifacts for inspection
    if os.getenv("KEEP_ARTIFACTS"):
        artifacts_dir = REPO_ROOT / 'artifacts' / basename
        try:
            shutil.rmtree(artifacts_dir)
        except FileNotFoundError:
            pass
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        # copy HTML
        shutil.copy2(html, artifacts_dir / html.name)
        # # copy VTT directory
        if vtt_dir.exists():
            shutil.copytree(vtt_dir, artifacts_dir / vtt_dir.name)
        # copy DOCX if it exists
        if 'docx' in locals() and docx.exists():
            shutil.copy2(docx, artifacts_dir / docx.name)
