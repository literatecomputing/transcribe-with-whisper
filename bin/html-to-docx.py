#!/usr/bin/env python3
"""Pure-Python HTML -> DOCX converter.

This tool extracts only the content inside <div class="transcript-segment">...
</div> blocks from an input HTML file, converts each block into its own
paragraph in the output DOCX, and preserves any speaker labels and timestamps
that are part of those blocks.

Behavior summary:
- Only content from <div class="transcript-segment"> is included. Other
  parts of the page (headers, nav, sidebars) are ignored.
- Each transcript-segment becomes one paragraph in the DOCX.
- Speaker labels and timestamps inside the segment HTML are left intact.

Usage:
    python bin/html-to-docx.py input.html [output.docx]

Exit codes:
  0  success
  1  input file missing
  2  missing Python dependencies (install python-docx htmldocx)
  3  conversion error
"""

from __future__ import annotations
import re
import sys
from pathlib import Path


def ensure_deps() -> bool:
    try:
        import docx  # noqa: F401
        import htmldocx  # noqa: F401
        return True
    except Exception:
        return False


def sanitize_html(html: str) -> str:
    """Lightweight sanitization that keeps transcript content intact.

    - Removes HTML comments, script/style blocks and inline event handlers.
    - Removes elements with class "html-only" entirely (these are UI-only).
    - Unwraps anchors (<a>text</a> -> text) so links don't break the converter.
    - Normalizes whitespace.
    """
    # Remove HTML comments
    html = re.sub(r"<!--.*?-->", "", html, flags=re.S)

    # Remove script and style blocks completely
    html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.S | re.I)
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.S | re.I)

    # Remove inline event handlers (onclick, onload, etc.) to avoid JS leakage
    html = re.sub(r"\s(on[a-zA-Z]+)=(?:\".*?\"|'.*?'|[^\s>]+)", "", html, flags=re.S | re.I)

    # Remove tags with class html-only (remove the whole element)
    html = re.sub(
        r"<([a-zA-Z0-9]+)([^>]*\bclass=[\'\"]?[^>]*\bhtml-only\b[^>]*[\'\"]?[^>]*)>.*?</\1>",
        "",
        html,
        flags=re.S | re.I,
    )

    # Unwrap anchors but keep inner HTML
    html = re.sub(r"<a[^>]*>(.*?)</a>", r"\1", html, flags=re.S | re.I)

    # Normalize newlines/whitespace
    html = re.sub(r"[\t\r\n]+", "\n", html)
    html = re.sub(r"[ \f\v]{2,}", " ", html)

    return html


def extract_transcript_fragment(html: str) -> str:
    """Return an HTML fragment made of <p class="transcript-segment">...</p>
    for every <div ... class="... transcript-segment ...">...</div> found in the
    input. We preserve inner HTML so speaker and timestamp markup remains.
    """
    parts = []

    # Find divs with class including transcript-segment (case-insensitive)
    pattern = re.compile(
        r"<div([^>]*)\bclass=[\'\"]?([^>]*\btranscript-segment\b[^>]*)[\'\"]?([^>]*)>(.*?)</div>",
        flags=re.S | re.I,
    )

    for m in pattern.finditer(html):
        full_attrs_left = (m.group(1) or "") + " class=\"" + (m.group(2) or "") + "\"" + (m.group(3) or "")
        inner_html = m.group(4) or ""

        # Trim whitespace-only segments
        if not inner_html.strip():
            continue

        # Build a paragraph tag preserving the original attributes (minus problematic > chars)
        # Keep the class attr so downstream rules can target it.
        parts.append(f"<p{full_attrs_left}>{inner_html}</p>")

    return "\n".join(parts)


def convert(in_path: Path, out_path: Path) -> None:
    from docx import Document
    from htmldocx import HtmlToDocx

    raw = in_path.read_text(encoding="utf-8")
    html = sanitize_html(raw)

    fragment = extract_transcript_fragment(html)

    # If no transcript segments found, fail fast — caller expects transcript-only output.
    if not fragment.strip():
        raise RuntimeError("no <div class=\"transcript-segment\"> blocks found in input HTML")

    doc = Document()
    converter = HtmlToDocx()
    converter.add_html_to_document(fragment, doc)
    doc.save(str(out_path))


def main(argv: list[str]) -> int:
    if len(argv) < 2 or len(argv) > 3:
        print(f"Usage: {Path(argv[0]).name} input.html [output.docx]", file=sys.stderr)
        return 2

    in_path = Path(argv[1])
    if not in_path.exists():
        print(f"Error: input file not found: {in_path}", file=sys.stderr)
        return 1

    out_path = Path(argv[2]) if len(argv) == 3 else in_path.with_suffix(".docx")

    if not ensure_deps():
        print("Error: missing Python dependencies. Install with: pip install python-docx htmldocx", file=sys.stderr)
        return 2

    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        convert(in_path, out_path)
        print(f"Wrote: {out_path}")
        return 0
    except Exception as e:
        print(f"DOCX conversion failed: {e}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
