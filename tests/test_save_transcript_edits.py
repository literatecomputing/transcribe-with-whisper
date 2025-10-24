import os
import sys
from pathlib import Path


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
