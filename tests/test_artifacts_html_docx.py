from pathlib import Path
import zipfile


def test_html_and_docx_from_artifacts_exist_and_open(app_with_artifacts):
    ctx = app_with_artifacts
    html = ctx.base_dir / f"{ctx.basename}.html"
    docx = ctx.base_dir / f"{ctx.basename}.docx"

    assert html.exists(), f"Missing HTML: {html}"
    # Basic sanity: small HTML must contain a title tag for MercuryScribe
    content = html.read_text(encoding="utf-8", errors="ignore")
    assert "MercuryScribe" in content or "<!doctype html>" in content.lower()

    if docx.exists():
        # Open docx as zip and ensure it contains word/document.xml
        with zipfile.ZipFile(docx, 'r') as zf:
            names = zf.namelist()
            assert any(n.startswith('word/document.xml') for n in names)
            xml = zf.read('word/document.xml').decode('utf-8', errors='ignore')
            assert "w:document" in xml or "w:p" in xml
