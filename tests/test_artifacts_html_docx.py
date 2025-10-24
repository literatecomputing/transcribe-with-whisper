import os
import re
import zipfile
from pathlib import Path

os.environ.setdefault("SKIP_PREFLIGHT_CHECKS", "1")
os.environ.setdefault("SKIP_HF_STARTUP_CHECK", "1")

from transcribe_with_whisper.main import generate_html, get_package_version


def _extract_generator_meta(content: str) -> str:
    match = re.search(r'<meta\s+name="generator"\s+content="([^"]+)"\s*/?>', content)
    assert match, "Missing generator meta tag"
    return match.group(1)


def test_html_and_docx_from_artifacts_exist_and_open(app_with_artifacts):
    ctx = app_with_artifacts
    html = ctx.base_dir / f"{ctx.basename}.html"
    docx = ctx.base_dir / f"{ctx.basename}.docx"

    assert html.exists(), f"Missing HTML: {html}"
    # Basic sanity: small HTML must contain a title tag for MercuryScribe
    content = html.read_text(encoding="utf-8", errors="ignore")
    assert "MercuryScribe" in content or "<!doctype html>" in content.lower()

    generator_value = _extract_generator_meta(content)
    assert generator_value == f"transcribe-with-whisper {get_package_version()}"

    if docx.exists():
        # Open docx as zip and ensure it contains word/document.xml
        with zipfile.ZipFile(docx, 'r') as zf:
            names = zf.namelist()
            assert any(n.startswith('word/document.xml') for n in names)
            xml = zf.read('word/document.xml').decode('utf-8', errors='ignore')
            assert "w:document" in xml or "w:p" in xml


def test_cli_generator_meta_tag(tmp_path: Path):
    html_path = tmp_path / "sample.html"
    generate_html(
        html_path,
        groups=[],
        vtt_files=[],
        inputfile="sample.mp4",
        speakers={},
        called_by_mercuryweb=False,
    )

    html = html_path.read_text(encoding="utf-8")
    generator_value = _extract_generator_meta(html)
    assert generator_value == f"transcribe-with-whisper {get_package_version()}"
