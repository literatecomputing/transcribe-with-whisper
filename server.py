import os
import shutil
import subprocess
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from huggingface_hub import HfApi


APP_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", APP_DIR / "uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Transcribe with Whisper (Web)")
app.mount("/files", StaticFiles(directory=str(UPLOAD_DIR)), name="files")


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
    dest_path = UPLOAD_DIR / file.filename
    with dest_path.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    # Build CLI command; pass speaker names if provided
    cmd = [
        "transcribe-with-whisper",
        file.filename,  # pass relative name so HTML references are web-servable
    ]
    if speaker:
        # Filter out empties; keep order
        speakers = [s.strip() for s in speaker if s and s.strip()]
        cmd.extend(speakers)

    # Run the CLI synchronously; the CLI writes ../<basename>.html relative to its work dir
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(UPLOAD_DIR),
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

    # Determine output HTML path; the CLI writes uploads/<basename>.html
    basename = Path(file.filename).stem
    html_out = UPLOAD_DIR / f"{basename}.html"
    if not html_out.exists():
        # Fallback: scan for any html created recently
        candidates = sorted(UPLOAD_DIR.glob("*.html"), key=lambda p: p.stat().st_mtime, reverse=True)
        if candidates:
            html_out = candidates[0]
        else:
            return PlainTextResponse("Transcription finished but no HTML output found.", status_code=500)

    # Redirect to served HTML
    rel_url = f"/files/{html_out.name}"
    return RedirectResponse(url=rel_url, status_code=303)
