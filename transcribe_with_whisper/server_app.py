import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

# Set web server mode to enable graceful startup without token
os.environ["WEB_SERVER_MODE"] = "1"
import re

import webvtt
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from huggingface_hub import HfApi, hf_hub_download
from huggingface_hub.utils import GatedRepoError

# Add support for getting audio file duration
try:
  from pydub import AudioSegment
  _HAS_PYDUB = True
except ImportError:
  _HAS_PYDUB = False


# Token storage functions
def _get_config_dir() -> Path:
  """Get the directory where config files are stored"""
  # Use the already-resolved TRANSCRIPTION_DIR so saved config lives where the server reads it
  try:
    config_base = TRANSCRIPTION_DIR
  except NameError:
    # Fallback only during early import when TRANSCRIPTION_DIR hasn't been set yet
    config_base = Path(
        os.getenv("TRANSCRIPTION_DIR",
                  str(Path(__file__).resolve().parent.parent / "mercuryscribe")))
  config_dir = Path(config_base) / ".config"
  config_dir.mkdir(parents=True, exist_ok=True)
  return config_dir


def _save_hf_token(token: str) -> None:
  """Save Hugging Face token to config file"""
  config_file = _get_config_dir() / "hf_token"
  config_file.touch(mode=0o600)
  normalized = token.strip()
  config_file.write_text(normalized, encoding='utf-8')
  config_file.chmod(0o600)
  if normalized:
    os.environ["HUGGING_FACE_AUTH_TOKEN"] = normalized


def _load_hf_token() -> str | None:
  """Load Hugging Face token from config file"""
  config_file = _get_config_dir() / "hf_token"
  if config_file.exists():
    try:
      token = config_file.read_text(encoding='utf-8').strip()
      if token:
        # Ensure any code relying on the environment sees the token as well
        os.environ["HUGGING_FACE_AUTH_TOKEN"] = token
        return token
      return None
    except (OSError, UnicodeDecodeError):
      return None
  return None


def _prime_token_env() -> str | None:
  """Ensure HUGGING_FACE_AUTH_TOKEN is populated from env or saved file."""
  env_token = os.getenv("HUGGING_FACE_AUTH_TOKEN")
  if env_token and env_token.strip():
    normalized = env_token.strip()
    os.environ["HUGGING_FACE_AUTH_TOKEN"] = normalized
    return normalized

  file_token = _load_hf_token()
  if file_token:
    os.environ["HUGGING_FACE_AUTH_TOKEN"] = file_token
    return file_token

  return None


APP_DIR = Path(__file__).resolve().parent
BRANDING_DIR = APP_DIR.parent / "branding"


# Select best available branding assets
_main_logo = "ms-logoblock-blue.text.svg" if (BRANDING_DIR / "ms-logoblock-blue.text.svg").exists() else "mercuryscribe-logo.svg"
_favicon = "ms-logoblock.svg" if (BRANDING_DIR / "ms-logoblock.svg").exists() else "mercuryscribe-logo.svg"

FAVICON_LINK_TAG = f'<link rel="icon" type="image/svg+xml" href="/branding/{_favicon}">' if BRANDING_DIR.exists() else ''


def _apply_branding(html: str) -> str:
  """Inject favicon and replace branding placeholders like {_main_logo}."""
  if FAVICON_LINK_TAG:
    html = html.replace("</title>", f"</title>\n    {FAVICON_LINK_TAG}", 1)
  
  # Replace logo placeholder if it exists
  html = html.replace("{_main_logo}", _main_logo)
  
  return html


# Preferred env var TRANSCRIPTION_DIR; fall back to legacy UPLOAD_DIR; default to HOME ~/mercuryscribe
# Prefer the user's home directory when available (both bundled and development). Only fall back
# to repo-relative path when HOME/USERPROFILE is not set.
home_dir = os.getenv("HOME") or os.getenv("USERPROFILE")
if home_dir:
  default_transcription_dir = Path(home_dir) / "mercuryscribe"
else:
  # If HOME isn't set, behave like a bundled app and try LOCALAPPDATA or APPDATA first,
  # then finally fall back to a repo-relative path.
  localapp = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA")
  if localapp:
    default_transcription_dir = Path(localapp) / "MercuryScribe"
  else:
    default_transcription_dir = APP_DIR.parent / "mercuryscribe"

TRANSCRIPTION_DIR = Path(
    os.getenv(
        "TRANSCRIPTION_DIR",
        os.getenv("UPLOAD_DIR", str(default_transcription_dir)),
    ))
TRANSCRIPTION_DIR.mkdir(parents=True, exist_ok=True)

# Load saved token into environment if needed
_prime_token_env()


@asynccontextmanager
async def lifespan(app: FastAPI):
  """Lifespan event handler for startup and shutdown events"""
  # Startup
  if os.getenv("SKIP_HF_STARTUP_CHECK") != "1":
    if _has_valid_token():
      print("Hugging Face token found and validated.")
    else:
      print("No valid Hugging Face token found. Users will be guided through setup.")
  else:
    print("Skipping HF token startup check due to SKIP_HF_STARTUP_CHECK=1.")

  yield

  # Shutdown (nothing to clean up for now)


app = FastAPI(title="MercuryScribe (Web)", lifespan=lifespan)
app.mount("/files", StaticFiles(directory=str(TRANSCRIPTION_DIR)), name="files")
if BRANDING_DIR.exists():
  app.mount("/branding", StaticFiles(directory=str(BRANDING_DIR)), name="branding")
else:
  print("Branding directory not found; favicon will be unavailable.")

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
      .row input[type=number] { width: 80px; padding: 0.6rem; border: 1px solid #ddd; border-radius: 6px; }
      .row label { min-width: 120px; }
      button { background: #0d6efd; color: white; border: 0; padding: 0.6rem 1rem; border-radius: 6px; cursor: pointer; }
      button:disabled { opacity: .6; cursor: progress; }
      .tip { color: #555; font-size: .95rem; }
      code { background: #f6f8fa; padding: .1rem .3rem; border-radius: 4px; }
      .help-text { color: #666; font-size: 0.85rem; margin-top: 0.25rem; }
    </style>
  </head>
  <body>
    <div class="card">
      <div style="display: flex; align-items: center; justify-content: center; margin-bottom: 1.5rem; border-bottom: 1px solid #eee; padding-bottom: 1.5rem;">
        <img src="/branding/{_main_logo}" alt="MercuryScribe Logo" style="max-height: 200px; width: auto; display: block;">
      </div>
      <p class="tip">Upload a video/audio file. The server will run diarization and transcription, then return an interactive HTML transcript.</p>
      <p class=\"tip\">You can manage or edit files on your computer in <code>~/mercuryscribe</code> or see them here <a href=\"/list\">here</a>.</p>
      <form action=\"/upload\" method=\"post\" enctype=\"multipart/form-data\" onsubmit=\"document.getElementById('submit').disabled = true; document.getElementById('submit').innerText='Processing…';\">
        <input type=\"file\" name=\"file\" accept=\"video/*,audio/*\" required>

        <details>
          <summary>🎙️ Speaker Configuration (Optional - improves accuracy)</summary>
          <div style=\"padding: 0.5rem 0;\">
            <div class=\"row\">
              <label for=\"num-speakers\">Number of speakers:</label>
              <input type=\"number\" id=\"num-speakers\" name=\"num_speakers\" min=\"1\" max=\"20\" placeholder=\"Auto\">
            </div>
            <div class=\"help-text\">If you know the exact number of speakers, enter it here for better accuracy. Leave blank for automatic detection.</div>

            <div class=\"row\" style=\"margin-top: 0.75rem;\">
              <label for=\"min-speakers\">Min speakers:</label>
              <input type=\"number\" id=\"min-speakers\" name=\"min_speakers\" min=\"1\" max=\"20\" placeholder=\"Auto\">
            </div>
            <div class=\"row\">
              <label for=\"max-speakers\">Max speakers:</label>
              <input type=\"number\" id=\"max-speakers\" name=\"max_speakers\" min=\"1\" max=\"20\" placeholder=\"Auto\">
            </div>
            <div class=\"help-text\">Or specify a range if you're unsure of the exact number.</div>
          </div>
        </details>

        <button id=\"submit\" type=\"submit\">Transcribe</button>
      </form>
    </div>
  </body>
  </html>
"""

SETUP_HTML = """
<!doctype html>
<html>
  <head>
    <meta charset=\"utf-8\">
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
    <title>MercuryScribe Setup</title>
    <style>
      body { font-family: system-ui, sans-serif; max-width: 800px; margin: 2rem auto; padding: 0 1rem; background: #f8f9fa; }
      .card { background: #fff; border-radius: 12px; padding: 2rem; box-shadow: 0 4px 12px rgba(0,0,0,0.1); margin-bottom: 1.5rem; }
      h1 { margin: 0 0 1rem; color: #333; }
      h2 { margin: 1.5rem 0 1rem; color: #444; font-size: 1.2rem; }
      .steps { counter-reset: step; }
      .step { counter-increment: step; margin: 1.5rem 0; }
      .step::before { content: counter(step); background: #0d6efd; color: white; border-radius: 50%; width: 24px; height: 24px; display: inline-flex; align-items: center; justify-content: center; margin-right: 0.75rem; font-weight: bold; font-size: 0.9rem; }
      .tip { color: #666; font-size: .95rem; background: #f6f8fa; padding: 1rem; border-radius: 8px; border-left: 4px solid #0d6efd; }
      .warning { color: #856404; background: #fff3cd; border-left: 4px solid #ffc107; }
      .success { color: #155724; background: #d4edda; border-left: 4px solid #28a745; }
      .error { color: #721c24; background: #f8d7da; border-left: 4px solid #dc3545; }
      code { background: #f6f8fa; padding: .2rem .4rem; border-radius: 4px; font-size: 0.9rem; }
      a { color: #0d6efd; text-decoration: none; }
      a:hover { text-decoration: underline; }
      input[type=text], input[type=password] { width: 100%; padding: 0.75rem; border: 1px solid #ddd; border-radius: 6px; box-sizing: border-box; font-size: 1rem; }
      button { background: #0d6efd; color: white; border: 0; padding: 0.75rem 1.5rem; border-radius: 6px; cursor: pointer; font-size: 1rem; }
      button:disabled { opacity: .6; cursor: not-allowed; }
      button.secondary { background: #6c757d; }
      .form-group { margin: 1rem 0; }
      label { display: block; margin-bottom: 0.5rem; font-weight: 500; }
      .token-form { margin-top: 1.5rem; }
      .status { margin-top: 1rem; padding: 1rem; border-radius: 6px; display: none; }
      .button-group { display: flex; gap: 1rem; margin-top: 1.5rem; }
      .token-preview { font-family: monospace; background: #f8f9fa; padding: 0.5rem; border: 1px solid #dee2e6; border-radius: 4px; margin: 0.5rem 0; word-break: break-all; }
            .model-list { margin: 0.75rem 0 0; padding-left: 1.5rem; }
            .model-list li { margin: 0.35rem 0; }
    </style>
  </head>
  <body>
    <div class="card">
      <div style="display: flex; align-items: center; justify-content: center; margin-bottom: 1.5rem; border-bottom: 1px solid #eee; padding-bottom: 1.5rem;">
        <img src="/branding/{_main_logo}" alt="MercuryScribe Logo" style="max-height: 200px; width: auto; display: block;">
      </div>
      <h2>🚀 Welcome!</h2>
      <p>Before you can start transcribing, we need to set up your HuggingFace access token. This enables the AI models for speaker diarization and transcription.</p>

    </div>

    <div class=\"card\">
      <h2>📋 Setup Steps</h2>
      <div class=\"steps\">
        <div class=\"step\">
          <strong>Create a HuggingFace account</strong> if you don't have one at <a href=\"https://huggingface.co/join\" target=\"_blank\">huggingface.co/join</a>
        </div>
        <div class=\"step\">
          <strong>Create an access token</strong> by visiting <a href=\"https://huggingface.co/settings/tokens\" target=\"_blank\">HuggingFace Settings → Access Tokens</a>
        </div>
        <div class=\"step\">
          <strong>Create a new token</strong> with these settings:
          <ul style=\"margin: 0.5rem 0; padding-left: 2rem;\">
            <li><strong>Name:</strong> MercuryScribe (or any name you prefer)</li>
            <li><strong>Type:</strong> Read (<strong>Not</strong> the default: "Fine-grained")</li>
          </ul>
        </div>
        <div class=\"step\">
          <strong>Copy the token</strong> - it should start with <code>hf_</code> and be about 37 characters long
        </div>
        <div class=\"step\">
          <strong>Paste it below</strong> and click "Save Token" after requesting access to the required models below
        </div>
      </div>

      <div class=\"tip\">
        <strong>💡 Tip:</strong> Your token looks like <code>hf_AbCdEfGhIjKlMnOpQrStUvWxYz</code> - a mix of upper/lowercase letters after "hf_"
      </div>
    </div>

            <div class="card">
                <h2>🧠 Required AI Models</h2>
                <p>MercuryScribe needs access to gated HuggingFace models. Open each link below (it will open in a new tab), click the <strong>Agree and access repository</strong> at the bottom of the page before clicking the save button here.</p>
                <ul class="model-list">
    __MODEL_LIST_ITEMS__
                </ul>
                <div class="tip">
                    <strong>Need more help?</strong> There is a video guide available on the <a href="https://www.mercuryscribe.com/docs/get-started/" target="_blank">get-started page</a>.
                </div>
            </div>

    <div class=\"card\">
      <h2>🔑 Enter Your Token</h2>
          <small style=\"color: #666; display: block; margin-top: 0.25rem;\">
            Scroll up for instructions on obtaining a token and accepting the required model licenses.
          </small>
      <div class=\"token-form\">
        <div class=\"form-group\">
          <label for=\"token\">HuggingFace Access Token:</label>
          <input type=\"password\" id=\"token\" placeholder=\"Paste your token here (starts with hf_)\" maxlength=\"50\">
          <small style=\"color: #666; display: block; margin-top: 0.25rem;\">
            Your token is hidden for security. Click "Show" to verify it's correct.
          </small>
        </div>

        <div class=\"button-group\">
          <button onclick=\"toggleTokenVisibility()\" class=\"secondary\" id=\"toggleBtn\">👁️ Show</button>
          <button onclick=\"validateAndSaveToken()\" id=\"saveBtn\">💾 Save Token</button>
        </div>

        <div id=\"status\" class=\"status\"></div>
      </div>
    </div>

    <div class=\"card\" id=\"successCard\" style=\"display: none;\">
      <h2>✅ Setup Complete!</h2>
      <p>Your HuggingFace token has been saved and validated successfully. You can now use MercuryScribe to transcribe your audio and video files.</p>
      <button onclick=\"window.location.href='/'\" style=\"background: #28a745;\">🎯 Start Transcribing</button>
    </div>

    <script>
      let tokenVisible = false;

      function toggleTokenVisibility() {
        const tokenInput = document.getElementById('token');
        const toggleBtn = document.getElementById('toggleBtn');

        tokenVisible = !tokenVisible;
        tokenInput.type = tokenVisible ? 'text' : 'password';
        toggleBtn.textContent = tokenVisible ? '🙈 Hide' : '👁️ Show';
      }

      async function validateAndSaveToken() {
        const token = document.getElementById('token').value.trim();
        const saveBtn = document.getElementById('saveBtn');
        const status = document.getElementById('status');

        if (!token) {
          showStatus('Please enter your HuggingFace token.', 'error');
          return;
        }

        if (!token.startsWith('hf_')) {
          showStatus('Invalid token format. HuggingFace tokens start with \"hf_\".', 'error');
          return;
        }

        saveBtn.disabled = true;
        saveBtn.textContent = '⏳ Validating...';

        try {
          const response = await fetch('/api/save-token', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({ token: token })
          });

          const result = await response.json();

          if (response.ok && result.success) {
            showStatus('✅ Token saved successfully! Redirecting...', 'success');
            document.getElementById('successCard').style.display = 'block';
            setTimeout(() => {
              window.location.href = '/';
            }, 2000);
          } else {
            let errorMsg = result.error || 'Failed to save token. Please check your token and try again.';

                        // Check if this is a model access issue
                                    const defaultModels = __MODEL_JSON__;
                                    const missingModels = result.missing_models || [];
                                    if (missingModels.length > 0 || result.requires_license_acceptance || errorMsg.toLowerCase().includes('access denied') || errorMsg.toLowerCase().includes('license')) {
                                        const modelsToSuggest = missingModels.length ? missingModels : defaultModels;
                                        const modelLinks = modelsToSuggest.map(model => {
                                const reason = model.reason ? ` – ${model.reason}` : '';
                                return `<li><a href="${model.url}" target="_blank">${model.name}</a>${reason}</li>`;
                            }).join('');

                            errorMsg += '<br><br><strong>📋 Action Required:</strong> Ensure your token has access to the following models:<ul class="model-list">' +
                                                     modelLinks +
                                                     '</ul>' +
                                                     'Open each link, accept the license, then try saving your token again.';
            }

            showStatus(`❌ ${errorMsg}`, 'error');
          }
        } catch (error) {
          showStatus('❌ Network error. Please check your connection and try again.', 'error');
        } finally {
          saveBtn.disabled = false;
          saveBtn.textContent = '💾 Save Token';
        }
      }

      function showStatus(message, type) {
        const status = document.getElementById('status');
        status.className = `status ${type}`;
        status.innerHTML = message; // Use innerHTML to support HTML content like links
        status.style.display = 'block';
      }

      // Allow Enter key to submit
      document.getElementById('token').addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
          validateAndSaveToken();
        }
      });

      // Auto-focus the token input
      document.getElementById('token').focus();
    </script>
  </body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def index(_: Request):
  if not _has_valid_token():
    return RedirectResponse(url="/setup", status_code=303)
  return HTMLResponse(_apply_branding(INDEX_HTML))


@app.get("/setup", response_class=HTMLResponse)
async def setup_page(_: Request):
  return HTMLResponse(_render_setup_html())


@app.post("/api/save-token")
async def save_token(request: Request):
  """Save and validate the Hugging Face token"""
  try:
    data = await request.json()
    token = data.get("token", "").strip()

    if not token:
      return {"success": False, "error": "Token is required"}

    # Validate the token
    validation = _validate_hf_token(token)
    if not validation["valid"]:
      return {
          "success": False,
          "error": validation.get("error"),
          "missing_models": validation.get("missing_models", []),
          "requires_license_acceptance": validation.get("requires_license_acceptance", False),
      }

    # Save the token
    _save_hf_token(token)
    return {
        "success": True,
        "message": "Token saved and validated successfully",
        "missing_models": [],
    }

  except Exception as e:
    return {"success": False, "error": f"Failed to save token: {str(e)}"}


@app.get("/api/check-token")
async def check_token():
  """Check if we have a valid token"""
  return {"has_token": _has_valid_token()}


@app.post("/api/test-token")
async def test_token(request: Request):
  """Test a token without saving it - useful for testing different scenarios"""
  try:
    data = await request.json()
    token = data.get("token", "").strip()
    force_no_access = data.get("force_no_access", False)  # For testing

    if not token:
      return {"success": False, "error": "No token provided"}

    # Special test scenarios
    if force_no_access or token.startswith("hf_test_no_access"):
      required_models = _get_required_hf_models()
      error_suffix = "; ".join(
          f"{model['name']} (access denied - you may need to accept the license)"
          for model in required_models)
      return {
          "success":
          False,
          "error":
          f"Cannot access required models: {error_suffix}",
          "requires_license_acceptance":
          True,
          "missing_models": [{
              "name": model["name"],
              "url": model["url"],
              "reason": "access denied - you may need to accept the license",
          } for model in required_models],
      }

    # Validate the token
    validation = _validate_hf_token(token)
    return {
        "success": validation["valid"],
        "error": validation.get("error"),
        "message": validation.get("message"),
        "missing_models": validation.get("missing_models", []),
        "requires_license_acceptance": validation.get("requires_license_acceptance", False)
    }

  except Exception as e:
    return {"success": False, "error": f"Failed to test token: {str(e)}"}


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

  # Format start time
  start_time = job.get('start_time', time.time())
  start_time_str = datetime.fromtimestamp(start_time).strftime("%I:%M:%S %p")

  # Format audio duration
  file_duration = job.get('file_duration')
  if file_duration and file_duration != "Unknown duration":
    duration_minutes = file_duration / 60
    duration_str = f"{duration_minutes:.1f} minutes"
  else:
    duration_str = "Unknown duration"

  return HTMLResponse(
      _apply_branding(f"""
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
      .info {{ color: #666; font-size: 0.9rem; margin: 0.5rem 0; }}
      .stats {{ background: #f8f9fa; padding: 0.75rem; border-radius: 6px; margin: 1rem 0; }}
      .stats-row {{ display: flex; justify-content: space-between; margin: 0.25rem 0; }}
    </style>
    <script>
      function formatTime(timestamp) {{
        const date = new Date(timestamp * 1000);
        return date.toLocaleTimeString('en-US', {{ hour: 'numeric', minute: '2-digit', second: '2-digit' }});
      }}

      function formatElapsed(seconds) {{
        const mins = seconds / 60;
        return mins.toFixed(1) + ' minutes';
      }}

      function formatElapsedShort(seconds) {{
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        if (mins === 0) return secs + 's';
        return mins + 'm ' + secs + 's';
      }}

      function updateElapsedTime() {{
        const now = Math.floor(Date.now() / 1000);
        const elapsed = now - {start_time};
        document.getElementById('elapsed-time').innerText = formatElapsed(elapsed);
      }}

      function updateProgress() {{
        fetch('/api/job/{job_id}')
          .then(response => response.json())
          .then(data => {{
            document.getElementById('progress-fill').style.width = data.progress + '%';
            document.getElementById('progress-text').innerText = data.progress + '%';
            document.getElementById('status-message').innerText = data.message;

            // Update elapsed time
            updateElapsedTime();

            if (data.status === 'completed' && data.result) {{
              document.querySelector('.spinner').style.display = 'none';

              // Calculate and display completion stats
              const endTime = data.end_time || Math.floor(Date.now() / 1000);
              const elapsed = endTime - data.start_time;

              document.getElementById('status-container').innerHTML =
                '<div class=\"success\">✅ Transcription completed! <a href=\"' + data.result + '\">View result</a></div>' +
                '<div class=\"stats\">' +
                '<div class=\"stats-row\"><strong>Completed at:</strong> <span>' + formatTime(endTime) + '</span></div>' +
                '<div class=\"stats-row\"><strong>Total time:</strong> <span>' + formatElapsedShort(elapsed) + '</span></div>' +
                '</div>' +
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
    <div class="card">
      <div style="display: flex; align-items: center; justify-content: center; margin-bottom: 1.5rem; border-bottom: 1px solid #eee; padding-bottom: 1.5rem;">
        <img src="/branding/{_main_logo}" alt="MercuryScribe Logo" style="max-height: 200px; width: auto; display: block;">
      </div>
      <h2>Transcribing: {job['filename']}</h2>
      <div class=\"stats\">
        <div class=\"stats-row\"><strong>Started:</strong> <span>{start_time_str}</span></div>
        <div class=\"stats-row\"><strong>Audio length:</strong> <span>{duration_str}</span></div>
        <div class=\"stats-row\"><strong>Elapsed time:</strong> <span id=\"elapsed-time\">0s</span></div>
      </div>
      <div class=\"progress-bar\">
        <div id=\"progress-fill\" class=\"progress-fill\" style=\"width: {job['progress']}%\"></div>
      </div>
      <div class=\"status\">
        <span class=\"spinner\"></span>
        <span id=\"progress-text\">{job['progress']}%</span> -
        <span id=\"status-message\">{job['message']}</span>
      </div>
      <div id=\"status-container\"></div>
    </div>
  </body>
</html>
"""))


def _build_cli_cmd(filename: str,
                   speakers: Optional[List[str]] = None,
                   num_speakers: Optional[int] = None,
                   min_speakers: Optional[int] = None,
                   max_speakers: Optional[int] = None) -> List[str]:
  """Use the python -m entry to invoke CLI installed from this same package."""
  # When running unpacked/dev, invoke via the Python interpreter module form.
  # When running as a frozen bundle, sys.executable is the bundled exe: use the bundle's --run-cli entry instead.
  if getattr(sys, 'frozen', False):
    # The bundle supports: MercuryScribe.exe --run-cli <args...>
    cmd: List[str] = [sys.executable, "--run-cli"]
    # Tag the invocation so the CLI can adjust behavior
    cmd.append("--called-by-mercuryweb")
    # Add speaker constraint flags after the portal flag below
  else:
    cmd: List[str] = [
        sys.executable, "-m", "transcribe_with_whisper.main", "--called-by-mercuryweb"
    ]

  # Add speaker constraint flags
  if num_speakers is not None:
    cmd.extend(["--num-speakers", str(num_speakers)])
  elif min_speakers is not None or max_speakers is not None:
    if min_speakers is not None:
      cmd.extend(["--min-speakers", str(min_speakers)])
    if max_speakers is not None:
      cmd.extend(["--max-speakers", str(max_speakers)])

  # Add filename (always after flags)
  cmd.append(filename)

  # Add speaker names
  if speakers:
    cmd.extend(speakers)

  return cmd


_REQUIRED_MODELS_CACHE: Optional[List[Dict[str, str]]] = None


def _determine_pyannote_major() -> int:
  """Return the detected pyannote.audio major version (default to 4 if unavailable)."""
  try:
    import pyannote.audio  # type: ignore

    version = getattr(pyannote.audio, "__version__", "4.0.0")
    major = int(str(version).split(".")[0])
    return major if major > 0 else 4
  except Exception:
    return 4


def _get_required_hf_models() -> List[Dict[str, str]]:
  """Determine the set of Hugging Face repositories required for the current pyannote stack."""
  global _REQUIRED_MODELS_CACHE
  if _REQUIRED_MODELS_CACHE is not None:
    return _REQUIRED_MODELS_CACHE

  major = _determine_pyannote_major()
  models: List[Dict[str, str]] = [{
      "name": "pyannote/speaker-diarization-community-1",
      "url": "https://huggingface.co/pyannote/speaker-diarization-community-1",
      "description": "Speaker diarization checkpoints for pyannote.audio",
      "probe_filename": "config.yaml",
  }]

  if major < 4:
    models.append({
        "name": "pyannote/speaker-diarization-3.1",
        "url": "https://huggingface.co/pyannote/speaker-diarization-3.1",
        "description": "Legacy diarization pipeline used with pyannote.audio 3.x",
        "probe_filename": "config.yaml",
    })

  models.append({
      "name": "pyannote/segmentation-3.0",
      "url": "https://huggingface.co/pyannote/segmentation-3.0",
      "description": "Voice activity segmentation for pyannote.audio",
      "probe_filename": "config.yaml",
  })

  _REQUIRED_MODELS_CACHE = models
  return models


def _render_setup_html() -> str:
  """Render the setup page HTML with the correct model list injected."""
  models = _get_required_hf_models()

  list_items = []
  for model in models:
    description = model.get("description")
    desc_suffix = f" – {description}" if description else ""
    list_items.append(
        f'        <li><a href="{model["url"]}" target="_blank">{model["name"]}</a>{desc_suffix}</li>'
    )

  model_json = json.dumps([{
      "name": model["name"],
      "url": model["url"],
      "reason": model.get("description", "access required"),
  } for model in models])

  html = SETUP_HTML
  html = html.replace("__MODEL_LIST_ITEMS__", "\n".join(list_items))
  html = html.replace("__MODEL_JSON__", model_json)
  return _apply_branding(html)


def _probe_model_access(model: Dict[str, str], token: str) -> Optional[str]:
  """Attempt to access a representative file in the model repo to verify gating status."""
  filename = model.get("probe_filename", "config.yaml")
  try:
    # Download into an isolated temp directory so cached artifacts from previous tokens don't mask permission errors
    with tempfile.TemporaryDirectory(prefix="hf_probe_") as tmpdir:
      hf_hub_download(
          repo_id=model["name"],
          filename=filename,
          token=token,
          force_download=True,
          cache_dir=tmpdir,
          local_files_only=False,
      )
    return None
  except GatedRepoError:
    return "access denied - you may need to accept the license"
  except Exception as exc:
    return f"error fetching probe file '{filename}': {exc}"


def _validate_hf_token_or_die() -> None:
  token = _prime_token_env()
  if not token:
    raise RuntimeError("HUGGING_FACE_AUTH_TOKEN is not set. Set it before starting the server.")
  try:
    api = HfApi()
    missing_models = []
    for model in _get_required_hf_models():
      try:
        api.model_info(model["name"], token=token)
      except Exception as exc:
        missing_models.append(f"{model['name']} (error: {exc})")
        continue

      probe_issue = _probe_model_access(model, token)
      if probe_issue:
        missing_models.append(f"{model['name']} ({probe_issue})")
    if missing_models:
      raise RuntimeError(
          "Hugging Face token validation failed. Missing access to required models: " +
          "; ".join(missing_models))
    print("✅ Hugging Face token validated (all required models accessible).")
  except Exception as e:
    raise RuntimeError(
        "Hugging Face token validation failed. Ensure the token is valid and has access to the required models. "
        "Original error: " + str(e))


def _validate_hf_token(token: str) -> dict:
  """Validate a Hugging Face token and return validation result"""
  if not token:
    return {"valid": False, "error": "Token is empty"}

  if not token.startswith("hf_"):
    return {"valid": False, "error": "Invalid token format. HuggingFace tokens start with 'hf_'"}

  try:
    api = HfApi()

    # Test basic API access first
    try:
      # This should work with any valid token
      api.whoami(token=token)
    except Exception as e:
      return {"valid": False, "error": f"Invalid token or API access denied: {str(e)}"}

    # Test access to required models
    missing_models = []
    requires_license_acceptance = False

    for model in _get_required_hf_models():
      try:
        api.model_info(model["name"], token=token)
      except Exception as e:
        error_msg = str(e).lower()
        if "not found" in error_msg or "repository not found" in error_msg:
          reason = "repository not found"
        elif "access" in error_msg or "forbidden" in error_msg or "401" in error_msg:
          reason = "access denied - you may need to accept the license"
          requires_license_acceptance = True
        else:
          reason = f"error: {str(e)}"

        missing_models.append({
            "name": model["name"],
            "url": model["url"],
            "reason": reason,
        })
        continue

      probe_issue = _probe_model_access(model, token)
      if probe_issue:
        if "access denied" in probe_issue:
          requires_license_acceptance = True
        missing_models.append({
            "name": model["name"],
            "url": model["url"],
            "reason": probe_issue,
        })

    if missing_models:
      missing_names = "; ".join(f"{model['name']} ({model['reason']})" for model in missing_models)
      return {
          "valid": False,
          "error": f"Cannot access required models: {missing_names}",
          "missing_models": missing_models,
          "requires_license_acceptance": requires_license_acceptance,
      }

    return {
        "valid": True,
        "message": "Token validated successfully. All required models accessible.",
        "missing_models": [],
    }

  except Exception as e:
    return {
        "valid": False,
        "error": f"Unexpected validation error: {str(e)}",
        "missing_models": [],
    }


def _has_valid_token() -> bool:
  """Check if a valid token exists (graceful version that doesn't crash)"""
  token = _prime_token_env()
  if not token:
    return False

  result = _validate_hf_token(token)
  return result.get("valid", False)


def _human_size(n: int) -> str:
  for unit in ["B", "KB", "MB", "GB", "TB"]:
    if n < 1024:
      return f"{n:.0f} {unit}"
    n /= 1024
  return f"{n:.0f} PB"


def _list_dir_entries(path: Path) -> Iterable[Path]:
  return sorted([p for p in path.iterdir() if p.is_file()], key=lambda p: p.name.lower())


def _get_audio_duration(file_path: Path) -> Optional[float]:
  """Get duration of audio/video file in seconds"""
  try:
    if _HAS_PYDUB:
      # Try pydub first (more reliable for various formats)
      audio = AudioSegment.from_file(str(file_path))
      return len(audio) / 1000.0  # Convert ms to seconds
    else:
      # Fallback to ffprobe if pydub not available
      result = subprocess.run([
          'ffprobe', '-v', 'quiet', '-show_entries', 'format=duration', '-of',
          'default=noprint_wrappers=1:nokey=1',
          str(file_path)
      ],
                              capture_output=True,
                              text=True)
      if result.returncode == 0 and result.stdout.strip():
        return float(result.stdout.strip())
  except Exception:
    pass
  return None


def _format_duration(seconds: float) -> str:
  """Format duration in seconds to MM:SS format"""
  minutes = int(seconds // 60)
  secs = int(seconds % 60)
  return f"{minutes}:{secs:02d}"


def _format_elapsed_time(start_time: float) -> str:
  """Format elapsed time since start_time"""
  elapsed = time.time() - start_time
  if elapsed < 60:
    return f"{elapsed:.0f}s"
  else:
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)
    return f"{minutes}m {seconds}s"


def _update_progress_from_output(job_id: str, line: str):
  """Parse CLI output line and update job progress"""
  global jobs

  if job_id not in jobs:
    return

  line = line.strip()
  if not line:
    return

  # Progress estimation based on recognizable output patterns
  try:
    # Phase 1: Initial setup and preflight (5-10%)
    if "Running preflight checks" in line:
      jobs[job_id]["progress"] = 5
      jobs[job_id]["message"] = "Running preflight checks..."
    elif "ffmpeg found:" in line:
      jobs[job_id]["progress"] = 7
      jobs[job_id]["message"] = "Checking system dependencies..."
    elif "All checks passed" in line:
      jobs[job_id]["progress"] = 10
      jobs[job_id]["message"] = "System checks complete..."

    # Phase 2: Audio processing (10-20%)
    elif "Input #0" in line and ("mp3" in line or "mp4" in line or "wav" in line):
      jobs[job_id]["progress"] = 12
      jobs[job_id]["message"] = "Reading input audio/video..."
    elif "ffmpeg" in line and "size=" in line and "time=" in line:
      jobs[job_id]["progress"] = 18
      jobs[job_id]["message"] = "Converting audio format..."

    # Phase 3: AI model loading (20-25%)
    elif "Loading Whisper model" in line:
      jobs[job_id]["progress"] = 22
      jobs[job_id]["message"] = "Loading Whisper AI model..."
    elif "Pipeline.from_pretrained" in line or "pyannote" in line:
      jobs[job_id]["progress"] = 25
      # Enhanced message with file duration
      file_duration = jobs[job_id].get("file_duration", "Unknown duration")
      duration_str = _format_duration(
          file_duration) if file_duration != "Unknown duration" else file_duration
      jobs[job_id][
          "message"] = f"Loading speaker diarization model for {duration_str} audio file..."

    # Phase 4: Speaker diarization (25-50%) - Longest phase
    elif "DEMO_FILE" in line or "diarization" in line.lower():
      # Check for specific diarization progress steps
      if "Diarization progress:" in line:
        # Parse chunk progress like "processing chunk 50/200 (25%)"
        if "processing chunk" in line and "/" in line:
          try:
            # Extract percentage from the message
            percent_match = re.search(r'\((\d+)%\)', line)
            if percent_match:
              chunk_percent = int(percent_match.group(1))
              # Map 0-100% chunk progress to 30-45% overall progress
              mapped_progress = 30 + (chunk_percent * 0.15)  # 15% of total progress
              jobs[job_id]["progress"] = min(int(mapped_progress), 45)
              jobs[job_id]["message"] = f"Speaker diarization: {chunk_percent}% complete..."
          except (ValueError, AttributeError):
            pass
        else:
          # Step-level progress messages
          step_name = line.split("Diarization progress:")[-1].strip()
          # Map common steps to progress percentages
          step_progress_map = {
              "segmentation": 30,
              "speaker_embedding": 35,
              "embeddings": 40,
              "clustering": 45,
          }
          for keyword, progress in step_progress_map.items():
            if keyword in step_name.lower():
              jobs[job_id]["progress"] = progress
              jobs[job_id]["message"] = f"Speaker diarization: {step_name}..."
              break
          else:
            # Generic diarization progress
            current = jobs[job_id]["progress"]
            if current < 50:
              jobs[job_id]["progress"] = min(current + 2, 50)
              jobs[job_id]["message"] = f"Speaker diarization: {step_name}..."
      else:
        jobs[job_id]["progress"] = 30
        # Enhanced message with file duration and elapsed time
        file_duration = jobs[job_id].get("file_duration", "Unknown duration")
        start_time = jobs[job_id].get("start_time", time.time())
        elapsed_time = time.time() - start_time

        duration_str = _format_duration(
            file_duration) if file_duration != "Unknown duration" else file_duration
        elapsed_str = _format_elapsed_time(elapsed_time)

        jobs[job_id][
            "message"] = f"Running speaker diarization AI on {duration_str} audio file... (elapsed: {elapsed_str})"
    elif "Detected speakers:" in line:
      jobs[job_id]["progress"] = 50
      # Extract speaker information for better UX
      if "[" in line and "]" in line:
        speaker_part = line.split("Detected speakers:")[1].strip()
        jobs[job_id]["message"] = f"Speaker diarization complete - {speaker_part}"
      else:
        jobs[job_id]["message"] = "Speaker diarization complete..."

    # Phase 5: Segment transcription (50-80%)
    # Now we get real progress from "Transcribing segment X/Y" messages
    elif "Transcribing segment" in line and "/" in line:
      try:
        # Extract current/total from "Transcribing segment 3/10: 0.wav"
        segment_part = line.split("Transcribing segment")[1].strip()
        current, total = segment_part.split(":")[0].split("/")
        current_num = int(current.strip())
        total_num = int(total.strip())

        # Map segment progress to 50-80% range
        segment_progress = (current_num / total_num) * 100
        mapped_progress = 50 + (segment_progress * 0.30)  # 30% of total progress
        jobs[job_id]["progress"] = min(int(mapped_progress), 80)
        jobs[job_id]["message"] = f"Transcribing segment {current_num}/{total_num}..."
      except (ValueError, IndexError):
        # Fallback if parsing fails
        current = jobs[job_id]["progress"]
        jobs[job_id]["progress"] = min(current + 2, 80)
        jobs[job_id]["message"] = "Transcribing audio segments..."

    elif "Completed segment" in line and "/" in line:
      try:
        # Extract current/total from "Completed segment 3/10"
        segment_part = line.split("Completed segment")[1].strip()
        current, total = segment_part.split("/")
        current_num = int(current.strip())
        total_num = int(total.strip())

        # Map segment progress to 50-80% range
        segment_progress = (current_num / total_num) * 100
        mapped_progress = 50 + (segment_progress * 0.30)
        jobs[job_id]["progress"] = min(int(mapped_progress), 80)
      except (ValueError, IndexError):
        pass

    # Phase 6: HTML generation (80-95%)
    elif "generate_html" in line or "Script completed successfully" in line:
      jobs[job_id]["progress"] = 90
      jobs[job_id]["message"] = "Generating HTML transcript..."
    elif "Output:" in line and ".html" in line:
      jobs[job_id]["progress"] = 95
      jobs[job_id]["message"] = "Transcription complete, preparing files..."

    # Error detection
    elif any(error_word in line.upper()
             for error_word in ["ERROR", "FAILED", "EXCEPTION", "TRACEBACK"]):
      # Skip common non-fatal warnings that might contain these words
      norm_line = line.lower()
      skip_warnings = [
          "torchcodec", "libtorchcodec", "userwarning", "futurewarning", "deprecationwarning",
          "skipping copy", "branding assets not found", "ffmpeg version", "libavutil",
          "libpython", "loading traceback", "not installed correctly"
      ]
      if any(skip in norm_line for skip in skip_warnings):
        pass
      else:
        jobs[job_id]["message"] = f"Error: {line[:100]}..."

    # Progress safety: Ensure we never go backwards and don't stall
    else:
      current_progress = jobs[job_id]["progress"]
      # Very gradual increment for any other output (prevents stalling)
      if current_progress < 85 and len(line) > 10:  # Only for substantive output
        jobs[job_id]["progress"] = min(current_progress + 0.5, 85)

  except Exception:
    # Don't let progress parsing errors break the job
    pass


def _run_transcription_job(job_id: str,
                           filename: str,
                           speakers: Optional[List[str]],
                           num_speakers: Optional[int] = None,
                           min_speakers: Optional[int] = None,
                           max_speakers: Optional[int] = None):
  global jobs
  try:
    # Store basename for VTT progress tracking
    basename = Path(filename).stem
    jobs[job_id]["basename"] = basename
    jobs[job_id]["status"] = "running"
    jobs[job_id]["message"] = "Starting transcription..."
    jobs[job_id]["progress"] = 5

    cmd = _build_cli_cmd(filename, speakers or None, num_speakers, min_speakers, max_speakers)

    # Debug logging
    exe_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.getcwd()
    log_path = os.path.join(exe_dir, "bundle_run.log")
    with open(log_path, "a", encoding="utf-8") as fh:
      fh.write(f"[_run_transcription_job] job_id: {job_id}, filename: {filename}, cmd: {cmd}\n")

    # Use Popen for real-time output monitoring
    import subprocess
    import threading

    # Prepare environment with token
    env = os.environ.copy()
    token = _prime_token_env()
    if token:
      env["HUGGING_FACE_AUTH_TOKEN"] = token

    # Ensure bundled ffmpeg is in PATH for subprocess
    if getattr(sys, 'frozen', False):
      exe_dir = Path(sys.executable).resolve().parent
      internal_dir = exe_dir / "_internal"
      current_path = env.get("PATH", "")
      env["PATH"] = f"{exe_dir}{os.pathsep}{internal_dir}{os.pathsep}{current_path}"

    proc = subprocess.Popen(cmd,
                            cwd=str(TRANSCRIPTION_DIR),
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True,
                            bufsize=1,
                            universal_newlines=True,
                            env=env)

    # Monitor output in real-time
    output_lines = []

    def monitor_output():
      nonlocal output_lines
      for line in iter(proc.stdout.readline, ''):
        if line:
          output_lines.append(line.strip())
          _update_progress_from_output(job_id, line.strip())

    monitor_thread = threading.Thread(target=monitor_output)
    monitor_thread.daemon = True
    monitor_thread.start()

    # Wait for process to complete
    proc.wait()
    monitor_thread.join(timeout=1)  # Give thread a moment to finish

    if proc.returncode != 0:
      jobs[job_id]["status"] = "error"
      jobs[job_id]["message"] = f"CLI failed with code {proc.returncode}"
      jobs[job_id]["error"] = "OUTPUT:\n" + "\n".join(output_lines)
      return

    jobs[job_id]["progress"] = 80

    basename = Path(filename).stem
    html_out = TRANSCRIPTION_DIR / f"{basename}.html"
    if not html_out.exists():
      candidates = sorted(TRANSCRIPTION_DIR.glob("*.html"),
                          key=lambda p: p.stat().st_mtime,
                          reverse=True)
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
      try:
        from transcribe_with_whisper.html_to_docx import \
          convert_html_file_to_docx
      except Exception as import_exc:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["message"] = ("DOCX generation failed: required Python packages are missing. "
                                   "Install with: pip install python-docx")
        jobs[job_id]["error"] = f"Import error for html_to_docx: {import_exc}"
        print(f"⚠️ DOCX generation unavailable: {import_exc}")
        return

      try:
        convert_html_file_to_docx(html_out, docx_out)
        print(f"✅ Generated DOCX (shared): {docx_out.name}")
      except Exception as py_exc:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["message"] = "DOCX generation failed during conversion"
        jobs[job_id]["error"] = f"Conversion error: {py_exc}"
        print(f"⚠️ DOCX conversion failed: {py_exc}")
    except Exception as e:
      print(f"⚠️ DOCX generation failed: {e}")

    jobs[job_id]["status"] = "completed"
    jobs[job_id]["progress"] = 100
    jobs[job_id]["end_time"] = time.time()

    # Calculate elapsed time for logging
    # elapsed = jobs[job_id]["end_time"] - jobs[job_id].get("start_time", jobs[job_id]["end_time"])
    elapsed_str = _format_elapsed_time(jobs[job_id].get("start_time", jobs[job_id]["end_time"]))
    end_time_str = datetime.fromtimestamp(jobs[job_id]["end_time"]).strftime("%I:%M:%S %p")

    jobs[job_id][
        "message"] = f"Transcription completed! (Finished at {end_time_str}, took {elapsed_str})"
    jobs[job_id]["result"] = f"/files/{html_out.name}"

    print(f"✅ Transcription completed at {end_time_str}")
    print(f"⏱️  Total elapsed time: {elapsed_str}")
  except Exception as e:
    jobs[job_id]["status"] = "error"
    jobs[job_id]["message"] = f"Failed to run transcription: {e}"


@app.post("/upload")
async def upload(file: UploadFile = File(...),
                 speaker: Optional[List[str]] = Form(default=None),
                 num_speakers: Optional[str] = Form(default=None),
                 min_speakers: Optional[str] = Form(default=None),
                 max_speakers: Optional[str] = Form(default=None)):
  global job_counter, jobs
  if not _prime_token_env():
    return PlainTextResponse("HUGGING_FACE_AUTH_TOKEN not set. Set it when running the server.",
                             status_code=500)

  dest_path = TRANSCRIPTION_DIR / file.filename
  with dest_path.open("wb") as out:
    shutil.copyfileobj(file.file, out)

  job_counter += 1
  job_id = str(job_counter)
  speakers = [s.strip() for s in (speaker or []) if s and s.strip()]

  # Parse and validate speaker constraints (handle empty strings from form)
  num_speakers_int = None
  min_speakers_int = None
  max_speakers_int = None

  try:
    if num_speakers and num_speakers.strip():
      num_speakers_int = int(num_speakers)
    if min_speakers and min_speakers.strip():
      min_speakers_int = int(min_speakers)
    if max_speakers and max_speakers.strip():
      max_speakers_int = int(max_speakers)
  except ValueError as e:
    return PlainTextResponse(f"Invalid speaker number: {e}", status_code=400)

  # Get audio duration for progress feedback
  file_duration = _get_audio_duration(dest_path)

  jobs[job_id] = {
      "status": "starting",
      "progress": 0,
      "message": "Preparing transcription...",
      "filename": file.filename,
      "start_time": time.time(),
      "file_duration": file_duration,
  }

  thread = threading.Thread(target=_run_transcription_job,
                            args=(job_id, file.filename, speakers, num_speakers_int,
                                  min_speakers_int, max_speakers_int))
  thread.daemon = True
  thread.start()

  return RedirectResponse(url=f"/progress/{job_id}", status_code=303)


@app.get("/list", response_class=HTMLResponse)
async def list_files(_: Request):
  files = _list_dir_entries(TRANSCRIPTION_DIR)
  rows = []
  media_exts = {".mp4", ".m4a", ".wav", ".mp3", ".mkv", ".mov"}
  vtt_dir = TRANSCRIPTION_DIR / "vtt"
  for p in files:
    name = p.name
    size = _human_size(p.stat().st_size)
    mtime = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    actions = []

    # HTML outputs: View (and Edit/Regenerate if VTTs exist)
    if p.suffix.lower() == ".html":
      actions.append(f'<a href="/files/{name}">View</a>')
      basename = p.stem
      # vtt_dir = TRANSCRIPTION_DIR / basename

    # Media inputs: allow Re-run
    if p.suffix.lower() in media_exts:
      actions.append(
          f'<form method="post" action="/rerun" style="display:inline">'
          f'<input type="hidden" name="filename" value="{name}">' \
          f'<button type="submit">Process</button></form>'
      )

    # Download links (strong for DOCX)
    if p.suffix.lower() == ".docx":
      actions.append(f'<a href="/files/{name}" download><strong>📄 Download DOCX</strong></a>')
    else:
      actions.append(f'<a href="/files/{name}" download>Download</a>')

    rows.append(
        f"<tr><td>{name}</td><td style='text-align:right'>{size}</td><td>{mtime}</td><td>{' | '.join(actions)}</td></tr>"
    )

  html = _apply_branding(f"""
<!doctype html>
<html>
  <head>
  <meta charset='utf-8'>
  <meta name='viewport' content='width=device-width, initial-scale=1'>
  <title>Available Files</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ padding: .5rem; border-bottom: 1px solid #eee; }}
    th {{ text-align: left; }}
  </style>
  </head>
  <body>
  <h1>Available Files</h1>
  <p><a href='/'>⬅ Upload</a></p>
  <table>
    <thead><tr><th>File</th><th style='text-align:right'>Size</th><th>Modified</th><th>Actions</th></tr></thead>
    <tbody>
      {''.join(rows)}
    </tbody>
  </table>
  </body>
</html>
""")
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

  # Get audio duration for progress feedback
  file_duration = _get_audio_duration(target)

  jobs[job_id] = {
      "status": "starting",
      "progress": 0,
      "message": "Preparing transcription...",
      "filename": filename,
      "start_time": time.time(),
      "file_duration": file_duration,
  }

  thread = threading.Thread(target=_run_transcription_job,
                            args=(job_id, target.name, None, None, None, None))
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
  """Save in-place edited transcript changes back to VTT files"""

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
        print(
            f"[DEBUG] Change: vttFile='{vtt_file}', captionIdx='{caption_idx_str}', text='{new_text[:50]}...'"
        )

      # Validate that we have the required VTT-specific information
      if not vtt_file or not caption_idx_str:
        if debug:
          print("[DEBUG] Missing VTT info, skipping change")
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
        failed.append({"error": f"Invalid captionIdx: {caption_idx_str}", "change": change})
        continue

      # Locate the specific VTT file
      vtt_path = vtt_dir / vtt_file
      if not vtt_path.exists():
        if debug:
          print(f"[DEBUG] VTT file not found: {vtt_path}")
        failed.append({"error": f"VTT file not found: {vtt_file}", "change": change})
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
        failed.append({"error": f"Error processing {vtt_file}: {str(e)}", "change": change})

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
    # existing_config_path: Optional[Path] = None
    for cand in config_candidates:
      if cand.exists():
        try:
          with open(cand, "r", encoding="utf-8") as f:
            existing_config = json.load(f)
            # existing_config_path = cand
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
        vtt_ids = sorted([p.stem for p in vtt_dir.glob("*.vtt") if p.stem.isdigit()],
                         key=lambda x: int(x))
        if vtt_ids:
          # Map provided new names onto track ids in order; if mapping fewer,
          # reuse last; if more, ignore extras
          new_names = list(speakers_mapping.values())
          for i, sid in enumerate(vtt_ids):
            name = new_names[i] if i < len(new_names) else f"Speaker {int(sid)+1}"
            speakers_by_id[sid] = {"name": name, "bgcolor": "lightgray", "textcolor": "darkorange"}
      # As a fallback, create a single default if nothing detected
      if not speakers_by_id:
        speakers_by_id["0"] = {
            "name": next(iter(speakers_mapping.values())),
            "bgcolor": "lightgray",
            "textcolor": "darkorange"
        }

    # Apply mapping: rename by matching current names to keys in provided mapping
    for sid, info in speakers_by_id.items():
      current = info.get("name", sid)
      if current in speakers_mapping:
        info["name"] = speakers_mapping[current]

    # Choose config path: prefer per-video directory
    config_path = (vtt_dir / f"{basename}-speakers.json") if vtt_dir.exists() else (
        TRANSCRIPTION_DIR / f"{basename}-speakers.json")
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

    return {"success": True, "message": "Transcript saved successfully"}
  except Exception as e:
    return {"success": False, "error": str(e)}


def main() -> None:
  """Run the MercuryScribe web server via uvicorn."""
  import uvicorn

  # Set web server mode to enable graceful startup without token
  os.environ["WEB_SERVER_MODE"] = "1"

  host = os.getenv("HOST", "0.0.0.0")
  port = int(os.getenv("PORT", "5001"))
  uvicorn.run(app, host=host, port=port, reload=False)


if __name__ == "__main__":
  main()
