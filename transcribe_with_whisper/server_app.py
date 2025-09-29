import os
import sys
import shutil
import subprocess
import threading
from pathlib import Path
from datetime import datetime
from typing import Iterable, List, Optional, Dict
import json
import re
import webvtt

from fastapi import FastAPI, File, UploadFile, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from huggingface_hub import HfApi


APP_DIR = Path(__file__).resolve().parent
# Preferred env var TRANSCRIPTION_DIR; fall back to legacy UPLOAD_DIR; default to repo-root ./transcription-files
TRANSCRIPTION_DIR = Path(
  os.getenv(
    "TRANSCRIPTION_DIR",
    os.getenv("UPLOAD_DIR", str(APP_DIR.parent / "transcription-files")),
  )
)
TRANSCRIPTION_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="MercuryScribe (Web)")
app.mount("/files", StaticFiles(directory=str(TRANSCRIPTION_DIR)), name="files")

# Simple in-memory job tracking
jobs: Dict[str, dict] = {}
job_counter = 0


INDEX_HTML = """
<!doctype html>
<html>
  <head>
    <meta charset=\"utf-8\">
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
    <title>MercuryScribe</title>
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
      <h1>MercuryScribe</h1>
      <p class=\"tip\">Upload a video/audio file. The server will run diarization and transcription, then return an interactive HTML transcript.</p>
      <p class=\"tip\">Manage or edit files in <code>./transcription-files</code> or use the list view: <a href=\"/list\">Browse transcription-files</a>.</p>
      <p class=\"tip\">Set <code>HUGGING_FACE_AUTH_TOKEN</code> in your environment before starting.</p>
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


@app.get("/api/job/{job_id}")
async def get_job_status(job_id: str):
    if job_id not in jobs:
        return {"error": "Job not found"}, 404
    return jobs[job_id]


@app.get("/progress/{job_id}", response_class=HTMLResponse)
async def progress_page(job_id: str):
    if job_id not in jobs:
        return PlainTextResponse("Job not found", status_code=404)

    job = jobs[job_id]
    return HTMLResponse(f"""
<!doctype html>
<html>
  <head>
    <meta charset=\"utf-8\">
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
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
              document.querySelector('.spinner').style.display = 'none';
              document.getElementById('status-container').innerHTML = 
                '<div class=\"success\">✅ Transcription completed! <a href=\"' + data.result + '\">View result</a></div>' +
                '<p><a href=\"/list\">View all files</a> | <a href=\"/\">Upload another file</a></p>';
            }} else if (data.status === 'error') {{
              document.querySelector('.spinner').style.display = 'none';
              document.getElementById('status-container').innerHTML = 
                '<div class=\"error\">❌ Error: ' + data.message + '</div>' +
                '<p><a href=\"/\">Try again</a></p>';
            }} else {{
              setTimeout(updateProgress, 2000);
            }}
          }})
          .catch(() => setTimeout(updateProgress, 5000));
      }}
      window.onload = function() {{ updateProgress(); }};
    </script>
  </head>
  <body>
    <div class=\"card\">
      <h1>Transcribing: {job['filename']}</h1>
      <div class=\"progress-bar\">
        <div id=\"progress-fill\" class=\"progress-fill\" style=\"width: {job['progress']}%\"></div>
      </div>
      <div class=\"status\">
        <span class=\"spinner\"></span>
        <span id=\"progress-text\">{job['progress']}%</span> -
        <span id=\"status-message\">{job['message']}</span>
      </div>
      <div id=\"status-container\"></div>
      <p><small>This page will automatically update. Please don't close your browser.</small></p>
    </div>
  </body>
</html>
""")


def _build_cli_cmd(filename: str, speakers: Optional[List[str]] = None) -> List[str]:
    """Use the python -m entry to invoke CLI installed from this same package."""
    cmd: List[str] = [sys.executable, "-m", "transcribe_with_whisper.main", filename]
    if speakers:
        cmd.extend(speakers)
    return cmd


def _validate_hf_token_or_die() -> None:
    token = os.getenv("HUGGING_FACE_AUTH_TOKEN")
    if not token:
        raise RuntimeError("HUGGING_FACE_AUTH_TOKEN is not set. Set it before starting the server.")
    try:
        api = HfApi()
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
    if os.getenv("SKIP_HF_STARTUP_CHECK") == "1":
        print("⚠️  Skipping HF token startup check due to SKIP_HF_STARTUP_CHECK=1.")
        return
    _validate_hf_token_or_die()


def _human_size(n: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.0f} PB"


def _list_dir_entries(path: Path) -> Iterable[Path]:
    return sorted([p for p in path.iterdir() if p.is_file()], key=lambda p: p.name.lower())


def _run_transcription_job(job_id: str, filename: str, speakers: Optional[List[str]]):
    global jobs
    try:
        jobs[job_id]["status"] = "running"
        jobs[job_id]["message"] = "Starting transcription..."
        jobs[job_id]["progress"] = 5

        cmd = _build_cli_cmd(filename, speakers or None)
        jobs[job_id]["message"] = "Processing audio and running AI models..."
        jobs[job_id]["progress"] = 20

        proc = subprocess.run(
            cmd,
            cwd=str(TRANSCRIPTION_DIR),
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

        try:
            docx_out = html_out.with_suffix('.docx')
            # Try to find helper script in working directory's bin first, then skip silently
            html_to_docx_script = Path("bin/html-to-docx.sh")
            if html_to_docx_script.exists():
                subprocess.run([str(html_to_docx_script), str(html_out), str(docx_out)], check=True, capture_output=True, text=True)
                print(f"✅ Generated DOCX: {docx_out.name}")
            else:
                print("⚠️ html-to-docx.sh not found in ./bin, skipping DOCX generation")
        except Exception as e:
            print(f"⚠️ DOCX generation failed: {e}")

        jobs[job_id]["status"] = "completed"
        jobs[job_id]["progress"] = 100
        jobs[job_id]["message"] = "Transcription completed!"
        jobs[job_id]["result"] = f"/files/{html_out.name}"
    except Exception as e:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["message"] = f"Failed to run transcription: {e}"


@app.post("/upload")
async def upload(file: UploadFile = File(...), speaker: Optional[List[str]] = Form(default=None)):
    global job_counter, jobs
    if not os.getenv("HUGGING_FACE_AUTH_TOKEN"):
        return PlainTextResponse(
            "HUGGING_FACE_AUTH_TOKEN not set. Set it when running the server.", status_code=500
        )

    dest_path = TRANSCRIPTION_DIR / file.filename
    with dest_path.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    job_counter += 1
    job_id = str(job_counter)
    speakers = [s.strip() for s in (speaker or []) if s and s.strip()]

    jobs[job_id] = {
        "status": "starting",
        "progress": 0,
        "message": "Preparing transcription...",
        "filename": file.filename,
    }

    thread = threading.Thread(target=_run_transcription_job, args=(job_id, file.filename, speakers))
    thread.daemon = True
    thread.start()

    return RedirectResponse(url=f"/progress/{job_id}", status_code=303)


@app.get("/list", response_class=HTMLResponse)
async def list_files(_: Request):
    files = _list_dir_entries(TRANSCRIPTION_DIR)
    rows = []
    media_exts = {".mp4", ".m4a", ".wav", ".mp3", ".mkv", ".mov"}
    for p in files:
        name = p.name
        size = _human_size(p.stat().st_size)
        mtime = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        actions = []

        # HTML outputs: View (and Edit/Regenerate if VTTs exist)
        if p.suffix.lower() == ".html":
            actions.append(f'<a href="/files/{name}">View</a>')
            basename = p.stem
            vtt_dir = TRANSCRIPTION_DIR / basename

        # Media inputs: allow Re-run
        if p.suffix.lower() in media_exts:
            actions.append(
                f'<form method="post" action="/rerun" style="display:inline">'
                f'<input type="hidden" name="filename" value="{name}">' \
                f'<button type="submit">Re-run</button></form>'
            )

        # Download links (strong for DOCX)
        if p.suffix.lower() == ".docx":
            actions.append(f'<a href="/files/{name}" download><strong>📄 Download DOCX</strong></a>')
        else:
            actions.append(f'<a href="/files/{name}" download>Download</a>')

        rows.append(
            f"<tr><td>{name}</td><td style='text-align:right'>{size}</td><td>{mtime}</td><td>{' | '.join(actions)}</td></tr>"
        )

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
    """Re-run transcription for an existing media file in the transcription dir."""
    global job_counter, jobs

    target = (TRANSCRIPTION_DIR / filename).resolve()
    if not target.exists() or target.parent != TRANSCRIPTION_DIR.resolve():
        return PlainTextResponse("Invalid file.", status_code=400)

    if target.suffix.lower() not in {".mp4", ".m4a", ".wav", ".mp3", ".mkv", ".mov"}:
        return PlainTextResponse("Re-run is only supported for media files.", status_code=400)

    job_counter += 1
    job_id = str(job_counter)
    jobs[job_id] = {
        "status": "starting",
        "progress": 0,
        "message": "Preparing transcription...",
        "filename": filename,
    }

    thread = threading.Thread(target=_run_transcription_job, args=(job_id, target.name, None))
    thread.daemon = True
    thread.start()

    return RedirectResponse(url=f"/progress/{job_id}", status_code=303)


def _load_transcript_data(basename: str):
    """Load transcript data from VTT files for editing"""
    vtt_dir = TRANSCRIPTION_DIR / basename
    segments = []

    if not vtt_dir.exists():
        return {"segments": segments}

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
                    "text": caption.text,
                })
        except Exception as e:
            print(f"Error reading VTT file {vtt_file}: {e}")

    segments.sort(key=lambda x: x["start_time"])
    return {"segments": segments}

## /edit route removed


@app.post("/save_transcript_edits/{basename}")
async def save_in_place_transcript_edits(basename: str, request: Request):
    """Save in-place edited transcript changes back to VTT files using precise VTT file and caption index"""
    
    # Enable debug logging if requested
    debug = os.getenv("DEBUG_SAVE_EDITS") == "1"
    
    try:
        data = await request.json()
        changes = data.get("changes", [])
        if not changes:
            return {"success": False, "error": "No changes provided"}

        vtt_dir = TRANSCRIPTION_DIR / basename
        if not vtt_dir.exists():
            return {"success": False, "error": f"Transcript directory not found: {basename}"}

        if debug:
            print(f"[DEBUG] Processing {len(changes)} changes for {basename}")

        # Track which VTT files we've modified
        modified_files: set[Path] = set()
        applied = 0
        failed: List[dict] = []

        for change in changes:
            # Extract VTT-specific information from the change
            vtt_file = change.get("vttFile", "").strip()
            caption_idx_str = change.get("captionIdx", "").strip()
            new_text = change.get("text", "").strip()
            
            if debug:
                print(f"[DEBUG] Change: vttFile='{vtt_file}', captionIdx='{caption_idx_str}', text='{new_text[:50]}...'")

            # Validate that we have the required VTT-specific information
            if not vtt_file or not caption_idx_str:
                if debug:
                    print(f"[DEBUG] Missing VTT info, skipping change")
                failed.append({
                    "error": "Missing vttFile or captionIdx - HTML may be from legacy version",
                    "change": change
                })
                continue

            try:
                caption_idx = int(caption_idx_str)
            except ValueError:
                if debug:
                    print(f"[DEBUG] Invalid captionIdx '{caption_idx_str}', skipping")
                failed.append({
                    "error": f"Invalid captionIdx: {caption_idx_str}",
                    "change": change
                })
                continue

            # Locate the specific VTT file
            vtt_path = vtt_dir / vtt_file
            if not vtt_path.exists():
                if debug:
                    print(f"[DEBUG] VTT file not found: {vtt_path}")
                failed.append({
                    "error": f"VTT file not found: {vtt_file}",
                    "change": change
                })
                continue

            try:
                # Load the VTT file
                captions = webvtt.read(str(vtt_path))
                
                # Validate caption index
                if caption_idx < 0 or caption_idx >= len(captions):
                    if debug:
                        print(f"[DEBUG] Caption index {caption_idx} out of range (0-{len(captions)-1})")
                    failed.append({
                        "error": f"Caption index {caption_idx} out of range (0-{len(captions)-1})",
                        "change": change
                    })
                    continue

                # Update the specific caption
                old_text = captions[caption_idx].text.strip()
                if old_text != new_text:
                    captions[caption_idx].text = new_text
                    captions.save(str(vtt_path))
                    modified_files.add(vtt_path)
                    if debug:
                        print(f"[DEBUG] Updated {vtt_file}[{caption_idx}]: '{old_text}' -> '{new_text}'")
                else:
                    if debug:
                        print(f"[DEBUG] No change needed for {vtt_file}[{caption_idx}]")

                applied += 1

            except Exception as e:
                if debug:
                    print(f"[DEBUG] Error processing {vtt_file}: {e}")
                failed.append({
                    "error": f"Error processing {vtt_file}: {str(e)}",
                    "change": change
                })

        result = {
            "success": True,
            "message": f"Applied {applied}/{len(changes)} changes to {len(modified_files)} VTT files"
        }
        
        if failed:
            result["failed"] = failed
            if debug:
                print(f"[DEBUG] {len(failed)} changes failed")

        return result

    except Exception as e:
        if debug:
            print(f"[DEBUG] Unexpected error: {e}")
        return {"success": False, "error": str(e)}


@app.post("/update-speakers")
async def update_speakers(request: Request):
  """Update speaker names mapping and persist to a JSON config.

  Accepts JSON: {"filename": basename, "speakers": {"Old Name": "New Name", ...}}
  Looks for an existing config in either:
    - {TRANSCRIPTION_DIR}/{basename}/{basename}-speakers.json
    - {TRANSCRIPTION_DIR}/{basename}-speakers.json
  If none exists, creates a new one based on detected VTT tracks.
  """
  try:
    data = await request.json()
    basename = data.get("filename")
    speakers_mapping = data.get("speakers") or {}
    if not basename or not isinstance(speakers_mapping, dict) or not speakers_mapping:
      return {"success": False, "message": "Missing filename or speakers mapping"}

    vtt_dir = TRANSCRIPTION_DIR / basename
    config_candidates = [
      vtt_dir / f"{basename}-speakers.json",
      TRANSCRIPTION_DIR / f"{basename}-speakers.json",
    ]

    # Try to load existing config
    existing_config_path: Optional[Path] = None
    existing_config: Optional[dict] = None
    for cand in config_candidates:
      if cand.exists():
        try:
          with open(cand, "r", encoding="utf-8") as f:
            existing_config = json.load(f)
          existing_config_path = cand
          break
        except Exception as e:
          return {"success": False, "message": f"Could not read speaker config {cand}: {e}"}

    # Normalize existing config to {speaker_id: {name,bgcolor,textcolor}}
    speakers_by_id: Dict[str, dict] = {}
    if existing_config:
      for speaker_id, info in existing_config.items():
        if isinstance(info, dict):
          speakers_by_id[speaker_id] = {
            "name": info.get("name", speaker_id),
            "bgcolor": info.get("bgcolor", "lightgray"),
            "textcolor": info.get("textcolor", "darkorange"),
          }
        else:
          speakers_by_id[speaker_id] = {
            "name": str(info),
            "bgcolor": "lightgray",
            "textcolor": "darkorange",
          }
    else:
      # No config yet: initialize from VTT files if present
      if vtt_dir.exists():
        vtt_ids = sorted([p.stem for p in vtt_dir.glob("*.vtt") if p.stem.isdigit()], key=lambda x: int(x))
        if vtt_ids:
          # Map provided new names onto track ids in order; if mapping fewer, reuse last; if more, ignore extras
          new_names = list(speakers_mapping.values())
          for i, sid in enumerate(vtt_ids):
            name = new_names[i] if i < len(new_names) else f"Speaker {int(sid)+1}"
            speakers_by_id[sid] = {"name": name, "bgcolor": "lightgray", "textcolor": "darkorange"}
      # As a fallback, create a single default if nothing detected
      if not speakers_by_id:
        speakers_by_id["0"] = {"name": next(iter(speakers_mapping.values())), "bgcolor": "lightgray", "textcolor": "darkorange"}

    # Apply mapping: rename by matching current names to keys in provided mapping
    for sid, info in speakers_by_id.items():
      current = info.get("name", sid)
      if current in speakers_mapping:
        info["name"] = speakers_mapping[current]

    # Choose config path: prefer per-video directory
    config_path = (vtt_dir / f"{basename}-speakers.json") if vtt_dir.exists() else (TRANSCRIPTION_DIR / f"{basename}-speakers.json")
    try:
      with open(config_path, "w", encoding="utf-8") as f:
        json.dump(speakers_by_id, f, indent=2)
    except Exception as e:
      return {"success": False, "message": f"Could not save speaker config {config_path}: {e}"}

    return {"success": True, "message": f"Updated speaker config: {config_path.name}"}
  except Exception as e:
    return {"success": False, "message": f"Error updating speakers: {str(e)}"}


@app.post("/api/save-transcript/{basename}")
async def save_transcript_edits(basename: str, request: Request):
    """Save edited transcript data back to VTT files and regenerate HTML/DOCX"""
    try:
        data = await request.json()
        segments = data.get("segments", [])

        # Group by speaker
        speaker_segments: Dict[str, List[dict]] = {}
        for seg in segments:
            speaker_segments.setdefault(seg.get("speaker", "Unknown"), []).append(seg)

        vtt_dir = TRANSCRIPTION_DIR / basename
        vtt_dir.mkdir(exist_ok=True)

        for old_vtt in vtt_dir.glob("*.vtt"):
            old_vtt.unlink()

        for speaker_idx, (_, speaker_segs) in enumerate(speaker_segments.items()):
            vtt_file = vtt_dir / f"{speaker_idx}.vtt"
            with open(vtt_file, 'w', encoding='utf-8') as f:
                f.write("WEBVTT\n\n")
                for seg in speaker_segs:
                    f.write(f"{seg['start_time']} --> {seg['end_time']}\n")
                    f.write(f"{seg['text']}\n\n")

        _regenerate_html_from_vtt(basename)
        return {"success": True, "message": "Transcript saved successfully"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def main() -> None:
    """Run the MercuryScribe web server via uvicorn."""
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "5001"))
    uvicorn.run(app, host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
