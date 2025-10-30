#!/usr/bin/env python3
"""CLI wrapper for the shared HTML->DOCX converter.

This file used to contain an independent implementation. It now delegates to
`transcribe_with_whisper.html_to_docx.convert_html_file_to_docx()` so the CLI
and the server share the same code path and behavior.

Exit codes:
  0  success
  1  input file missing
  2  missing Python dependencies (install python-docx)
  3  conversion error
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the repository root is on sys.path so `from transcribe_with_whisper.*`
# imports work when this script is executed directly (e.g. ``python bin/html-to-docx.py``).
# When Python runs a script, sys.path[0] is the script directory (bin/), which
# prevents imports like `transcribe_with_whisper` from resolving to the repo
# package. Prepending the repo root makes local package imports robust.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main(argv: list[str]) -> int:
    if len(argv) < 2 or len(argv) > 3:
        print(f"Usage: {Path(argv[0]).name} input.html [output.docx]", file=sys.stderr)
        return 2

    in_path = Path(argv[1])
    if not in_path.exists():
        print(f"Error: input file not found: {in_path}", file=sys.stderr)
        return 1

    out_path = Path(argv[2]) if len(argv) == 3 else in_path.with_suffix(".docx")

    try:
        # Import the shared converter. This will raise ImportError if python-docx
        # (or the shared module) is not available, which we treat as a deps error.
        from transcribe_with_whisper.html_to_docx import ensure_deps, convert_html_file_to_docx
    except Exception as e:  # broad except to catch ImportError and other import-time failures
        print("Error: missing Python dependencies. Install with: pip install python-docx", file=sys.stderr)
        print(f"(import error: {e})", file=sys.stderr)
        return 2

    if not ensure_deps():
        print("Error: missing Python dependencies. Install with: pip install python-docx", file=sys.stderr)
        return 2

    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        convert_html_file_to_docx(in_path, out_path)
        print(f"Wrote: {out_path}")
        return 0
    except Exception as e:
        print(f"DOCX conversion failed: {e}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    # Import sys here to guard against accidental removal or reordering of the
    # top-level import during edits/formatting. Importing locally keeps this
    # invocation robust and avoids NameError if the global `sys` is not present.
    import sys

    raise SystemExit(main(sys.argv))
