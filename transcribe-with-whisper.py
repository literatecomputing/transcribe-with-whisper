#!/usr/bin/env python3
"""Compatibility wrapper for the `transcribe-with-whisper` CLI.

This script historically contained a standalone implementation of the
transcription pipeline and HTML generation. It now delegates to the
maintained package entry point in `transcribe_with_whisper.main` so that
there is only one source of truth for the HTML output.
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> None:
    """Forward execution to the modern CLI implementation."""

    from transcribe_with_whisper.main import main as cli_main

    if argv is None:
        cli_main()
        return

    original_argv = sys.argv
    sys.argv = [original_argv[0]] + argv
    try:
        cli_main()
    finally:
        sys.argv = original_argv


if __name__ == "__main__":  # pragma: no cover - thin wrapper
    main(sys.argv[1:])

print(f"Script completed successfully! Output: {outputHtml}")
