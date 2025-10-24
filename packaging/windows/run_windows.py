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
import time
import webbrowser
from pathlib import Path
import sys
import io
import importlib
import traceback
import os as _os

# Configure text IO to UTF-8 as early as possible at module import time.
# Prefer setting PYTHONIOENCODING and avoid rewrapping sys.stdout/stderr here,
# because wrapping can fail in frozen/executed-with-redirection scenarios
# (it may attempt to wrap a closed underlying buffer). The environment var
# is sufficient in most cases to ensure UTF-8 encoding for subprocesses and
# Python text IO.
try:
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
except Exception:
    pass

# Defensive: if sys.stdout/stderr are closed (can happen in frozen apps
# run under certain launchers or when output was redirected and closed),
# replace them with devnull file objects so future prints won't raise.
try:
    if getattr(sys.stderr, "closed", False):
        sys.stderr = open(_os.devnull, "w", encoding="utf-8", errors="replace")
    if getattr(sys.stdout, "closed", False):
        sys.stdout = open(_os.devnull, "w", encoding="utf-8", errors="replace")
except Exception:
    # best-effort
    pass

# Early exception handler that writes tracebacks to a bundle-local file so
# we can diagnose import-time errors without depending on sys.stderr.
def _early_excepthook(exc_type, exc_value, exc_tb):
    try:
        exe_dir = Path(sys.executable).resolve().parent
        log_path = exe_dir / BUNDLE_LOG_NAME
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write("[EARLY-EXCEPTION] \n")
            fh.write("".join(traceback.format_exception(exc_type, exc_value, exc_tb)))
    except Exception:
        # If even this fails, there's nothing else we can do here
        pass

sys.excepthook = _early_excepthook

# Prefer packages placed next to the exe (onedir) over frozen archive modules.
# This makes it possible to copy a package directory (e.g. pyannote/) into the
# onedir next to the executable and have the frozen app import it as a normal
# filesystem package.
try:
    exe_dir = Path(sys.executable).resolve().parent
    exe_dir_str = str(exe_dir)
    if exe_dir_str and exe_dir_str not in sys.path:
        sys.path.insert(0, exe_dir_str)
        # Avoid calling runtime helper functions here (they are defined later).
        # We'll rely on the main() function to write bundle logs after helpers exist.
except Exception:
    # best-effort only
    pass

LOG_NAME = "mercuryscribe.log"
BUNDLE_LOG_NAME = "bundle_run.log"
BUNDLE_FLAG_NAME = "server_started.flag"


def _ensure_transcription_dir():
    # Prefer the user's home directory (USERPROFILE/HOME) on Windows to match macOS/Linux/Docker behavior
    home = os.getenv("USERPROFILE") or os.getenv("HOME")
    if home:
        default = Path(home) / "mercuryscribe"
    else:
        # Fallback to LOCALAPPDATA\MercuryScribe if a home directory isn't available
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


def _insert_pyannote_telemetry_stub():
    """Insert a defensive no-op telemetry stub for pyannote before importing the package.

    This must run early (including CLI mode) to avoid import-time IO inside frozen bundles.
    """
    try:
        import types
        import sys as _sys
        telemetry_mod_name = "pyannote.audio.telemetry"
        telemetry_metrics_name = "pyannote.audio.telemetry.metrics"
        if telemetry_mod_name not in _sys.modules:
            stub = types.ModuleType(telemetry_mod_name)
            def set_telemetry_metrics(enabled, save_choice_as_default=False):
                return None
            def set_opentelemetry_log_level(level):
                return None
            def track_model_init(*args, **kwargs):
                return None
            def track_pipeline_init(*args, **kwargs):
                return None
            def track_pipeline_apply(*args, **kwargs):
                return None
            stub.set_telemetry_metrics = set_telemetry_metrics
            stub.set_opentelemetry_log_level = set_opentelemetry_log_level
            stub.track_model_init = track_model_init
            stub.track_pipeline_init = track_pipeline_init
            stub.track_pipeline_apply = track_pipeline_apply
            _sys.modules[telemetry_mod_name] = stub
            _sys.modules[telemetry_metrics_name] = stub
            _write_bundle_log("Inserted pyannote.telemetry stub into sys.modules (early)")
    except Exception:
        # best-effort only
        pass


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
    # Ensure stdout/stderr are UTF-8 to avoid UnicodeEncodeError when the
    # application prints emoji or other non-encodable characters on Windows
    # consoles that default to a legacy code page.
    try:
        # If PYTHONIOENCODING isn't already set, prefer utf-8 for all text IO.
        os.environ.setdefault("PYTHONIOENCODING", "utf-8")
        # Setting PYTHONIOENCODING is typically sufficient. Avoid rewrapping
        # sys.stdout/sys.stderr here because it can lead to 'I/O operation on
        # closed file' when the process is invoked with redirected output.
        _write_bundle_log("Set PYTHONIOENCODING=utf-8 (no rewrap) to avoid encoding errors")
    except Exception:
        # Best-effort: if wrapping fails (rare under frozen exe), continue.
        pass

    _write_log("Starting MercuryScribe (Windows bundle)")
    _write_bundle_log("Starting MercuryScribe (Windows bundle)")
    # Ensure ffmpeg path is available to any subprocesses and log what we find
    _add_bundled_ffmpeg_to_path()
    _log_ffmpeg_path()

    # Disable pyannote telemetry explicitly via environment variable as recommended
    # by pyannote docs. Setting the environment variable prevents the telemetry
    # module from performing import-time config IO inside frozen bundles.
    try:
        os.environ.setdefault("PYANNOTE_METRICS_ENABLED", "0")
        _write_bundle_log("Set PYANNOTE_METRICS_ENABLED=0 to disable pyannote telemetry")
    except Exception:
        # best-effort only
        pass

    # Insert telemetry stub early so CLI-mode imports below cannot trigger file IO
    _insert_pyannote_telemetry_stub()

    # Support a simple CLI mode when invoked as: MercuryScribe.exe --run-cli <args...>
    # This allows the web server to spawn the bundled exe to perform CLI work
    if "--run-cli" in sys.argv:
        try:
            idx = sys.argv.index("--run-cli")
            cli_args = sys.argv[idx+1:]
            # Make sys.argv look like a normal CLI invocation for the bundled module
            sys.argv = [sys.executable] + cli_args
            _write_bundle_log(f"Entering CLI mode with args: {cli_args}")
            import transcribe_with_whisper.main as cli_mod
            cli_mod.main()
            return
        except Exception as exc:
            import traceback
            _write_bundle_log(f"Exception in CLI mode: {exc}")
            _write_bundle_log(traceback.format_exc())
            raise

    # Prefer using the package's entrypoint programmatically to avoid subprocess complexity
    try:
        # Insert a safe no-op telemetry stub so importing pyannote subpackages
        # cannot trigger import-time IO inside a frozen bundle. We set the
        # environment variable first (upstream-recommended), then register a
        # stub module for both 'pyannote.audio.telemetry' and
        # 'pyannote.audio.telemetry.metrics'. This is intentionally defensive
        # and avoids importing the real telemetry module inside the bundle.
        try:
            import types
            telemetry_mod_name = "pyannote.audio.telemetry"
            telemetry_metrics_name = "pyannote.audio.telemetry.metrics"
            if telemetry_mod_name not in sys.modules:
                stub = types.ModuleType(telemetry_mod_name)
                def set_telemetry_metrics(enabled, save_choice_as_default=False):
                    return None
                def set_opentelemetry_log_level(level):
                    return None
                def track_model_init(*args, **kwargs):
                    return None
                def track_pipeline_init(*args, **kwargs):
                    return None
                def track_pipeline_apply(*args, **kwargs):
                    return None
                stub.set_telemetry_metrics = set_telemetry_metrics
                stub.set_opentelemetry_log_level = set_opentelemetry_log_level
                stub.track_model_init = track_model_init
                stub.track_pipeline_init = track_pipeline_init
                stub.track_pipeline_apply = track_pipeline_apply
                sys.modules[telemetry_mod_name] = stub
                sys.modules[telemetry_metrics_name] = stub
                _write_bundle_log("Inserted pyannote.telemetry stub into sys.modules")
        except Exception:
            # Best-effort only
            pass

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
