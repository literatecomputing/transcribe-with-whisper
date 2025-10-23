# -*- mode: python ; coding: utf-8 -*-


a_from_pyannote = None
try:
    from PyInstaller.utils.hooks import collect_submodules, collect_data_files
    pyannote_subs = collect_submodules('pyannote.audio')
    # Collect package data files for pyannote so the onedir build contains the
    # package files (models, subpackages, data) that imports expect at runtime.
    pyannote_datas = collect_data_files('pyannote')
except Exception:
    # Fallback conservative defaults when PyInstaller helpers aren't available
    pyannote_subs = ['pyannote.audio', 'pyannote.audio.models']
    pyannote_datas = []

hidden_imports = [
    'transcribe_with_whisper',
    'transcribe_with_whisper.server_app',
]
hidden_imports.extend(pyannote_subs)
hidden_imports.extend(["docx", "htmldocx"])


a = Analysis(
    ['packaging\\windows\\run_windows.py'],
    pathex=['.'],
    binaries=[],
    # Start with static datas then extend with any pyannote package files
    datas=[
        ('branding', 'branding'),
        ('packaging/ffmpeg/ffmpeg.exe', '.'),
        ('packaging/ffmpeg/ffprobe.exe', '.'),
        # Include pyannote telemetry config so runtime can find it inside the bundle
        ('.venv/Lib/site-packages/pyannote/audio/telemetry/config.yaml', '_internal/pyannote/audio/telemetry'),
    ] + pyannote_datas,
    hiddenimports=hidden_imports,
    hookspath=['hooks'],
    hooksconfig={},
    runtime_hooks=[],
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
