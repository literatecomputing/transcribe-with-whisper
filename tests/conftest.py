import os
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

ARTIFACTS_BASE = Path(__file__).resolve().parent.parent / "artifacts" / "test-audio"
ART_BASENAME = "test-audio"


def _reload_app_with_transcription_dir(tmpdir: Path):
    os.environ["SKIP_HF_STARTUP_CHECK"] = "1"
    os.environ["TRANSCRIPTION_DIR"] = str(tmpdir)
    # Ensure a clean import so module-level TRANSCRIPTION_DIR picks up env
    if "transcribe_with_whisper.server_app" in sys.modules:
        del sys.modules["transcribe_with_whisper.server_app"]
    sys.path.insert(0, str(Path.cwd()))
    import importlib
    mod = importlib.import_module("transcribe_with_whisper.server_app")
    # Hard-set TRANSCRIPTION_DIR and remount /files to tmpdir to be explicit
    mod.TRANSCRIPTION_DIR = Path(tmpdir)
    mod.app.mount("/files", mod.StaticFiles(directory=str(mod.TRANSCRIPTION_DIR)), name="files")
    return mod.app


@pytest.fixture()
def app_with_artifacts(tmp_path: Path):
    """Prepare a temp TRANSCRIPTION_DIR seeded from artifacts/test-audio.

    Layout under artifacts/test-audio expected:
      - test-audio.html
      - test-audio.docx (optional for some tests)
      - test-audio/ (directory) containing 0.vtt, 1.vtt, ...
    """
    src_dir = ARTIFACTS_BASE
    assert src_dir.exists(), f"Artifacts folder not found: {src_dir}"

    dest_dir = tmp_path
    # Copy top-level files
    for name in (f"{ART_BASENAME}.html", f"{ART_BASENAME}.docx"):
        src = src_dir / name
        if src.exists():
            shutil.copy2(src, dest_dir / name)

    # Copy VTT directory
    src_vtt_dir = src_dir / ART_BASENAME
    assert src_vtt_dir.exists(), f"Artifacts VTT dir not found: {src_vtt_dir}"
    dest_vtt_dir = dest_dir / ART_BASENAME
    shutil.copytree(src_vtt_dir, dest_vtt_dir)

    app = _reload_app_with_transcription_dir(dest_dir)
    client = TestClient(app)
    return SimpleNamespace(
        client=client,
        base_dir=dest_dir,
        basename=ART_BASENAME,
        vtt_dir=dest_vtt_dir,
    )
