"""Runtime hook to set UTF-8 environment for frozen executables.

This runs very early inside the PyInstaller bootloader and is the safe place
to set environment variables like PYTHONIOENCODING and PYTHONUTF8 so that
standard library IO will prefer UTF-8 even when the console uses a legacy
code page.

It also installs a minimal excepthook that writes tracebacks to a bundle
local `bundle_run.log` so we can diagnose early import/runtime errors
when sys.stderr isn't usable (CI log capture, redirected output, etc.).
"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

# Prefer UTF-8 for text IO.
try:
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    os.environ.setdefault("PYTHONUTF8", "1")
except Exception:
    pass

# Early logging helper that writes to a log next to the executable.
def _write_bundle_log(msg: str):
    try:
        exe_dir = Path(sys.executable).resolve().parent
        log_path = exe_dir / "bundle_run.log"
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(msg + "\n")
    except Exception:
        # Best-effort only; don't raise from the hook
        pass

def _early_excepthook(exc_type, exc_value, exc_tb):
    try:
        _write_bundle_log("[RUNTIME-HOOK] Unhandled exception:")
        _write_bundle_log("".join(traceback.format_exception(exc_type, exc_value, exc_tb)))
    except Exception:
        pass

# Install the early excepthook if one is not already set.
try:
    if getattr(sys, "excepthook", None) is not None:
        sys.excepthook = _early_excepthook
except Exception:
    pass
