"""
Entrypoint script for the Windows PyInstaller bundle.
- Ensures bundled ffmpeg is on PATH
- Sets sensible TRANSCRIPTION_DIR default (%%LOCALAPPDATA%%\MercuryScribe)
- Launches the FastAPI app from the package and opens the default browser to the setup page
- Writes a simple log file to %LOCALAPPDATA%/MercuryScribe/log.txt

This script is intended to be bundled with PyInstaller (onedir).
"""
from __future__ import annotations

import os
import sys
import time
import webbrowser
from pathlib import Path

LOG_NAME = "mercuryscribe.log"
BUNDLE_LOG_NAME = "bundle_run.log"
BUNDLE_FLAG_NAME = "server_started.flag"


def _ensure_transcription_dir():
    # Use %LOCALAPPDATA% on Windows if available
    localapp = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA")
    default = Path(localapp) / "MercuryScribe" if localapp else Path.cwd() / "mercuryscribe"
    td = Path(os.getenv("TRANSCRIPTION_DIR", str(default)))
    td.mkdir(parents=True, exist_ok=True)
    return td


def _add_bundled_ffmpeg_to_path():
    exe_dir = Path(sys.executable).resolve().parent
    ffmpeg = exe_dir / "ffmpeg.exe"
    ffprobe = exe_dir / "ffprobe.exe"
    internal_dir = exe_dir / "_internal"
    internal_ffmpeg = internal_dir / "ffmpeg.exe"
    internal_ffprobe = internal_dir / "ffprobe.exe"
    added = False
    if ffmpeg.exists() and ffprobe.exists():
        os.environ["PATH"] = f"{exe_dir}{os.pathsep}" + os.environ.get("PATH", "")
        added = True
    if internal_ffmpeg.exists() and internal_ffprobe.exists():
        os.environ["PATH"] = f"{internal_dir}{os.pathsep}" + os.environ.get("PATH", "")
        added = True
    return added

def _log_ffmpeg_path():
    path = os.environ.get("PATH", "")
    print(f"[MercuryScribe] PATH: {path}")
    ffmpeg_path = None
    for p in path.split(os.pathsep):
        candidate = Path(p) / "ffmpeg.exe"
        if candidate.exists():
            ffmpeg_path = str(candidate)
            break
    if ffmpeg_path:
        print(f"[MercuryScribe] ffmpeg found at: {ffmpeg_path}")
    else:
        print("[MercuryScribe] ffmpeg NOT found in PATH!")


def _write_log(msg: str):
    td = _ensure_transcription_dir()
    log_path = td / LOG_NAME
    try:
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass


def _write_bundle_log(msg: str):
    # Write a log next to the exe so the build script can always find it inside the bundle
    try:
        exe_dir = Path(sys.executable).resolve().parent
        log_path = exe_dir / BUNDLE_LOG_NAME
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        # best-effort only
        pass


def main():
    _write_log("Starting MercuryScribe (Windows bundle)")
    _write_bundle_log("Starting MercuryScribe (Windows bundle)")

    _add_bundled_ffmpeg_to_path()
    _log_ffmpeg_path()

    # Prefer using the package's entrypoint programmatically to avoid subprocess complexity
    try:
        # Ensure the package is importable
        import transcribe_with_whisper.server_app as server_app

        # Run the app via uvicorn programmatically
        import uvicorn
        import traceback

        host = os.getenv("HOST", "127.0.0.1")
        port = int(os.getenv("PORT", "5001"))

        # Open browser shortly after server starts and write a startup flag file
        def on_startup():
            url = f"http://{host}:{port}/"
            try:
                webbrowser.open(url)
                _write_log(f"Opened browser to {url}")
                _write_bundle_log(f"Opened browser to {url}")
            except Exception as exc:
                _write_log(f"Failed to open browser: {exc}")
                _write_bundle_log(f"Failed to open browser: {exc}")
            # write a readiness flag next to the exe so build scripts can detect successful startup
            try:
                exe_dir = Path(sys.executable).resolve().parent
                flag_path = exe_dir / BUNDLE_FLAG_NAME
                with open(flag_path, "w", encoding="utf-8") as fh:
                    fh.write("started\n")
                _write_bundle_log(f"Wrote startup flag at {flag_path}")
            except Exception as exc:
                _write_bundle_log(f"Failed to write startup flag: {exc}")

        _write_log(f"Launching uvicorn on {host}:{port}")
        _write_bundle_log(f"Launching uvicorn on {host}:{port}")

        # Register the startup handler so FastAPI calls it when ready
        try:
            server_app.app.add_event_handler("startup", on_startup)
        except Exception:
            # best-effort: handler registration may not be available; on_startup will still try to write the flag
            _write_bundle_log("Failed to register startup handler (continuing)")

        # Run uvicorn and catch top-level exceptions so they get written to the bundle log
        try:
            uvicorn.run(server_app.app, host=host, port=port, lifespan="on", access_log=False)
        except Exception as exc:
            _write_bundle_log(f"Exception running uvicorn: {exc}")
            _write_bundle_log(traceback.format_exc())
            _write_log(f"Exception running uvicorn: {exc}")
            raise

    except Exception as exc:
        import traceback

        _write_log(f"Failed to start server: {exc}")
        _write_bundle_log(f"Failed to start server: {exc}")
        _write_bundle_log(traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
