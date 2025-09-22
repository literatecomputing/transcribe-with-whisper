import os
import sys
import shutil
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Iterable

from fastapi import FastAPI, File, UploadFile, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from huggingface_hub import HfApi


APP_DIR = Path(__file__).resolve().parent
# Preferred env var TRANSCRIPTION_DIR; fall back to legacy UPLOAD_DIR; default to transcription-files
TRANSCRIPTION_DIR = Path(
  os.getenv(
    "TRANSCRIPTION_DIR",
    os.getenv("UPLOAD_DIR", str(APP_DIR / "transcription-files")),
  )
)
TRANSCRIPTION_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Transcribe with Whisper (Web)")
app.mount("/files", StaticFiles(directory=str(TRANSCRIPTION_DIR)), name="files")


INDEX_HTML = """
<!doctype html>
<html>
  <head>
    <meta charset=\"utf-8\">
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
    <title>Transcribe with Whisper</title>
    <style>
      body { font-family: system-ui, sans-serif; max-width: 800px; margin: 2rem auto; padding: 0 1rem; }
      .card { background: #fff; border-radius: 8px; padding: 1rem 1.25rem; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
      h1 { margin: 0 0 1rem; }
      form { display: grid; gap: 0.75rem; }
      input[type=file] { padding: 0.75rem; border: 1px solid #ddd; border-radius: 6px; }
      .row { display: flex; gap: 0.5rem; align-items: center; }
      .row input[type=text] { flex: 1; padding: 0.6rem; border: 1px solid #ddd; border-radius: 6px; }
      button { background: #0d6efd; color: white; border: 0; padding: 0.6rem 1rem; border-radius: 6px; cursor: pointer; }
      button:disabled { opacity: .6; cursor: progress; }
      .tip { color: #555; font-size: .95rem; }
      code { background: #f6f8fa; padding: .1rem .3rem; border-radius: 4px; }
    </style>
  </head>
  <body>
    <div class=\"card\">
      <h1>Transcribe with Whisper</h1>
      <p class=\"tip\">Upload a video/audio file. The server will run diarization and transcription, then return an interactive HTML transcript.</p>
      <p class=\"tip\">Manage or edit files in <code>./transcription-files</code> or use the list view: <a href=\"/list\">Browse transcription-files</a>.</p>
      <p class=\"tip\">You can edit the <code>html</code> or <code>vtt</code> files in the transcription-files directory.</p>
      <p class=\"tip\">See <a href='https://github.com/literatecomputing/transcribe-with-whisper'>the GitHub repo</a> for more information.</p>
      <form action=\"/upload\" method=\"post\" enctype=\"multipart/form-data\" onsubmit=\"document.getElementById('submit').disabled = true; document.getElementById('submit').innerText='Processing…';\">
        <input type=\"file\" name=\"file\" accept=\"video/*,audio/*\" required>
        <details>
          <summary>Optional: Speaker names</summary>
          <div class=\"row\"><input type=\"text\" name=\"speaker\" placeholder=\"Speaker 1\"></div>
          <div class=\"row\"><input type=\"text\" name=\"speaker\" placeholder=\"Speaker 2\"></div>
          <div class=\"row\"><input type=\"text\" name=\"speaker\" placeholder=\"Speaker 3\"></div>
          <div class=\"row\"><input type=\"text\" name=\"speaker\" placeholder=\"Speaker 4\"></div>
        </details>
        <button id=\"submit\" type=\"submit\">Transcribe</button>
      </form>
    </div>
  </body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def index(_: Request):
    return HTMLResponse(INDEX_HTML)


def _build_cli_cmd(filename: str, speakers: list[str] | None = None) -> list[str]:
  # Use the Python module entrypoint to avoid reliance on console_scripts in PATH
  cmd: list[str] = [sys.executable, "-m", "transcribe_with_whisper.main", filename]
  if speakers:
    cmd.extend(speakers)
  return cmd


def _subprocess_env_with_repo_path() -> dict:
  # Ensure the repo root is on PYTHONPATH so transcribe_with_whisper can be imported
  repo_root = str(APP_DIR)
  env = dict(os.environ)
  existing = env.get("PYTHONPATH", "")
  if existing:
    env["PYTHONPATH"] = f"{repo_root}:{existing}"
  else:
    env["PYTHONPATH"] = repo_root
  return env


def _validate_hf_token_or_die() -> None:
  token = os.getenv("HUGGING_FACE_AUTH_TOKEN")
  if not token:
    # Fail fast with a clear message
    raise RuntimeError(
      "HUGGING_FACE_AUTH_TOKEN is not set. Set it before starting the server."
    )
  try:
    api = HfApi()
    # Validate we can access the diarization and segmentation models
    api.model_info("pyannote/speaker-diarization", token=token)
    api.model_info("pyannote/segmentation-3.0", token=token)
    print("✅ Hugging Face token validated (speaker-diarization and segmentation-3.0 accessible).")
  except Exception as e:
    raise RuntimeError(
      "Hugging Face token validation failed. Ensure the token is valid and has access to "
      "'pyannote/speaker-diarization' and 'pyannote/segmentation-3.0'. Original error: " + str(e)
    )


@app.on_event("startup")
def startup_check_token():
  # Allow bypass for local dev if needed: SKIP_HF_STARTUP_CHECK=1
  if os.getenv("SKIP_HF_STARTUP_CHECK") == "1":
    print("⚠️  Skipping HF token startup check due to SKIP_HF_STARTUP_CHECK=1.")
    return
  _validate_hf_token_or_die()


@app.post("/upload")
async def upload(file: UploadFile = File(...), speaker: list[str] | None = Form(default=None)):
  # Ensure HF token is provided
  if not os.getenv("HUGGING_FACE_AUTH_TOKEN"):
      return PlainTextResponse(
          "HUGGING_FACE_AUTH_TOKEN not set. Set it when running the container.", status_code=500
      )

  # Persist upload
  dest_path = TRANSCRIPTION_DIR / file.filename
  with dest_path.open("wb") as out:
    shutil.copyfileobj(file.file, out)

  # Build CLI command; pass speaker names if provided
  # Build command using Python module to avoid PATH issues
  speakers = [s.strip() for s in (speaker or []) if s and s.strip()]
  cmd = _build_cli_cmd(file.filename, speakers or None)

  # Run the CLI synchronously; the CLI writes ../<basename>.html relative to its work dir
  try:
    proc = subprocess.run(
      cmd,
      cwd=str(TRANSCRIPTION_DIR),
      env=_subprocess_env_with_repo_path(),
      capture_output=True,
      text=True,
      check=False,
    )
  except Exception as e:
    return PlainTextResponse(f"Failed to run CLI: {e}", status_code=500)

  if proc.returncode != 0:
    return PlainTextResponse(
      f"CLI failed with code {proc.returncode}\nSTDOUT:\n{proc.stdout}\n\nSTDERR:\n{proc.stderr}",
      status_code=500,
    )

  # Determine output HTML path; the CLI writes <basename>.html in the working directory
  basename = Path(file.filename).stem
  html_out = TRANSCRIPTION_DIR / f"{basename}.html"
  if not html_out.exists():
    # Fallback: scan for any html created recently
    candidates = sorted(TRANSCRIPTION_DIR.glob("*.html"), key=lambda p: p.stat().st_mtime, reverse=True)
    if candidates:
      html_out = candidates[0]
    else:
      return PlainTextResponse("Transcription finished but no HTML output found.", status_code=500)

  # Redirect to served HTML
  rel_url = f"/files/{html_out.name}"
  return RedirectResponse(url=rel_url, status_code=303)


def _human_size(n: int) -> str:
  # Simple human-readable size formatter
  for unit in ["B", "KB", "MB", "GB", "TB"]:
    if n < 1024:
      return f"{n:.0f} {unit}"
    n /= 1024
  return f"{n:.0f} PB"


def _list_dir_entries(path: Path) -> Iterable[Path]:
  return sorted([p for p in path.iterdir() if p.is_file()], key=lambda p: p.name.lower())


@app.get("/list", response_class=HTMLResponse)
async def list_files(_: Request):
  files = _list_dir_entries(TRANSCRIPTION_DIR)
  rows = []
  for p in files:
    name = p.name
    size = _human_size(p.stat().st_size)
    mtime = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    actions = []
    # View if HTML
    if p.suffix.lower() == ".html":
      actions.append(f'<a href="/files/{name}">View</a>')
    # Re-run if media input
    if p.suffix.lower() in {".mp4", ".m4a", ".wav", ".mp3", ".mkv", ".mov"}:
      actions.append(
        f'<form method="post" action="/rerun" style="display:inline">'
        f'<input type="hidden" name="filename" value="{name}">' \
        f'<button type="submit">Re-run</button></form>'
      )
    # Always allow direct download
    actions.append(f'<a href="/files/{name}" download>Download</a>')
    rows.append(f"<tr><td>{name}</td><td style='text-align:right'>{size}</td><td>{mtime}</td><td>{' | '.join(actions)}</td></tr>")

  html = f"""
<!doctype html>
<html>
  <head>
  <meta charset='utf-8'>
  <meta name='viewport' content='width=device-width, initial-scale=1'>
  <title>Transcription files</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ padding: .5rem; border-bottom: 1px solid #eee; }}
    th {{ text-align: left; }}
  </style>
  </head>
  <body>
  <h1>Transcription files</h1>
  <p><a href='/'>⬅ Upload another file</a></p>
  <table>
    <thead><tr><th>File</th><th style='text-align:right'>Size</th><th>Modified</th><th>Actions</th></tr></thead>
    <tbody>
    {''.join(rows)}
    </tbody>
  </table>
  </body>
</html>
"""
  return HTMLResponse(html)


@app.post("/rerun")
async def rerun(filename: str = Form(...)):
  # Validate target file is in the directory
  target = (TRANSCRIPTION_DIR / filename).resolve()
  if not target.exists() or target.parent != TRANSCRIPTION_DIR.resolve():
    return PlainTextResponse("Invalid file.", status_code=400)

  if target.suffix.lower() not in {".mp4", ".m4a", ".wav", ".mp3", ".mkv", ".mov"}:
    return PlainTextResponse("Re-run is only supported for media files.", status_code=400)

  cmd = _build_cli_cmd(target.name)
  try:
    proc = subprocess.run(
      cmd,
      cwd=str(TRANSCRIPTION_DIR),
      env=_subprocess_env_with_repo_path(),
      capture_output=True,
      text=True,
      check=False,
    )
  except Exception as e:
    return PlainTextResponse(f"Failed to run CLI: {e}", status_code=500)

  if proc.returncode != 0:
    return PlainTextResponse(
      f"CLI failed with code {proc.returncode}\nSTDOUT:\n{proc.stdout}\n\nSTDERR:\n{proc.stderr}",
      status_code=500,
    )

  basename = target.stem
  html_out = TRANSCRIPTION_DIR / f"{basename}.html"
  if not html_out.exists():
    return PlainTextResponse("Finished but no HTML output found.", status_code=500)
  return RedirectResponse(url=f"/files/{html_out.name}", status_code=303)
