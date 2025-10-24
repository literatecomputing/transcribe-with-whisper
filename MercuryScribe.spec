# -*- mode: python ; coding: utf-8 -*-

# Minimal, stable spec: avoid hard-coded local .venv paths which are not present
# in CI runners. Keep datas limited to assets that are in the repository.
# -*- mode: python ; coding: utf-8 -*-


a_from_pyannote = None
try:
    from PyInstaller.utils.hooks import collect_submodules, collect_data_files
    from pathlib import Path
    try:
        pyannote_subs = collect_submodules('pyannote.audio')
    except Exception:
        pyannote_subs = ['pyannote.audio', 'pyannote.audio.models']
    try:
        raw_pyannote_datas = collect_data_files('pyannote')
    except Exception:
        raw_pyannote_datas = []
    # Filter datas to ensure source paths actually exist (avoid CI failures)
    pyannote_datas = []
    for src, dest in raw_pyannote_datas:
        if Path(src).exists():
            pyannote_datas.append((src, dest))
except Exception:
    # Fallback conservative defaults when PyInstaller helpers aren't available
    pyannote_subs = ['pyannote.audio', 'pyannote.audio.models']
    pyannote_datas = []

hidden_imports = [
    'transcribe_with_whisper',
    'transcribe_with_whisper.server_app',
    'docx',
    'htmldocx
]
hidden_imports.extend(pyannote_subs)

a = Analysis(
    ['packaging\\windows\\run_windows.py'],
    pathex=['.'],
    binaries=[],
    # Start with static datas then extend with any pyannote package files
    datas=[
        ('branding', 'branding'),
        ('packaging/ffmpeg/ffmpeg.exe', '.'),
        ('packaging/ffmpeg/ffprobe.exe', '.'),
    ] + pyannote_datas,
    hiddenimports=hidden_imports,
    hookspath=['hooks'],
    hooksconfig={},
    runtime_hooks=['hooks/runtime_utf8.py'],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MercuryScribe',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='MercuryScribe',
)
