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


def _ensure_transcription_dir():
    # Use %LOCALAPPDATA% on Windows if available
    localapp = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA")
    default = Path(localapp) / "MercuryScribe" if localapp else Path.cwd() / "mercuryscribe"
    td = Path(os.getenv("TRANSCRIPTION_DIR", str(default)))
    td.mkdir(parents=True, exist_ok=True)
    return td


def _add_bundled_ffmpeg_to_path():
    # If ffmpeg.exe is next to the exe, add that folder to PATH
    exe_dir = Path(sys.executable).resolve().parent
    ffmpeg = exe_dir / "ffmpeg.exe"
    ffprobe = exe_dir / "ffprobe.exe"
    if ffmpeg.exists() and ffprobe.exists():
        os.environ["PATH"] = f"{exe_dir}{os.pathsep}" + os.environ.get("PATH", "")
        return True
    return False


def _write_log(msg: str):
    td = _ensure_transcription_dir()
    log_path = td / LOG_NAME
    try:
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass


def main():
    _write_log("Starting MercuryScribe (Windows bundle)")

    _add_bundled_ffmpeg_to_path()

    # Prefer using the package's entrypoint programmatically to avoid subprocess complexity
    try:
        # Ensure the package is importable
        import transcribe_with_whisper.server_app as server_app

        # Run the app via uvicorn programmatically
        import uvicorn

        host = os.getenv("HOST", "127.0.0.1")
        port = int(os.getenv("PORT", "5001"))

        # Open browser shortly after server starts
        def on_startup():
            url = f"http://{host}:{port}/"
            try:
                webbrowser.open(url)
                _write_log(f"Opened browser to {url}")
            except Exception as exc:
                _write_log(f"Failed to open browser: {exc}")

        _write_log(f"Launching uvicorn on {host}:{port}")
        uvicorn.run(server_app.app, host=host, port=port, lifespan="on", access_log=False)

    except Exception as exc:
        _write_log(f"Failed to start server: {exc}")
        raise


if __name__ == "__main__":
    main()
