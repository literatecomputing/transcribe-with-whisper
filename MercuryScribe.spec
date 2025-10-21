# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['packaging\\windows\\run_windows.py'],
    pathex=['.'],
    binaries=[],
    datas=[('branding', 'branding'), ('packaging/ffmpeg/ffmpeg.exe', '.'), ('packaging/ffmpeg/ffprobe.exe', '.')],
    hiddenimports=['transcribe_with_whisper', 'transcribe_with_whisper.server_app', 'pyannote', 'pyannote.audio', 'pyannote.audio.telemetry'],
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
