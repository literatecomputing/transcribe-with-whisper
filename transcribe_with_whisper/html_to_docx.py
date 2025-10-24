"""Shared HTML -> DOCX conversion helpers.

This module provides a single implementation used by the CLI script and the
web server. It extracts only the content inside <div class="transcript-segment">
blocks, writes one paragraph per segment and preserves speaker/timestamp text.
This avoids duplicate implementations and keeps behavior consistent across
environments (dev, frozen bundle, CI).
"""
from __future__ import annotations

import html as htmlmod
import re
from pathlib import Path


def ensure_deps() -> bool:
  try:
    import docx  # noqa: F401
    return True
  except Exception:
    return False


def sanitize_html(html: str) -> str:
  # Remove comments
  html = re.sub(r"<!--.*?-->", "", html, flags=re.S)
  # Strip scripts/styles
  html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.S | re.I)
  html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.S | re.I)
  # Unwrap anchors
  html = re.sub(r"<a[^>]*>(.*?)</a>", r"\1", html, flags=re.S | re.I)
  # Remove html-only blocks
  html = re.sub(
      r"<([a-zA-Z0-9]+)([^>]*\bclass=[\'\"]?[^>]*\bhtml-only\b[^>]*[\'\"]?[^>]*)>.*?</\1>",
      "",
      html,
      flags=re.S | re.I,
  )
  # Normalize whitespace
  html = re.sub(r"[\t\r\n]+", "\n", html)
  html = re.sub(r"[ \f\v]{2,}", " ", html)
  return html


def _strip_tags(s: str) -> str:
  t = re.sub(r"<[^>]+>", "", s)
  t = htmlmod.unescape(t)
  t = re.sub(r"[\t\r\n]+", " ", t)
  t = re.sub(r" {2,}", " ", t)
  return t.strip()


def convert_html_string_to_docx(html: str, out_path: Path) -> None:
  """Convert HTML text to a DOCX at out_path.

    Only content inside <div class="transcript-segment">...</div> is used.
    Raises RuntimeError if no transcript segments are found.
    """
  if not ensure_deps():
    raise RuntimeError("python-docx is not installed")

  html = sanitize_html(html)

  seg_pattern = re.compile(
      r"<div[^>]*\bclass=[\'\"]?[^>]*\btranscript-segment\b[^>]*[\'\"]?[^>]*>(.*?)</div>",
      flags=re.S | re.I,
  )

  segments = seg_pattern.findall(html)
  if not segments:
    raise RuntimeError('no <div class="transcript-segment"> blocks found')

  from docx import Document

  doc = Document()

  for inner in segments:
    speaker = ""
    timestamp = ""
    m = re.search(r'<span[^>]*\bclass=[\'\"]?[^>]*\bspeaker-name\b[^>]*[\'\"]?[^>]*>(.*?)</span>',
                  inner,
                  flags=re.S | re.I)
    if m:
      speaker = _strip_tags(m.group(1))

    m = re.search(r'<span[^>]*\bclass=[\'\"]?[^>]*\btimestamp\b[^>]*[\'\"]?[^>]*>(.*?)</span>',
                  inner,
                  flags=re.S | re.I)
    if m:
      timestamp = _strip_tags(m.group(1))

    m = re.search(
        r'<span[^>]*\bclass=[\'\"]?[^>]*\btranscript-text\b[^>]*[\'\"]?[^>]*>(.*?)</span>',
        inner,
        flags=re.S | re.I)
    if m:
      text = _strip_tags(m.group(1))
    else:
      text = _strip_tags(inner)

    pieces = []
    if speaker:
      pieces.append(speaker)
    if timestamp:
      pieces.append(timestamp)
    if text:
      pieces.append(text)

    paragraph_text = " ".join(pieces).strip()
    if paragraph_text:
      doc.add_paragraph(paragraph_text)

  doc.save(str(out_path))


def convert_html_file_to_docx(in_path: Path, out_path: Path) -> None:
  html = in_path.read_text(encoding="utf-8")
  return convert_html_string_to_docx(html, out_path)
