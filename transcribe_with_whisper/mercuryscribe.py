"""MercuryScribe CLI wrapper

Provides a friendly error if web dependencies are not installed, then runs the
packaged FastAPI app.
"""
from __future__ import annotations

import sys


def main() -> None:
  try:
    import fastapi  # noqa: F401
    import uvicorn  # noqa: F401
  except Exception as e:
    msg = ("MercuryScribe web dependencies are not installed.\n\n"
           "Install with:\n\n"
           "  pip install \"transcribe-with-whisper[web]\"\n\n"
           f"Original error: {e}")
    print(msg)
    sys.exit(1)

  # Only import server after deps are confirmed to improve error UX
  from . import server_app

  server_app.main()


if __name__ == "__main__":
  main()
