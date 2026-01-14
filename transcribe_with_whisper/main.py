import argparse
import base64
import html as html_module
import importlib
import os
import platform
import re
import shlex
import subprocess
import sys
import warnings
from functools import lru_cache
from pathlib import Path

from transcribe_with_whisper import ensure_preflight

ensure_preflight()

import webvtt
from faster_whisper import WhisperModel
from pyannote.audio import Pipeline
from pydub import AudioSegment

try:
  from importlib.metadata import PackageNotFoundError
  from importlib.metadata import version as pkg_version
except ImportError:  # pragma: no cover - fallback for Python <3.8
  from importlib_metadata import PackageNotFoundError
  from importlib_metadata import version as pkg_version  # type: ignore
try:
  import torchaudio  # type: ignore
  _HAS_TORCHAUDIO = True
except Exception:
  _HAS_TORCHAUDIO = False

# Check pyannote.audio version for API compatibility
try:
  import pyannote.audio
  _PYANNOTE_VERSION = pyannote.audio.__version__
  _PYANNOTE_MAJOR = int(_PYANNOTE_VERSION.split('.')[0])
except Exception:
  # Fallback: assume version 4.x if import fails
  _PYANNOTE_MAJOR = 4

warnings.filterwarnings("ignore", message="Model was trained with")
warnings.filterwarnings("ignore", message="Lightning automatically upgraded")
warnings.filterwarnings("ignore", message=".*StreamingMediaDecoder has been deprecated.*")
warnings.filterwarnings("ignore", category=UserWarning, module="torchaudio._backend.ffmpeg")


@lru_cache(maxsize=1)
def _find_bundled_ffmpeg() -> str | None:
  """Find the bundled ffmpeg executable if running from a PyInstaller bundle."""
  if not getattr(sys, 'frozen', False):
    return None

  exe_dir = Path(sys.executable).resolve().parent
  internal_dir = exe_dir / "_internal"

  # Check common locations for bundled ffmpeg
  candidates = [
      exe_dir / "ffmpeg.exe",  # Windows
      exe_dir / "ffmpeg",  # Linux/macOS
      internal_dir / "ffmpeg.exe",
      internal_dir / "ffmpeg",
  ]

  for candidate in candidates:
    if candidate.exists() and candidate.is_file():
      return str(candidate)

  return None


@lru_cache(maxsize=1)
def _get_embedded_favicon_data_uri() -> str | None:
  """Return the data URI for the bundled square logo favicon."""
  logo_path = Path(
      __file__).resolve().parent.parent / "branding" / "icon-square.png"
  if not logo_path.exists():
    return None

  try:
    svg_bytes = logo_path.read_bytes()
  except OSError as exc:
    print(f"⚠️ Unable to read favicon asset: {exc}")
    return None

  encoded = base64.b64encode(svg_bytes).decode("ascii")
  return f"data:image/png;base64,{encoded}"


def is_apple_silicon() -> bool:
  """Return True when running on an Apple Silicon Mac."""
  return platform.system() == "Darwin" and platform.machine().lower() in {"arm64", "aarch64"}


def _torch_mps_available() -> bool:
  """Detect whether PyTorch Metal (MPS) backend is available."""
  try:
    import torch  # type: ignore

    mps_backend = getattr(torch.backends, "mps", None)
    if mps_backend is None:
      return False
    return bool(getattr(mps_backend, "is_available", lambda: False)())
  except Exception:
    return False


def _maybe_move_pipeline_to_mps(pipeline) -> bool:
  """Attempt to move a pyannote Pipeline to the MPS device if available."""
  if not is_apple_silicon() or not _torch_mps_available():
    return False

  try:
    import torch  # type: ignore

    pipeline.to(torch.device("mps"))
    print("⚡️ Using Apple Metal (MPS) acceleration for diarization.")
    return True
  except AttributeError:
    # Pipeline does not expose .to(); ignore silently
    return False
  except Exception as exc:
    print(f"⚠️ Could not enable MPS for pyannote pipeline: {exc}")
    return False


def _has_coreml_extension() -> bool:
  """Check whether the installed faster-whisper build exposes the CoreML extension."""
  try:
    ext_module = importlib.import_module("ctranslate2._ext")  # type: ignore[import]
  except ModuleNotFoundError:
    return False
  except Exception:
    return False
  return hasattr(ext_module, "coreml")


def create_whisper_model(
    model_size: str,
    device: str | None = None,
    compute_type: str | None = None,
    coreml_units: str | None = None,
):
  """Instantiate WhisperModel with sensible defaults and optional CoreML acceleration."""
  requested_device = (device or "auto").lower()
  requested_compute_type = compute_type or "auto"
  requested_coreml_units = coreml_units.lower() if coreml_units else None

  if requested_coreml_units and not _has_coreml_extension():
    print("⚠️ CoreML compute units were requested but faster-whisper[coreml] isn't installed. "
          "Install it on Apple Silicon to enable CoreML acceleration.")
    requested_coreml_units = None

  model_kwargs: dict[str, str] = {}
  attempted_coreml = False

  if requested_coreml_units:
    attempted_coreml = True
    model_kwargs["coreml_compute_units"] = requested_coreml_units
    if requested_device == "auto":
      requested_device = "cpu"
    if requested_compute_type in (None, "auto", "default"):
      requested_compute_type = "int8"
  elif requested_device == "auto" and is_apple_silicon() and _has_coreml_extension():
    attempted_coreml = True
    requested_device = "cpu"
    if requested_compute_type in (None, "auto", "default"):
      requested_compute_type = "int8"
    requested_coreml_units = "all"
    model_kwargs["coreml_compute_units"] = requested_coreml_units
    print("🍎 Apple Silicon detected; enabling CoreML acceleration (compute_units=all).")

  resolved_coreml_units = model_kwargs.get("coreml_compute_units")

  try:
    model = WhisperModel(
        model_size,
        device=requested_device,
        compute_type=requested_compute_type,
        **model_kwargs,
    )
  except Exception as exc:
    if attempted_coreml:
      print(f"⚠️ CoreML acceleration request failed ({exc}). "
            "Falling back to default Whisper settings.")
      model_kwargs = {}
      resolved_coreml_units = None
      model = WhisperModel(model_size,
                           device=(device or "auto"),
                           compute_type=(compute_type or "auto"))
    else:
      raise

  actual_device = getattr(model.model, "device", requested_device)
  actual_compute = getattr(model.model, "compute_type", requested_compute_type)
  print(
      f"Loaded Whisper model '{model_size}' on device={actual_device} (compute_type={actual_compute})"
  )
  if resolved_coreml_units:
    print(f"CoreML compute units: {resolved_coreml_units}")

  return model


def get_package_version() -> str:
  """Return the project version from local metadata or installed package."""
  distribution_name = "transcribe-with-whisper"

  setup_path = Path(__file__).resolve().parent.parent / "setup.py"
  if setup_path.exists():
    match = re.search(r"version\s*=\s*['\"]([^'\"]+)['\"]", setup_path.read_text(encoding="utf-8"))
    if match:
      return match.group(1)

  try:
    return pkg_version(distribution_name)
  except PackageNotFoundError:
    try:
      from pkg_resources import get_distribution  # type: ignore

      return get_distribution(distribution_name).version
    except Exception:
      return "unknown"


def millisec(timeStr):
  spl = timeStr.split(":")
  s = int((int(spl[0]) * 3600 + int(spl[1]) * 60 + float(spl[2])) * 1000)
  return s


def format_time(seconds):
  hours = int(seconds // 3600)
  minutes = int((seconds % 3600) // 60)
  secs = seconds % 60
  return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"


def convert_to_wav(inputfile, outputfile):
  import os
  abs_input = os.path.abspath(inputfile)
  abs_output = os.path.abspath(outputfile)
  exe_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.getcwd()
  log_path = os.path.join(exe_dir, "convert_to_wav.log")

  def log(msg):
    with open(log_path, "a", encoding="utf-8") as fh:
      fh.write(msg + "\n")

  log(f"[convert_to_wav] cwd: {os.getcwd()}")
  log(f"[convert_to_wav] inputfile: {inputfile}, abs: {abs_input}, exists: {os.path.isfile(inputfile)}"
      )
  log(f"[convert_to_wav] outputfile: {outputfile}, abs: {abs_output}, will create: {not os.path.isfile(outputfile)}"
      )
  # On Windows, ffmpeg should handle both / and \\ in paths, but always use abs path for safety
  input_arg = abs_input
  output_arg = abs_output
  if not os.path.isfile(outputfile):
    ffmpeg_cmd = _find_bundled_ffmpeg() or "ffmpeg"
    log(f"[convert_to_wav] using ffmpeg: {ffmpeg_cmd}")
    try:
      result = subprocess.run([ffmpeg_cmd, "-i", input_arg, output_arg])
      log(f"[convert_to_wav] ffmpeg exited with code {result.returncode}")
      if result.returncode != 0:
        log(f"[convert_to_wav] ffmpeg stderr: {result.stderr}")
    except FileNotFoundError as e:
      log(f"[convert_to_wav] ffmpeg command not found: {e}")
      raise
    except Exception as e:
      log(f"[convert_to_wav] unexpected error: {e}")
      raise


def create_spaced_audio(inputWav, outputWav, spacer_ms=2000):
  audio = AudioSegment.from_wav(inputWav)
  spacer = AudioSegment.silent(duration=spacer_ms)
  audio = spacer.append(audio, crossfade=0)
  audio.export(outputWav, format="wav")


def get_diarization(inputWav,
                    diarizationFile,
                    num_speakers=None,
                    min_speakers=None,
                    max_speakers=None):
  auth_token = os.getenv("HUGGING_FACE_AUTH_TOKEN")
  if not auth_token:
    raise ValueError("HUGGING_FACE_AUTH_TOKEN environment variable is required")

  # Use appropriate API based on pyannote.audio version
  if _PYANNOTE_MAJOR >= 4:
    # pyannote.audio 4.0.0+ API
    pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-community-1",
                                        token=auth_token)
  else:
    # pyannote.audio 3.x API
    pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1",
                                        use_auth_token=auth_token)

  _maybe_move_pipeline_to_mps(pipeline)

  if not os.path.isfile(diarizationFile):
    # Add progress hook to report diarization progress
    def progress_hook(step_name=None, step_artifact=None, file=None, total=None, completed=None):
      """Progress callback for diarization pipeline"""
      if completed is not None and total is not None:
        # This is chunk progress during inference
        percent = int((completed / total) * 100) if total > 0 else 0
        print(f"Diarization progress: processing chunk {completed}/{total} ({percent}%)",
              flush=True)
      elif step_name:
        # This is step-level progress
        print(f"Diarization progress: {step_name}", flush=True)

    # Build pipeline parameters with speaker constraints
    pipeline_params = {"hook": progress_hook}

    if num_speakers is not None:
      pipeline_params["num_speakers"] = num_speakers
      print(f"Using specified number of speakers: {num_speakers}")
    elif min_speakers is not None or max_speakers is not None:
      if min_speakers is not None:
        pipeline_params["min_speakers"] = min_speakers
        print(f"Using minimum speakers: {min_speakers}")
      if max_speakers is not None:
        pipeline_params["max_speakers"] = max_speakers
        print(f"Using maximum speakers: {max_speakers}")

    if _HAS_TORCHAUDIO:
      # Load audio into memory for faster processing
      waveform, sample_rate = torchaudio.load(inputWav)
      dz = pipeline({"waveform": waveform, "sample_rate": sample_rate}, **pipeline_params)
    else:
      # Fallback to file path if torchaudio is not available
      dz = pipeline({"uri": "blabla", "audio": inputWav}, **pipeline_params)
    # In pyannote.audio 4.0, pipeline returns an object with .speaker_diarization attribute
    diarization = dz.speaker_diarization if hasattr(dz, 'speaker_diarization') else dz
    with open(diarizationFile, "w") as f:
      f.write(str(diarization))
  with open(diarizationFile) as f:
    return f.read().splitlines()


def group_segments(dzs):
  groups, g, lastend = [], [], 0
  for d in dzs:
    if g and g[0].split()[-1] != d.split()[-1]:
      groups.append(g)
      g = []
    g.append(d)
    end = millisec(re.findall(r"[0-9]+:[0-9]+:[0-9]+\.[0-9]+", d)[1])
    if lastend > end:
      groups.append(g)
      g = []
    else:
      lastend = end
  if g:
    groups.append(g)
  return groups


def export_segments_audio(groups, inputWav, spacermilli=2000):
  audio = AudioSegment.from_wav(inputWav)
  segment_files = []
  for idx, g in enumerate(groups):
    start = millisec(re.findall(r"[0-9]+:[0-9]+:[0-9]+\.[0-9]+", g[0])[0])
    end = millisec(re.findall(r"[0-9]+:[0-9]+:[0-9]+\.[0-9]+", g[-1])[1])
    audio[start:end].export(f"{idx}.wav", format="wav")
    segment_files.append(f"{idx}.wav")
  return segment_files


def transcribe_segments(segment_files,
                        model_size="base",
                        device="auto",
                        compute_type="auto",
                        coreml_units=None,
                        speaker_header=False,
                        speaker_inline=True):
  model = create_whisper_model(model_size,
                               device=device,
                               compute_type=compute_type,
                               coreml_units=coreml_units)
  total_segments = len(segment_files)
  for idx, f in enumerate(segment_files, start=1):
    vtt_file = f"{Path(f).stem}.vtt"
    if not os.path.isfile(vtt_file):
      print(f"Transcribing segment {idx}/{total_segments}: {f}", flush=True)
      segments, _ = model.transcribe(f, language="en")
      with open(vtt_file, "w", encoding="utf-8") as out:
        out.write("WEBVTT\n\n")
        for s in segments:
          out.write(f"{format_time(s.start)} --> {format_time(s.end)}\n{s.text.strip()}\n\n")
      print(f"Completed segment {idx}/{total_segments}", flush=True)
  return [f"{Path(f).stem}.vtt" for f in segment_files]


def generate_html(
    outputHtml,
    groups,
    vtt_files,
    inputfile,
    speakers,
    *,
    speaker_section=True,
    speaker_inline=True,
    spacermilli=2000,
    called_by_mercuryweb=False,
    mercury_command: str | None = None,
):
  # video_title is inputfile with no extension
  video_title = os.path.splitext(inputfile)[0]
  html = []
  favicon_href = _get_embedded_favicon_data_uri()
  favicon_tag = f"\n    <link rel=\"icon\" type=\"image/svg+xml\" href=\"{favicon_href}\">" if favicon_href else ""
  generator_source = "mercuryweb" if called_by_mercuryweb else "transcribe-with-whisper"
  generator_meta_tag = f"\n    <meta name=\"generator\" content=\"{generator_source} {get_package_version()}\">"
  command_meta_tag = ""
  section_meta_tag = f"\n    <meta name=\"speaker-section\" content=\"{'true' if speaker_section else 'false'}\">"
  inline_meta_tag = f"\n    <meta name=\"speaker-inline\" content=\"{'true' if speaker_inline else 'false'}\">"
  speaker_meta_tags = ""
  for speaker_id, (speaker_name, bg_color, text_color) in sorted(speakers.items(),
                                                                 key=lambda item: str(item[0])):
    escaped_id = html_module.escape(str(speaker_id), quote=True)
    escaped_name = html_module.escape(speaker_name, quote=True)
    escaped_bg = html_module.escape(bg_color, quote=True)
    escaped_fg = html_module.escape(text_color, quote=True)
    speaker_meta_tags += (
        f"\n    <meta name=\"speaker\" data-id=\"{escaped_id}\" "
        f"data-bg=\"{escaped_bg}\" data-fg=\"{escaped_fg}\" content=\"{escaped_name}\">")
  if mercury_command:
    escaped_command = html_module.escape(mercury_command, quote=True)
    command_meta_tag = f"\n    <meta name=\"mercuryscribe-command\" content=\"{escaped_command}\">"

  preS = f"""<!DOCTYPE html>\n<html lang=\"en\">\n  <head>\n    <meta charset=\"UTF-8\">\n    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n    <meta http-equiv=\"X-UA-Compatible\" content=\"ie=edge\">\n    <title>{inputfile}</title>{favicon_tag}{generator_meta_tag}{command_meta_tag}{section_meta_tag}{inline_meta_tag}{speaker_meta_tags}\n    <style>
        body {{
            font-family: sans-serif;
            font-size: 18px;
            color: #111;
            padding: 0 0 1em 0;
	        background-color: #efe7dd;
        }}
        table {{
             border-spacing: 10px;
        }}
        th {{ text-align: left;}}
        .lt {{
          color: inherit;
          text-decoration: inherit;
        }}
        .l {{
          color: #050;
        }}
        .s {{
            display: inline-block;
        }}
        .c {{
            display: inline-block;
        }}
        .e {{
            border-radius: 20px;
            width: fit-content;
            height: fit-content;
            padding: 5px 30px 5px 30px;
            font-size: 18px;
            display: flex;
            flex-direction: column;
            margin-bottom: 10px;
        }}

        .t {{
            display: inline-block;
        }}
        #video-header {{
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            width: 100%;
            background: #efe7dd;
            z-index: 1000;
            padding: 12px 24px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            display: flex;
            flex-direction: column;
            gap: 12px;
        }}
        #video-header .page-title {{
            text-align: center;
            margin: 0;
            font-size: 1.5rem;
        }}
        .header-main {{
            display: flex;
            align-items: flex-start;
            justify-content: flex-start;
            gap: 16px;
        }}
        .media-wrapper {{
            flex: 0 1 auto;
            display: flex;
            justify-content: flex-start;
        }}
        #player {{
            max-height: min(28vh, 320px);
            width: clamp(280px, 40vw, 540px);
            height: auto;
            border: none;
        }}
        #content {{
            margin-top: max(calc(28vh + 120px), 360px);
        }}
        .timestamp {{
            color: #666;
            font-size: 14px;
            font-weight: bold;
        }}
        .speaker-name {{
            font-weight: bold;
            margin-right: 8px;
        }}
        
        /* Edit mode styles */
        .edit-controls {{
            display: flex;
            flex-direction: column;
            gap: 6px;
            justify-content: flex-start;
            align-items: stretch;
            margin: 0;
        }}
        .edit-btn {{
            background: #007bff;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            cursor: pointer;
            margin: 0;
            font-size: 14px;
            width: 100%;
            text-align: left;
        }}
        .edit-btn:hover {{
            background: #0056b3;
        }}
        .edit-btn.active {{
            background: #28a745;
        }}
        .edit-btn:disabled {{
            background: #6c757d;
            cursor: not-allowed;
        }}
        .save-status {{
            display: inline-block;
            margin-left: 10px;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
        }}
        .save-success {{
            background: #d4edda;
            color: #155724;
        }}
        .save-error {{
            background: #f8d7da;
            color: #721c24;
        }}
        
        /* Editable transcript styles */
        .transcript-segment {{
            position: relative;
        }}
        .transcript-segment.editable {{
            border: 1px dashed #007bff;
            border-radius: 4px;
            margin: 2px 0;
        }}
        .transcript-segment.editable:hover {{
            background-color: #f8f9fa;
        }}
        .transcript-segment.editing {{
            background-color: #fff3cd;
            border: 2px solid #ffc107;
        }}
        .transcript-text {{
            cursor: text;
        }}
        .transcript-segment.editable .transcript-text {{
            min-height: 1.2em;
            padding: 2px 4px;
            border-radius: 2px;
        }}
        .transcript-text[contenteditable="true"] {{
            outline: none;
            background: #fffbf0;
            border: 1px solid #ffc107;
            border-radius: 2px;
        }}
        
        /* Hide server-dependent buttons when viewing as local file */
        .local-file-mode #edit-mode-btn,
        .local-file-mode #edit-speakers-btn,
        .local-file-mode #reprocess-btn,
        .local-file-mode #back-to-list-btn {{
            display: none !important;
        }}

        /* When editing, hide all buttons except Save Changes */
    .editing .edit-controls button {{ display: none !important; }}
    .editing .edit-controls #save-btn {{ display: inline-block !important; }}
    </style>
</head>
  <body>
   """ + f"""
        <div id="video-header" class="html-only">
        <h2 class="page-title">{video_title}</h2>
        <div class="header-main">
            <div class="edit-controls">
                <button id="edit-mode-btn" class="edit-btn" onclick="toggleEditMode()">📝 Edit Mode</button>
                <button id="edit-speakers-btn" class="edit-btn" onclick="editSpeakers()">👥 Edit Speakers</button>
                <button id="reprocess-btn" class="edit-btn" onclick="reprocessFile()">🔄 Reprocess</button>
                <button id="back-to-list-btn" class="edit-btn" onclick="goBackToList()">📋 View All Files</button>
                <button id="save-btn" class="edit-btn" onclick="saveChanges()" style="display: none;">💾 Save Changes</button>
                <button id="cancel-btn" class="edit-btn" onclick="cancelEdits()" style="display: none;">❌ Cancel</button>
                <span id="save-status" class="save-status"></span>
            </div>
            <div class="media-wrapper">
                <video id="player" preload controls>
                    <source src="{inputfile}" type="video/mp4; codecs=avc1.42E01E,mp4a.40.2" />
                </video>
            </div>
        </div>
        </div>
    <div id="content">
  <div class="e" style="background-color: white">
  """
  html.append(preS)
  def_boxclr, def_spkrclr = "white", "orange"

  for idx, g in enumerate(groups):
    # Use the actual start time of the diarization segment, not offset by spacermilli
    shift = millisec(re.findall(r"[0-9]+:[0-9]+:[0-9]+\.[0-9]+", g[0])[0])
    spacer_offset_sec = spacermilli / 1000.0
    speaker = g[0].split()[-1]
    spkr_name, boxclr, spkrclr = speakers.get(speaker, (speaker, def_boxclr, def_spkrclr))
    escaped_speaker_id = html_module.escape(speaker, quote=True)
    escaped_speaker_name = html_module.escape(spkr_name, quote=True)
    html.append(f'    <div class="e" data-speaker-id="{escaped_speaker_id}" '
                f'data-speaker-name="{escaped_speaker_name}" style="background-color:{boxclr}">')
    if speaker_section:
      html.append(f'      <span style="color:{spkrclr}">{spkr_name}</span><br>')
    captions = [[int(millisec(c.start)), int(millisec(c.end)), c.text]
                for c in webvtt.read(vtt_files[idx])]
    vtt_filename = Path(vtt_files[idx]).name
    for ci, c in enumerate(captions):
      # VTT timestamps are relative to the audio segment, need to add diarization segment start time
      vtt_start_sec = c[0] / 1000  # VTT timestamp in seconds
      vtt_end_sec = c[1] / 1000

      # Add the diarization segment start time to get absolute video time
      raw_start = vtt_start_sec + (shift / 1000) - spacer_offset_sec
      raw_end = vtt_end_sec + (shift / 1000) - spacer_offset_sec

      absolute_start_sec = max(0.0, raw_start)
      # Normalize tiny offsets that stem from the spacer padding
      if absolute_start_sec < 0.5 and vtt_start_sec == 0:
        absolute_start_sec = 0.0

      absolute_end_sec = max(absolute_start_sec, raw_end)

      startStr = f"{int(absolute_start_sec//3600):02d}:{int((absolute_start_sec%3600)//60):02d}:{absolute_start_sec%60:05.2f}"
      endStr = f"{int(absolute_end_sec//3600):02d}:{int((absolute_end_sec%3600)//60):02d}:{absolute_end_sec%60:05.2f}"
      timestamp = f"{int(absolute_start_sec//3600):01d}:{int((absolute_start_sec%3600)//60):02d}:{absolute_start_sec%60:04.1f}"
      # Include speaker name and timestamp for DOCX export, wrapped for editing
      # Add VTT file and timestamp data attributes for precise editing
      html.append(
          f'      <div class="transcript-segment" '
          f'data-start="{absolute_start_sec}" data-end="{absolute_end_sec}" data-speaker="{spkr_name}" '
          f'data-vtt-file="{vtt_filename}" data-vtt-start="{vtt_start_sec}" data-vtt-end="{vtt_end_sec}" '
          f'data-caption-idx="{ci}">')
      if speaker_inline:
        html.append(f'        <span class="speaker-name">{spkr_name}: </span>')
      html.append(f'        <span class="timestamp">[{timestamp}] </span>')
      html.append(
          f'        <span class="transcript-text"><a href="#{startStr}" class="lt" onclick="jumptoTime({int(absolute_start_sec)})">{c[2]}</a></span>'
      )
      html.append('      </div>')
    html.append("    </div>")
  html.append(
      "  </div> <!-- end of class e and speaker segments -->\n    </div> <!-- end of content -->")

  # Add JavaScript at the end of the body for proper DOM loading
  javascript_code = """
    <script>
      console.log('Loading video highlight script...');
      
      // Detect if viewing as local file and hide server-dependent buttons
      if (window.location.protocol === 'file:') {
          console.log('Detected local file mode - hiding server-dependent buttons');
          document.body.classList.add('local-file-mode');
      }
      
      function jumptoTime(time){
          var v = document.getElementsByTagName('video')[0];
          // Jump directly to the exact time (no offset)
          console.log("jumping to time:", time);
          if (v) {
              v.currentTime = time;
          }
      }

      // Track current segment highlighting
      var currentHighlighted = null;

      function highlightCurrentSegment() {
          var v = document.getElementsByTagName('video')[0];
          if (!v) {
              console.log('Video element not found');
              return;
          }
          
          var currentTime = v.currentTime;
          // Use the current time directly (no offset)
          console.log('Current video time:', currentTime);
          
          // Find all clickable transcript segments
          var segments = document.querySelectorAll('a.lt[onclick]');
          console.log('Found segments:', segments.length);
          
          var targetSegment = null;
          
          // Find the segment that should be highlighted based on adjusted video time
          for (var i = 0; i < segments.length; i++) {
              var onclick = segments[i].getAttribute('onclick');
              if (!onclick) continue;
              
              var match = onclick.match(/jumptoTime\\((\\d+)\\)/);
              if (!match) continue;
              
              var segmentTime = parseInt(match[1]);
              
              // Check if this is the current or most recent segment
              if (segmentTime <= currentTime) {
                  targetSegment = segments[i];
              } else {
                  break; // segments are in chronological order
              }
          }
          
          // Only update highlighting if we're switching to a different segment
          if (targetSegment !== currentHighlighted) {
              // Remove previous highlighting
              if (currentHighlighted) {
                  currentHighlighted.style.backgroundColor = '';
                  currentHighlighted.style.fontWeight = '';
                  console.log('Removed previous highlight');
              }
              
              // Highlight new segment
              if (targetSegment) {
                  targetSegment.style.backgroundColor = '#ffeb3b';
                  targetSegment.style.fontWeight = 'bold';
                  currentHighlighted = targetSegment;
                  console.log('Highlighted new segment:', targetSegment.textContent.substring(0, 50) + '...');
                  
                  // Scroll to keep current segment visible
                  targetSegment.scrollIntoView({
                      behavior: 'smooth',
                      block: 'center'
                  });
              }
          }
      }

      // Initialize when DOM is ready
      function initializeVideoTracking() {
          console.log('Initializing video tracking...');
          var v = document.getElementsByTagName('video')[0];
          if (v) {
              console.log('Video found, adding event listeners');
              // Update highlighting as video plays
              v.addEventListener('timeupdate', highlightCurrentSegment);
              
              // Also update when user seeks
              v.addEventListener('seeked', highlightCurrentSegment);
              
              // Initial highlight check
              setTimeout(highlightCurrentSegment, 100);
          } else {
              console.log('Video not found, retrying in 500ms');
              setTimeout(initializeVideoTracking, 500);
          }
      }
      
      // Edit mode functionality
      let editMode = false;
      let originalContent = {};
      
      function toggleEditMode() {
          editMode = !editMode;
          const editButton = document.querySelector('#edit-mode-btn');
          const saveButton = document.querySelector('#save-btn');
          const cancelButton = document.querySelector('#cancel-btn');
          const body = document.body;
          const segments = document.querySelectorAll('.transcript-segment');
          
          if (editMode) {
              // Enter edit mode
              body.classList.add('editing');
              editButton.textContent = '📝 Editing...';
              // Let CSS control button visibility in edit mode
              saveButton.style.display = 'inline-block';
              // Intentionally keep cancel hidden; only Save should show while editing
              
              // Store original content and make segments editable
              segments.forEach(segment => {
                  // Store only the transcript text content, not timestamp/speaker
                  const transcriptTextSpan = segment.querySelector('.transcript-text');
                  originalContent[segment.dataset.start] = transcriptTextSpan ? transcriptTextSpan.textContent : '';
                  
                  // Make only the transcript-text span editable, not the whole segment
                  const textSpan = segment.querySelector('.transcript-text');
                  if (textSpan) {
                      textSpan.contentEditable = true;
                  }
                  segment.classList.add('editable');
              });
          } else {
              // Exit edit mode
              body.classList.remove('editing');
              editButton.textContent = '📝 Edit Mode';
              saveButton.style.display = 'none';
              // Keep cancel hidden
              
              // Make segments non-editable
              segments.forEach(segment => {
                  const textSpan = segment.querySelector('.transcript-text');
                  if (textSpan) {
                      textSpan.contentEditable = false;
                  }
                  segment.classList.remove('editable');
              });
              
              originalContent = {};
          }
      }
      
      function saveChanges() {
          const segments = document.querySelectorAll('.transcript-segment');
          const changes = [];
          
          segments.forEach(segment => {
              const start = segment.dataset.start;
              const end = segment.dataset.end;
              const speaker = segment.dataset.speaker || '';
              const vttFile = segment.dataset.vttFile || '';
              const vttStart = segment.dataset.vttStart || '';
              const vttEnd = segment.dataset.vttEnd || '';
              const captionIdx = segment.dataset.captionIdx || '';
              
              // Extract only the text from the transcript-text span, not the timestamp and speaker
              const transcriptTextSpan = segment.querySelector('.transcript-text');
              const newText = transcriptTextSpan ? transcriptTextSpan.textContent.trim() : '';
              const originalText = originalContent[start] || '';
              
              if (newText !== originalText) {
                  changes.push({
                      // absolute timings are still included for UI uses, but server will rely on VTT-local hints
                      start: start,
                      end: end,
                      speaker: speaker,
                      text: newText,
                      originalText: originalText,
                      vttFile: vttFile,
                      vttStart: vttStart,
                      vttEnd: vttEnd,
                      captionIdx: captionIdx
                  });
              }
          });
          
          if (changes.length === 0) {
              alert('No changes detected.');
              toggleEditMode();
              return;
          }
          
          // Send changes to server
          const videoFile = window.location.pathname.split('/').pop().replace('.html', '');
          
          fetch(`/save_transcript_edits/${videoFile}`, {
              method: 'POST',
              headers: {
                  'Content-Type': 'application/json'
              },
              body: JSON.stringify({ changes: changes })
          })
          .then(response => response.json())
          .then(data => {
              if (data.success) {
                  alert('Changes saved to VTT files! To see your changes in the HTML, click "Reprocess".');
                  toggleEditMode(); // Exit edit mode
              } else {
                  alert('Error saving changes: ' + (data.error || 'Unknown error'));
              }
          })
          .catch(error => {
              console.error('Error saving changes:', error);
              alert('Error saving changes: ' + error.message);
          });
      }
      
      function cancelEdits() {
          if (confirm('Are you sure you want to cancel all edits?')) {
              const segments = document.querySelectorAll('.transcript-segment');
              
              // Restore original content
              segments.forEach(segment => {
                  const start = segment.dataset.start;
                  if (originalContent[start]) {
                      const textSpan = segment.querySelector('.transcript-text');
                      if (textSpan) {
                          textSpan.textContent = originalContent[start];
                      }
                  }
              });
              
              toggleEditMode();
          }
      }
      
      function reprocessFile() {
          if (confirm('This will reprocess the current video file. This may take several minutes. Continue?')) {
              // Extract filename from current URL or use a data attribute
              const videoElement = document.querySelector('video source');
              if (videoElement) {
                  const videoSrc = videoElement.src;
                  const filename = videoSrc.substring(videoSrc.lastIndexOf('/') + 1);
                  
                  // Create a form and submit it like the working version on the main page
                  const form = document.createElement('form');
                  form.method = 'post';
                  form.action = '/rerun';
                  
                  const input = document.createElement('input');
                  input.type = 'hidden';
                  input.name = 'filename';
                  input.value = filename;
                  
                  form.appendChild(input);
                  document.body.appendChild(form);
                  form.submit();
              } else {
                  alert('Could not determine video filename');
              }
          }
      }
      
      function goBackToList() {
          window.location.href = '/list';
      }
      
      function editSpeakers() {
          // Extract current speakers from the page
          const speakerBlocks = document.querySelectorAll('.e[data-speaker-id]');
          const speakers = [];
          const seenSpeakerIds = new Set();
          
          speakerBlocks.forEach(block => {
              const speakerId = block.dataset.speakerId;
              if (!speakerId || seenSpeakerIds.has(speakerId)) {
                  return;
              }
              seenSpeakerIds.add(speakerId);
              const speakerName = (block.dataset.speakerName || speakerId).trim();
              if (speakerName) {
                  speakers.push(speakerName);
              }
          });
          
          if (speakers.length === 0) {
              alert('No speakers found in transcript');
              return;
          }
          
          // Create a simple dialog for editing speaker names
          let dialogContent = 'Edit Speaker Names:\\n\\n';
          const newNames = [];
          
          for (let i = 0; i < speakers.length; i++) {
              const currentName = speakers[i];
              const newName = prompt(dialogContent + `Speaker ${i+1} (currently "${currentName}"):`);
              
              if (newName === null) {
                  // User cancelled
                  return;
              }
              
              newNames.push(newName.trim() || currentName);
              dialogContent += `Speaker ${i+1}: "${newNames[i]}"\\n`;
          }
          
          // Show confirmation
          const confirmed = confirm(
              'Update speakers with these names?\\n\\n' + 
              speakers.map((old, i) => `"${old}" → "${newNames[i]}"`).join('\\n') +
              '\\n\\nThis will reprocess the file with updated speaker names.'
          );
          
          if (confirmed) {
              updateSpeakersAndReprocess(speakers, newNames);
          }
      }
      
      function updateSpeakersAndReprocess(oldNames, newNames) {
          const videoElement = document.querySelector('video source');
          if (!videoElement) {
              alert('Could not determine video filename');
              return;
          }
          
          const videoSrc = videoElement.src;
          const filename = videoSrc.substring(videoSrc.lastIndexOf('/') + 1);
          const basename = filename.replace(/\\.[^/.]+$/, ""); // Remove extension
          
          // Create speaker mapping
          const speakerMapping = {};
          for (let i = 0; i < oldNames.length; i++) {
              speakerMapping[oldNames[i]] = newNames[i];
          }
          
          // Send update request
          fetch('/update-speakers', {
              method: 'POST',
              headers: {
                  'Content-Type': 'application/json',
              },
              body: JSON.stringify({
                  filename: basename,
                  speakers: speakerMapping
              })
          })
          .then(response => response.json())
          .then(data => {
              if (data.success) {
                  alert('Speaker names updated! Reprocessing file...');
                  // Now reprocess with updated speakers
                  reprocessFile();
              } else {
                  alert('Error updating speakers: ' + (data.message || 'Unknown error'));
              }
          })
          .catch(error => {
              console.error('Error:', error);
              alert('Error updating speakers: ' + error.message);
          });
      }
      
      // Start initialization when DOM loads
      if (document.readyState === 'loading') {
          document.addEventListener('DOMContentLoaded', initializeVideoTracking);
      } else {
          initializeVideoTracking();
      }
    </script>
  </body>
</html>"""

  html.append(javascript_code)
  with open(outputHtml, "w", encoding="utf-8") as f:
    f.write("\n".join(html))


def cleanup(files):
  for f in files:
    if os.path.isfile(f):
      os.remove(f)


def get_speaker_config_path(basename):
  """Get the path to the speaker configuration file"""
  return f"{basename}-speakers.json"


def load_speaker_config(basename):
  """Load speaker configuration from JSON file"""
  config_path = get_speaker_config_path(basename)
  if os.path.exists(config_path):
    try:
      import json
      with open(config_path, 'r') as f:
        config = json.load(f)
      # Convert to the format expected by generate_html
      speakers = {}
      for speaker_id, info in config.items():
        if isinstance(info, dict):
          speakers[speaker_id] = (info.get('name', speaker_id), info.get('bgcolor', 'lightgray'),
                                  info.get('textcolor', 'darkorange'))
        else:
          # Legacy format - just the name
          speakers[speaker_id] = (info, 'lightgray', 'darkorange')
      return speakers
    except (json.JSONDecodeError, KeyError) as e:
      print(f"Warning: Could not load speaker config {config_path}: {e}")
      return None
  return None


def save_speaker_config(basename, speakers):
  """Save speaker configuration to JSON file"""
  config_path = get_speaker_config_path(basename)
  config = {}
  for speaker_id, (name, bgcolor, textcolor) in speakers.items():
    config[speaker_id] = {'name': name, 'bgcolor': bgcolor, 'textcolor': textcolor}

  try:
    import json
    with open(config_path, 'w') as f:
      json.dump(config, f, indent=2)
    print(f"Saved speaker configuration to {config_path}")
  except Exception as e:
    print(f"Warning: Could not save speaker config {config_path}: {e}")


def discover_speakers_from_groups(groups):
  """Analyze diarization groups to discover which speakers are actually present"""
  speakers_found = set()
  for g in groups:
    speaker = g[0].split()[-1]  # Extract speaker ID from diarization line
    speakers_found.add(speaker)
  return sorted(list(speakers_found))


def transcribe_video(
    inputfile,
    speaker_names=None,
    num_speakers=None,
    min_speakers=None,
    max_speakers=None,
    speaker_section=True,
    speaker_inline=True,
    whisper_model="base",
    whisper_device="auto",
    whisper_compute_type="auto",
    coreml_units=None,
    called_by_mercuryweb=False,
    mercury_command: str | None = None,
):
  basename = Path(inputfile).stem
  workdir = basename
  Path(workdir).mkdir(exist_ok=True)
  os.chdir(workdir)

  # Prepare audio
  inputWavCache = f"{basename}.cache.wav"
  # If the caller provided an absolute path, don't prefix with "../" (that corrupts absolute paths
  # when the code changes into the workdir). Use the absolute or original path accordingly.
  if os.path.isabs(str(inputfile)):
    input_arg = str(inputfile)
  else:
    input_arg = f"../{inputfile}"
  convert_to_wav(input_arg, inputWavCache)
  outputWav = f"{basename}-spaced.wav"
  create_spaced_audio(inputWavCache, outputWav)

  diarizationFile = f"{basename}-diarization.txt"
  dzs = get_diarization(outputWav, diarizationFile, num_speakers, min_speakers, max_speakers)
  groups = group_segments(dzs)

  segment_files = export_segments_audio(groups, outputWav)
  vtt_files = transcribe_segments(
      segment_files,
      model_size=whisper_model,
      device=whisper_device,
      compute_type=whisper_compute_type,
      coreml_units=coreml_units,
  )

  # Discover which speakers are actually present
  actual_speakers = discover_speakers_from_groups(groups)
  print(f"Detected speakers: {actual_speakers}")

  # Try to load existing speaker config first
  speakers = load_speaker_config(basename)

  if speakers is None:
    # No config exists, create default mapping
    speakers = {}
    default_colors = [('lightgray', 'darkorange'), ('#e1ffc7', 'darkgreen'),
                      ('#ffe1e1', 'darkblue'), ('#e1e1ff', 'darkred'), ('#fff1e1', 'darkpurple'),
                      ('#f1e1ff', 'darkcyan')]

    if speaker_names:
      # Use provided speaker names
      for i, name in enumerate(speaker_names):
        if i < len(actual_speakers):
          speaker_id = actual_speakers[i]
          bgcolor, textcolor = default_colors[i % len(default_colors)]
          speakers[speaker_id] = (name, bgcolor, textcolor)
    else:
      # Create default names for detected speakers
      for i, speaker_id in enumerate(actual_speakers):
        bgcolor, textcolor = default_colors[i % len(default_colors)]
        speakers[speaker_id] = (f"Speaker {i+1}", bgcolor, textcolor)

    # Save the initial config
    save_speaker_config(basename, speakers)
    print(f"Created speaker config file: {get_speaker_config_path(basename)}")
    print("You can edit speaker names and rerun to update the transcript.")

  # Ensure all detected speakers have entries (in case new speakers appeared)
  updated = False
  for speaker_id in actual_speakers:
    if speaker_id not in speakers:
      # New speaker detected, add with default settings
      i = len(speakers)
      bgcolor, textcolor = default_colors[i % len(default_colors)]
      speakers[speaker_id] = (f"Speaker {i+1}", bgcolor, textcolor)
      updated = True

  if updated:
    save_speaker_config(basename, speakers)
    print("Updated speaker config with newly detected speakers")

  generate_html(
      f"../{basename}.html",
      groups,
      vtt_files,
      inputfile,
      speakers,
      speaker_section=speaker_section,
      speaker_inline=speaker_inline,
      called_by_mercuryweb=called_by_mercuryweb,
      mercury_command=mercury_command,
  )
  # Try to create a DOCX using the shared html_to_docx helper so the CLI and
  # the web server use the same conversion code path.
  try:
    from transcribe_with_whisper.html_to_docx import ensure_deps, convert_html_file_to_docx
  except Exception as import_exc:
    print("⚠️ DOCX generation unavailable: required Python packages are missing. Install with: pip install python-docx")
    print(f"(import error for html_to_docx: {import_exc})")
  else:
    try:
      if ensure_deps():
        html_out = Path(f"../{basename}.html")
        docx_out = html_out.with_suffix('.docx')
        convert_html_file_to_docx(html_out, docx_out)
        print(f"✅ Generated DOCX (shared): {docx_out.name}")
      else:
        print("⚠️ DOCX generation unavailable: python-docx not installed. Install with: pip install python-docx")
    except Exception as py_exc:
      print(f"⚠️ DOCX conversion failed: {py_exc}")
  cleanup([inputWavCache, outputWav] + segment_files)
  print(f"Script completed successfully! Output: ../{basename}.html")


def main():
  # Debug logging for CLI startup
  exe_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.getcwd()
  log_path = os.path.join(exe_dir, "bundle_run.log")
  with open(log_path, "a", encoding="utf-8") as fh:
    fh.write(f"[CLI main] Starting CLI with args: {sys.argv}\n")

  parser = argparse.ArgumentParser(description='Transcribe video/audio with speaker diarization',
                                   formatter_class=argparse.RawDescriptionHelpFormatter,
                                   epilog='''
Examples:
  # Basic transcription
  %(prog)s video.mp4
  
  # With speaker names
  %(prog)s video.mp4 "Alice" "Bob"
  
  # Specify exact number of speakers (improves accuracy)
  %(prog)s video.mp4 --num-speakers 2
  
  # Specify speaker range
  %(prog)s video.mp4 --min-speakers 2 --max-speakers 4
  
  # Combine speaker names with constraints
  %(prog)s video.mp4 --num-speakers 2 "Alice" "Bob"
        ''')

  parser.add_argument('--version',
                      action='version',
                      version=f"transcribe-with-whisper {get_package_version()}",
                      help="Show the application's version number and exit")

  parser.add_argument('video_file', help='Video or audio file to transcribe')
  parser.add_argument('speaker_names',
                      nargs='*',
                      help='Optional speaker names (e.g., "Alice" "Bob")')
  parser.add_argument('--num-speakers',
                      type=int,
                      metavar='N',
                      help='Exact number of speakers (improves diarization accuracy)')
  parser.add_argument('--min-speakers', type=int, metavar='N', help='Minimum number of speakers')
  parser.add_argument('--max-speakers', type=int, metavar='N', help='Maximum number of speakers')
  parser.add_argument('--speaker-section',
                      dest='speaker_section',
                      action=argparse.BooleanOptionalAction,
                      default=False,
                      help='Include speaker when speakers switch turns.')
  parser.add_argument('--speaker-inline',
                      dest='speaker_inline',
                      action=argparse.BooleanOptionalAction,
                      default=True,
                      help='Include speaker label on each line (use --no-speaker-inline to hide).')
  parser.add_argument(
      '--called-by-mercuryweb',
      dest='called_by_mercuryweb',
      action=argparse.BooleanOptionalAction,
      default=False,
      help='Indicate whether the invocation originated from the Mercury web interface.')
  args = parser.parse_args()
  command_line = " ".join(shlex.quote(arg) for arg in sys.argv)

  # Validate speaker constraints
  if args.num_speakers is not None and (args.min_speakers is not None
                                        or args.max_speakers is not None):
    print("Error: Cannot use --num-speakers with --min-speakers or --max-speakers")
    sys.exit(1)

  if args.num_speakers is not None and args.num_speakers < 1:
    print("Error: --num-speakers must be at least 1")
    sys.exit(1)

  if args.min_speakers is not None and args.min_speakers < 1:
    print("Error: --min-speakers must be at least 1")
    sys.exit(1)

  if args.max_speakers is not None and args.max_speakers < 1:
    print("Error: --max-speakers must be at least 1")
    sys.exit(1)

  if args.min_speakers is not None and args.max_speakers is not None:
    if args.min_speakers > args.max_speakers:
      print("Error: --min-speakers cannot be greater than --max-speakers")
      sys.exit(1)

  transcribe_video(
      args.video_file,
      args.speaker_names if args.speaker_names else None,
      args.num_speakers,
      args.min_speakers,
      args.max_speakers,
      speaker_section=args.speaker_section,
      speaker_inline=args.speaker_inline,
      called_by_mercuryweb=args.called_by_mercuryweb,
      mercury_command=command_line,
  )


if __name__ == "__main__":
  main()
