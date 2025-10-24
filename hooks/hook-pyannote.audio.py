"""PyInstaller hook for pyannote.audio

This hook explicitly collects pyannote.audio submodules and package data so
they get included in frozen builds. We filter data file sources to existing
paths to avoid causing Analysis-time failures on environments with different
site-packages layouts.
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

hiddenimports = []
datas = []

try:
    # Collect all pyannote.audio submodules (this should include pyannote.audio.models)
    hiddenimports = collect_submodules('pyannote.audio') or []
except Exception:
    # Conservative fallback
    hiddenimports = ['pyannote.audio', 'pyannote.audio.models']

try:
    raw_datas = collect_data_files('pyannote') or []
    for src, dest in raw_datas:
        if Path(src).exists():
            datas.append((src, dest))
except Exception:
    # If collecting datas fails, leave datas empty; it's better to ship code
    # modules than to fail the build due to missing local paths.
    datas = []
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

hiddenimports = collect_submodules('pyannote.audio')
datas = collect_data_files('pyannote.audio')
