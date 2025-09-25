import os
import sys
import shutil
import subprocess
import threading
import time
import json
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

# Simple in-memory job tracking
jobs = {}  # job_id -> {"status": "running|completed|error", "progress": 0-100, "message": "...", "result": "..."}
job_counter = 0


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


@app.get("/progress/{job_id}", response_class=HTMLResponse)
async def progress_page(job_id: str):
    if job_id not in jobs:
        return PlainTextResponse("Job not found", status_code=404)
    
    job = jobs[job_id]
    return HTMLResponse(f"""
<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Transcription Progress</title>
    <style>
      body {{ font-family: system-ui, sans-serif; max-width: 800px; margin: 2rem auto; padding: 0 1rem; }}
      .card {{ background: #fff; border-radius: 8px; padding: 1rem 1.25rem; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
      .progress-bar {{ width: 100%; height: 20px; background: #f0f0f0; border-radius: 10px; overflow: hidden; margin: 1rem 0; }}
      .progress-fill {{ height: 100%; background: #0d6efd; transition: width 0.5s ease; }}
      .spinner {{ display: inline-block; width: 20px; height: 20px; border: 3px solid #f3f3f3; border-top: 3px solid #0d6efd; border-radius: 50%; animation: spin 2s linear infinite; }}
      @keyframes spin {{ 0% {{ transform: rotate(0deg); }} 100% {{ transform: rotate(360deg); }} }}
      .status {{ margin: 1rem 0; }}
      .error {{ color: #dc3545; }}
      .success {{ color: #28a745; }}
    </style>
    <script>
      function updateProgress() {{
        fetch('/api/job/{job_id}')
          .then(response => response.json())
          .then(data => {{
            document.getElementById('progress-fill').style.width = data.progress + '%';
            document.getElementById('progress-text').innerText = data.progress + '%';
            document.getElementById('status-message').innerText = data.message;
            
            if (data.status === 'completed' && data.result) {{
              // Hide spinner and update status
              document.querySelector('.spinner').style.display = 'none';
              document.getElementById('status-container').innerHTML = 
                '<div class="success">✅ Transcription completed! <a href="' + data.result + '">View result</a></div>' +
                '<p><a href="/list">View all files</a> | <a href="/">Upload another file</a></p>';
            }} else if (data.status === 'error') {{
              // Hide spinner and show error
              document.querySelector('.spinner').style.display = 'none';
              document.getElementById('status-container').innerHTML = 
                '<div class="error">❌ Error: ' + data.message + '</div>' +
                '<p><a href="/">Try again</a></p>';
            }} else {{
              setTimeout(updateProgress, 2000); // Check again in 2 seconds
            }}
          }})
          .catch(error => {{
            console.error('Error:', error);
            setTimeout(updateProgress, 5000);
          }});
      }}
      
      // Start checking progress when page loads
      window.onload = function() {{
        updateProgress();
      }};
    </script>
  </head>
  <body>
    <div class="card">
      <h1>Transcribing: {job['filename']}</h1>
      <div class="progress-bar">
        <div id="progress-fill" class="progress-fill" style="width: {job['progress']}%"></div>
      </div>
      <div class="status">
        <span class="spinner"></span> 
        <span id="progress-text">{job['progress']}%</span> - 
        <span id="status-message">{job['message']}</span>
      </div>
      <div id="status-container"></div>
      <p><small>This page will automatically update. Please don't close your browser.</small></p>
    </div>
  </body>
</html>
""")


@app.get("/api/job/{job_id}")
async def get_job_status(job_id: str):
    if job_id not in jobs:
        return {"error": "Job not found"}, 404
    return jobs[job_id]


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


def _run_transcription_job(job_id: str, filename: str, speakers: list[str] | None):
  """Run transcription in background thread"""
  global jobs
  
  try:
    jobs[job_id]["status"] = "running"
    jobs[job_id]["message"] = "Starting transcription..."
    jobs[job_id]["progress"] = 5
    
    # Build CLI command
    cmd = _build_cli_cmd(filename, speakers or None)
    
    jobs[job_id]["message"] = "Processing audio and running AI models..."
    jobs[job_id]["progress"] = 20
    
    # Run the CLI
    proc = subprocess.run(
      cmd,
      cwd=str(TRANSCRIPTION_DIR),
      env=_subprocess_env_with_repo_path(),
      capture_output=True,
      text=True,
      check=False,
    )
    
    jobs[job_id]["progress"] = 80
    
    if proc.returncode != 0:
      jobs[job_id]["status"] = "error"
      jobs[job_id]["message"] = f"CLI failed with code {proc.returncode}"
      jobs[job_id]["error"] = f"STDOUT:\n{proc.stdout}\n\nSTDERR:\n{proc.stderr}"
      return

    # Find output HTML
    basename = Path(filename).stem
    html_out = TRANSCRIPTION_DIR / f"{basename}.html"
    if not html_out.exists():
      candidates = sorted(TRANSCRIPTION_DIR.glob("*.html"), key=lambda p: p.stat().st_mtime, reverse=True)
      if candidates:
        html_out = candidates[0]
      else:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["message"] = "No HTML output found"
        return

    jobs[job_id]["message"] = "Generating DOCX file..."
    jobs[job_id]["progress"] = 90

    # Generate DOCX file automatically
    try:
      docx_out = html_out.with_suffix('.docx')
      html_to_docx_script = APP_DIR / "bin" / "html-to-docx.sh"
      
      if html_to_docx_script.exists():
        subprocess.run([
          str(html_to_docx_script), 
          str(html_out), 
          str(docx_out)
        ], check=True, capture_output=True, text=True)
        print(f"✅ Generated DOCX: {docx_out.name}")
      else:
        print("⚠️ html-to-docx.sh script not found, skipping DOCX generation")
    except Exception as e:
      print(f"⚠️ DOCX generation failed: {e}")
      # Don't fail the job if DOCX generation fails

    jobs[job_id]["status"] = "completed"
    jobs[job_id]["progress"] = 100
    jobs[job_id]["message"] = "Transcription completed!"
    jobs[job_id]["result"] = f"/files/{html_out.name}"
    
  except Exception as e:
    jobs[job_id]["status"] = "error"
    jobs[job_id]["message"] = f"Failed to run transcription: {e}"


@app.post("/upload")
async def upload(file: UploadFile = File(...), speaker: list[str] | None = Form(default=None)):
  global job_counter, jobs
  
  # Ensure HF token is provided
  if not os.getenv("HUGGING_FACE_AUTH_TOKEN"):
      return PlainTextResponse(
          "HUGGING_FACE_AUTH_TOKEN not set. Set it when running the container.", status_code=500
      )

  # Persist upload
  dest_path = TRANSCRIPTION_DIR / file.filename
  with dest_path.open("wb") as out:
    shutil.copyfileobj(file.file, out)

  # Create job and start background processing
  job_counter += 1
  job_id = str(job_counter)
  speakers = [s.strip() for s in (speaker or []) if s and s.strip()]
  
  jobs[job_id] = {
    "status": "starting",
    "progress": 0,
    "message": "Preparing transcription...",
    "filename": file.filename
  }
  
  # Start background thread
  thread = threading.Thread(target=_run_transcription_job, args=(job_id, file.filename, speakers))
  thread.daemon = True
  thread.start()
  
  # Redirect to progress page
  return RedirectResponse(url=f"/progress/{job_id}", status_code=303)


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
    # Highlight DOCX files
    if p.suffix.lower() == ".docx":
      actions.append(f'<a href="/files/{name}" download><strong>📄 Download DOCX</strong></a>')
    else:
      # Always allow direct download for other files
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
  global job_counter, jobs
  
  # Validate target file is in the directory
  target = (TRANSCRIPTION_DIR / filename).resolve()
  if not target.exists() or target.parent != TRANSCRIPTION_DIR.resolve():
    return PlainTextResponse("Invalid file.", status_code=400)

  if target.suffix.lower() not in {".mp4", ".m4a", ".wav", ".mp3", ".mkv", ".mov"}:
    return PlainTextResponse("Re-run is only supported for media files.", status_code=400)

  # Create job and start background processing
  job_counter += 1
  job_id = str(job_counter)
  
  jobs[job_id] = {
    "status": "starting",
    "progress": 0,
    "message": "Preparing transcription...",
    "filename": filename
  }
  
  # Start background thread
  thread = threading.Thread(target=_run_transcription_job, args=(job_id, target.name, None))
  thread.daemon = True
  thread.start()
  
  # Redirect to progress page
  return RedirectResponse(url=f"/progress/{job_id}", status_code=303)
