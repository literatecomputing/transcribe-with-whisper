import os
import sys
import shutil
import subprocess
import threading
import time
import json
import re
from pathlib import Path
from datetime import datetime
from typing import Iterable

from fastapi import FastAPI, File, UploadFile, Request, Form
import webvtt
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
      # Check if VTT directory exists for editing
      basename = p.stem
      vtt_dir = TRANSCRIPTION_DIR / basename
      if vtt_dir.exists() and any(vtt_dir.glob("*.vtt")):
        actions.append(f'<a href="/edit/{name}" style="color: #007bff;">✏️ Edit</a>')
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


@app.post("/update-speakers")
async def update_speakers(request: Request):
  """Update speaker names in the configuration file"""
  try:
    data = await request.json()
    filename = data.get('filename')
    speakers_mapping = data.get('speakers')
    
    if not filename or not speakers_mapping:
      return {"success": False, "message": "Missing filename or speakers data"}
    
    # Import the speaker config functions
    import sys
    import os
    import json
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    
    # The config file is in the video's working directory
    working_dir = TRANSCRIPTION_DIR / filename
    config_path = working_dir / f"{filename}-speakers.json"
    
    # Load existing config from the working directory
    speakers = None
    if config_path.exists():
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            # Convert to the format expected by generate_html
            speakers = {}
            for speaker_id, info in config.items():
                if isinstance(info, dict):
                    speakers[speaker_id] = (info.get('name', speaker_id), 
                                          info.get('bgcolor', 'lightgray'), 
                                          info.get('textcolor', 'darkorange'))
                else:
                    # Legacy format - just the name
                    speakers[speaker_id] = (info, 'lightgray', 'darkorange')
        except (json.JSONDecodeError, KeyError) as e:
            return {"success": False, "message": f"Could not load speaker config {config_path}: {e}"}
    
    if speakers is None:
      return {"success": False, "message": f"Speaker config file not found: {config_path}"}
    
    # Update speaker names based on mapping
    updated_speakers = {}
    for speaker_id, (current_name, bgcolor, textcolor) in speakers.items():
      # Check if this speaker name should be updated
      new_name = speakers_mapping.get(current_name, current_name)
      updated_speakers[speaker_id] = (new_name, bgcolor, textcolor)
    
    # Save updated config to the working directory
    updated_config = {}
    for speaker_id, (name, bgcolor, textcolor) in updated_speakers.items():
        updated_config[speaker_id] = {
            'name': name,
            'bgcolor': bgcolor,
            'textcolor': textcolor
        }
    
    try:
        with open(config_path, 'w') as f:
            json.dump(updated_config, f, indent=2)
    except Exception as e:
        return {"success": False, "message": f"Could not save speaker config {config_path}: {e}"}
    
    return {"success": True, "message": f"Updated speaker config: {config_path}"}
    
  except Exception as e:
    return {"success": False, "message": f"Error updating speakers: {str(e)}"}


@app.get("/edit/{filename}", response_class=HTMLResponse)
async def edit_transcript(filename: str):
    """Serve the ProseMirror-based transcript editor"""
    
    # Validate the HTML file exists
    html_path = TRANSCRIPTION_DIR / filename
    if not html_path.exists() or html_path.suffix.lower() != ".html":
        return PlainTextResponse("HTML file not found", status_code=404)
    
    # Find the corresponding VTT directory
    basename = html_path.stem
    vtt_dir = TRANSCRIPTION_DIR / basename
    
    if not vtt_dir.exists():
        return PlainTextResponse("No editable transcript data found", status_code=404)
    
    # Load transcript data from VTT files
    transcript_data = _load_transcript_data(basename)
    
    editor_html = f"""
<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Edit Transcript: {basename}</title>
    
    <!-- ProseMirror CSS -->
    <link rel="stylesheet" href="https://unpkg.com/prosemirror-view@1.32.7/style/prosemirror.css">
    <link rel="stylesheet" href="https://unpkg.com/prosemirror-menu@1.2.4/style/menu.css">
    
    <style>
      body {{ 
        font-family: system-ui, sans-serif; 
        max-width: 1200px; 
        margin: 2rem auto; 
        padding: 0 1rem;
        background: #f8f9fa;
      }}
      
      .editor-container {{ 
        background: white; 
        border-radius: 8px; 
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        overflow: hidden;
      }}
      
      .editor-header {{
        background: #343a40;
        color: white;
        padding: 1rem 1.5rem;
        display: flex;
        justify-content: space-between;
        align-items: center;
      }}
      
      .editor-header h1 {{
        margin: 0;
        font-size: 1.25rem;
      }}
      
      .editor-actions {{
        display: flex;
        gap: 0.5rem;
      }}
      
      .btn {{
        padding: 0.5rem 1rem;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        font-size: 0.875rem;
        text-decoration: none;
        display: inline-block;
      }}
      
      .btn-primary {{
        background: #007bff;
        color: white;
      }}
      
      .btn-secondary {{
        background: #6c757d;
        color: white;
      }}
      
      .btn:hover {{
        opacity: 0.9;
      }}
      
      .prosemirror-editor {{
        padding: 1.5rem;
        min-height: 500px;
      }}
      
      .ProseMirror {{
        outline: none;
        line-height: 1.6;
        font-size: 16px;
      }}
      
      .transcript-segment {{
        margin: 1rem 0;
        padding: 1rem;
        border-left: 4px solid #007bff;
        background: #f8f9fa;
        border-radius: 4px;
      }}
      
      .segment-header {{
        display: flex;
        justify-content: space-between;
        margin-bottom: 0.5rem;
        font-size: 0.875rem;
        color: #6c757d;
      }}
      
      .speaker-name {{
        font-weight: bold;
        color: #007bff;
      }}
      
      .timestamp {{
        font-family: monospace;
      }}
      
      .segment-text {{
        color: #333;
      }}
      
      .save-status {{
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 0.5rem 1rem;
        border-radius: 4px;
        display: none;
      }}
      
      .save-success {{
        background: #d4edda;
        color: #155724;
        border: 1px solid #c3e6cb;
      }}
      
      .save-error {{
        background: #f8d7da;
        color: #721c24;
        border: 1px solid #f5c6cb;
      }}
    </style>
  </head>
  <body>
    <div class="editor-container">
      <div class="editor-header">
        <h1>Edit Transcript: {basename}</h1>
        <div class="editor-actions">
          <button class="btn btn-primary" onclick="saveTranscript()">Save Changes</button>
          <a href="/files/{filename}" class="btn btn-secondary">View HTML</a>
          <a href="/list" class="btn btn-secondary">Back to List</a>
        </div>
      </div>
      
      <div class="prosemirror-editor">
        <div id="editor"></div>
      </div>
    </div>
    
    <div id="save-status" class="save-status"></div>
    
    <!-- ProseMirror JavaScript -->
    <script src="https://unpkg.com/prosemirror-state@1.4.3/dist/index.js"></script>
    <script src="https://unpkg.com/prosemirror-view@1.32.7/dist/index.js"></script>
    <script src="https://unpkg.com/prosemirror-model@1.21.0/dist/index.js"></script>
    <script src="https://unpkg.com/prosemirror-schema-basic@1.2.2/dist/index.js"></script>
    <script src="https://unpkg.com/prosemirror-keymap@1.2.2/dist/index.js"></script>
    <script src="https://unpkg.com/prosemirror-history@1.3.2/dist/index.js"></script>
    <script src="https://unpkg.com/prosemirror-commands@1.5.2/dist/index.js"></script>
    
    <script>
      // Transcript data loaded from server
      const transcriptData = {json.dumps(transcript_data)};
      
      // Create ProseMirror schema with custom nodes for transcript segments
      const {{ Schema, DOMParser, DOMSerializer }} = ProseMirror.model;
      const {{ EditorState }} = ProseMirror.state;
      const {{ EditorView }} = ProseMirror.view;
      const {{ schema }} = ProseMirror.schemaBasic;
      const {{ keymap }} = ProseMirror.keymap;
      const {{ history, undo, redo }} = ProseMirror.history;
      const {{ baseKeymap }} = ProseMirror.commands;
      
      // Custom schema that includes transcript segments
      const transcriptSchema = new Schema({{
        nodes: schema.spec.nodes.update("transcript_segment", {{
          content: "block+",
          group: "block",
          attrs: {{
            speaker: {{ default: "" }},
            startTime: {{ default: "" }},
            endTime: {{ default: "" }},
            segmentId: {{ default: "" }}
          }},
          toDOM(node) {{
            return ["div", {{
              class: "transcript-segment",
              "data-segment-id": node.attrs.segmentId,
              "data-speaker": node.attrs.speaker,
              "data-start-time": node.attrs.startTime,
              "data-end-time": node.attrs.endTime
            }}, [
              "div", {{ class: "segment-header" }}, [
                "span", {{ class: "speaker-name" }}, node.attrs.speaker
              ],
              ["span", {{ class: "timestamp" }}, `${{node.attrs.startTime}} → ${{node.attrs.endTime}}`]
            ], ["div", {{ class: "segment-text" }}, 0]];
          }},
          parseDOM: [{{
            tag: "div.transcript-segment",
            getAttrs(dom) {{
              return {{
                speaker: dom.getAttribute("data-speaker") || "",
                startTime: dom.getAttribute("data-start-time") || "",
                endTime: dom.getAttribute("data-end-time") || "",
                segmentId: dom.getAttribute("data-segment-id") || ""
              }};
            }}
          }}]
        }}),
        marks: schema.spec.marks
      }});
      
      // Create initial document from transcript data
      function createInitialDoc() {{
        const segments = transcriptData.segments || [];
        const content = segments.map((segment, index) => {{
          return transcriptSchema.nodes.transcript_segment.create({{
            speaker: segment.speaker,
            startTime: segment.start_time,
            endTime: segment.end_time,
            segmentId: `segment-${{index}}`
          }}, [
            transcriptSchema.nodes.paragraph.create({{}}, [
              transcriptSchema.text(segment.text)
            ])
          ]);
        }});
        
        return transcriptSchema.nodes.doc.create({{}}, content);
      }}
      
      // Initialize the editor
      const state = EditorState.create({{
        doc: createInitialDoc(),
        plugins: [
          history(),
          keymap({{ "Mod-z": undo, "Mod-y": redo, "Mod-Shift-z": redo }}),
          keymap(baseKeymap)
        ]
      }});
      
      const view = new EditorView(document.querySelector("#editor"), {{
        state,
        dispatchTransaction(transaction) {{
          view.updateState(view.state.apply(transaction));
        }}
      }});
      
      // Save transcript function
      async function saveTranscript() {{
        const doc = view.state.doc;
        const segments = [];
        
        doc.forEach((node) => {{
          if (node.type.name === "transcript_segment") {{
            let text = "";
            node.forEach((child) => {{
              if (child.isText) text += child.text;
              else if (child.content) {{
                child.content.forEach((grandchild) => {{
                  if (grandchild.isText) text += grandchild.text;
                }});
              }}
            }});
            
            segments.push({{
              speaker: node.attrs.speaker,
              start_time: node.attrs.startTime,
              end_time: node.attrs.endTime,
              text: text.trim()
            }});
          }}
        }});
        
        try {{
          const response = await fetch(`/api/save-transcript/{basename}`, {{
            method: 'POST',
            headers: {{
              'Content-Type': 'application/json',
            }},
            body: JSON.stringify({{ segments }})
          }});
          
          const result = await response.json();
          
          if (response.ok) {{
            showStatus('Changes saved successfully!', 'success');
            // Optionally redirect to view the updated file
            setTimeout(() => {{
              window.location.href = `/files/{filename}`;
            }}, 1500);
          }} else {{
            showStatus(`Error saving: ${{result.error}}`, 'error');
          }}
        }} catch (error) {{
          showStatus(`Network error: ${{error.message}}`, 'error');
        }}
      }}
      
      function showStatus(message, type) {{
        const statusEl = document.getElementById('save-status');
        statusEl.textContent = message;
        statusEl.className = `save-status save-${{type}}`;
        statusEl.style.display = 'block';
        
        setTimeout(() => {{
          statusEl.style.display = 'none';
        }}, 3000);
      }}
    </script>
  </body>
</html>
"""
    
    return HTMLResponse(editor_html)


def _load_transcript_data(basename: str):
    """Load transcript data from VTT files for editing"""
    vtt_dir = TRANSCRIPTION_DIR / basename
    segments = []
    
    if not vtt_dir.exists():
        return {"segments": segments}
    
    # Find VTT files in the directory
    vtt_files = sorted(vtt_dir.glob("*.vtt"))
    
    for vtt_file in vtt_files:
        try:
            captions = webvtt.read(str(vtt_file))
            speaker_match = re.search(r"(\d+)\.vtt", vtt_file.name)
            speaker_id = speaker_match.group(1) if speaker_match else "Unknown"
            speaker_name = f"Speaker {int(speaker_id) + 1}" if speaker_id.isdigit() else speaker_id
            
            for caption in captions:
                segments.append({
                    "speaker": speaker_name,
                    "start_time": caption.start,
                    "end_time": caption.end,
                    "text": caption.text
                })
        except Exception as e:
            print(f"Error reading VTT file {vtt_file}: {e}")
    
    # Sort segments by start time
    segments.sort(key=lambda x: x["start_time"])
    
    return {"segments": segments}


@app.post("/save_transcript_edits/{basename}")
async def save_in_place_transcript_edits(basename: str, request: Request):
    """Save in-place edited transcript changes back to VTT files"""
    
    try:
        data = await request.json()
        changes = data.get("changes", [])
        
        if not changes:
            return {"success": False, "error": "No changes provided"}
        
        # Read existing VTT files
        vtt_dir = TRANSCRIPTION_DIR / basename
        if not vtt_dir.exists():
            return {"success": False, "error": f"Transcript directory not found: {basename}"}
        
        vtt_files = list(vtt_dir.glob("*.vtt"))
        if not vtt_files:
            return {"success": False, "error": "No VTT files found"}
        
        # Apply changes to VTT files
        for vtt_file in vtt_files:
            captions = webvtt.read(str(vtt_file))
            modified = False
            
            print(f"Processing VTT file: {vtt_file}")
            print(f"Number of changes to apply: {len(changes)}")
            
            # Apply each change
            for change_idx, change in enumerate(changes):
                start_time_seconds = float(change["start"])  # This is in decimal seconds
                new_text = change["text"]
                
                # Convert decimal seconds to WebVTT time format for comparison
                hours = int(start_time_seconds // 3600)
                minutes = int((start_time_seconds % 3600) // 60)
                seconds = start_time_seconds % 60
                webvtt_time = f"{hours:02d}:{minutes:02d}:{seconds:06.3f}"
                
                print(f"\n--- Change {change_idx + 1}/{len(changes)} ---")
                print(f"Looking for caption with start time: {start_time_seconds}s -> {webvtt_time}")
                print(f"New text: '{new_text}'")
                
                # Find matching caption by start time (with some tolerance for floating point precision)
                found = False
                best_match = None
                best_diff = float('inf')
                
                for caption_idx, caption in enumerate(captions):
                    print(f"  [{caption_idx}] Checking caption start: {caption.start}")
                    print(f"      Current text: '{caption.text}'")
                    
                    # Convert caption start time to seconds for comparison
                    caption_parts = caption.start.split(':')
                    caption_hours = int(caption_parts[0])
                    caption_minutes = int(caption_parts[1])
                    caption_seconds = float(caption_parts[2])
                    caption_total_seconds = caption_hours * 3600 + caption_minutes * 60 + caption_seconds
                    
                    time_diff = abs(caption_total_seconds - start_time_seconds)
                    print(f"      Time difference: {time_diff:.3f}s")
                    
                    # Allow larger tolerance to account for shift calculations in HTML generation
                    if time_diff < 3.0:
                        if time_diff < best_diff:
                            best_match = (caption_idx, caption, time_diff)
                            best_diff = time_diff
                        print(f"      ✓ Within tolerance (best so far: {time_diff:.3f}s)")
                    else:
                        print(f"      ✗ Outside tolerance")
                
                if best_match:
                    caption_idx, caption, time_diff = best_match
                    print(f"  BEST MATCH: Caption [{caption_idx}] with {time_diff:.3f}s difference")
                    print(f"  Old text: '{caption.text}'")
                    if caption.text.strip() != new_text.strip():
                        caption.text = new_text.strip()
                        modified = True
                        print(f"  ✓ Updated caption text to: '{caption.text}'")
                    else:
                        print(f"  - Text unchanged")
                    found = True
                else:
                    print(f"  ✗ No matching caption found for start time: {start_time_seconds}s")
                    print(f"  Available VTT timestamps:")
                    for i, cap in enumerate(captions):
                        cap_parts = cap.start.split(':')
                        cap_seconds = int(cap_parts[0]) * 3600 + int(cap_parts[1]) * 60 + float(cap_parts[2])
                        diff = abs(cap_seconds - start_time_seconds)
                        print(f"    [{i}] {cap.start} ({cap_seconds:.3f}s) - diff: {diff:.3f}s - '{cap.text[:50]}...'")
                
                if not found:
                    print(f"  ⚠️ SKIPPED: No match found for change {change_idx + 1}")
            
            # Save modified VTT file
            if modified:
                print(f"Saving modified VTT file: {vtt_file}")
                captions.save(str(vtt_file))
            else:
                print(f"No changes to save for VTT file: {vtt_file}")
        
        print(f"Successfully saved changes to VTT files in {vtt_dir}")
        
        # For now, let's just update VTT files and tell user to manually regenerate
        # The complex HTML regeneration can be done via the existing rerun button
        
        return {"success": True, "message": "Transcript changes saved successfully"}
        
    except Exception as e:
        print(f"Error saving transcript edits: {e}")
        return {"success": False, "error": str(e)}


@app.post("/api/save-transcript/{basename}")
async def save_transcript_edits(basename: str, request: Request):
    """Save edited transcript data back to VTT files and regenerate HTML/DOCX"""
    
    try:
        data = await request.json()
        segments = data.get("segments", [])
        
        # Group segments by speaker
        speaker_segments = {}
        for segment in segments:
            speaker = segment["speaker"]
            if speaker not in speaker_segments:
                speaker_segments[speaker] = []
            speaker_segments[speaker].append(segment)
        
        # Save to VTT files
        vtt_dir = TRANSCRIPTION_DIR / basename
        vtt_dir.mkdir(exist_ok=True)
        
        # Clear existing VTT files
        for old_vtt in vtt_dir.glob("*.vtt"):
            old_vtt.unlink()
        
        # Write new VTT files
        for speaker_idx, (speaker, speaker_segs) in enumerate(speaker_segments.items()):
            vtt_file = vtt_dir / f"{speaker_idx}.vtt"
            
            with open(vtt_file, 'w', encoding='utf-8') as f:
                f.write("WEBVTT\\n\\n")
                
                for seg in speaker_segs:
                    f.write(f"{seg['start_time']} --> {seg['end_time']}\\n")
                    f.write(f"{seg['text']}\\n\\n")
        
        # Regenerate HTML file
        _regenerate_html_from_vtt(basename)
        
        return {"success": True, "message": "Transcript saved successfully"}
        
    except Exception as e:
        return {"success": False, "error": str(e)}


def _regenerate_html_from_vtt(basename: str):
    """Regenerate HTML file from updated VTT files"""
    try:
        # This is a simplified regeneration - in a full implementation,
        # you'd want to call the main transcription pipeline with the updated VTT files
        # For now, we'll create a basic HTML structure
        
        transcript_data = _load_transcript_data(basename)
        segments = transcript_data["segments"]
        
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{basename} (Edited)</title>
    <style>
        body {{ font-family: sans-serif; margin: 2rem; }}
        .segment {{ margin: 1rem 0; padding: 1rem; background: #f8f9fa; border-radius: 4px; }}
        .speaker {{ font-weight: bold; color: #007bff; }}
        .timestamp {{ color: #6c757d; font-size: 0.875rem; }}
    </style>
</head>
<body>
    <h1>Transcript: {basename} (Edited)</h1>
    <p><em>This transcript has been edited. <a href="/edit/{basename}.html">Edit again</a></em></p>
"""
        
        for segment in segments:
            html_content += f'''
    <div class="segment">
        <div class="timestamp">[{segment["start_time"]} → {segment["end_time"]}]</div>
        <div><span class="speaker">{segment["speaker"]}:</span> {segment["text"]}</div>
    </div>
'''
        
        html_content += """
</body>
</html>
"""
        
        html_path = TRANSCRIPTION_DIR / f"{basename}.html"
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
            
    except Exception as e:
        print(f"Error regenerating HTML: {e}")
