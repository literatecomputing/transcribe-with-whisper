#!/usr/bin/env python3
import os
import platform
import shutil
import subprocess
import sys

REQUIRED_LIBS = [
    "pyannote.audio",
    "pydub",
    "faster_whisper",
    "webvtt",
]

# Torch 2.6+ weights_only compatibility for pyannote.audio
try:
    import torch
    if hasattr(torch.serialization, "add_safe_globals"):
        # We need to allow-list pyannote classes used in model checkpoints
        # to avoid WeightsUnpickler error in Torch 2.6+
        safe_types = []
        try:
            from pyannote.audio.core.task import Specifications, Problem, Resolution
            safe_types.extend([Specifications, Problem, Resolution])
        except ImportError:
            pass
            
        try:
            # Sometimes used in older or specific models
            from pyannote.database.protocol.protocol import Protocol
            safe_types.append(Protocol)
        except ImportError:
            pass

        if safe_types:
            torch.serialization.add_safe_globals(safe_types)
except ImportError:
    pass


def check_platform_notes():
  system = platform.system()
  machine = platform.machine()

  if system == "Darwin":  # macOS
    if machine == "arm64":
      print("💻 Detected Apple Silicon Mac (arm64).")
      print("👉 faster-whisper will run on CPU by default.")
    else:
      print("💻 Detected Intel Mac (x86_64).")
      print("👉 Running in CPU mode only (no GPU acceleration).")
  elif system == "Linux":
    print("🐧 Detected Linux system.")
  elif system == "Windows":
    print("🪟 Detected Windows system.")
  else:
    print(f"ℹ️ Detected {system} on {machine}. No special notes.")


def check_ffmpeg():
  if shutil.which("ffmpeg") is None:
    print("❌ ffmpeg not found on system PATH.")
    print("\n👉 To install ffmpeg:")
    print("   • Ubuntu/Debian:  sudo apt update && sudo apt install ffmpeg")
    print("   • macOS (Homebrew):  brew install ffmpeg")
    print("   • Windows (choco):  choco install ffmpeg")
    print("     Or download manually: https://ffmpeg.org/download.html")
    sys.exit(1)
  else:
    try:
      result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
      if result.returncode == 0:
        print(f"✅ ffmpeg found: {result.stdout.splitlines()[0]}")
      else:
        raise RuntimeError("ffmpeg exists but did not run properly")
    except Exception as e:
      print(f"❌ Error checking ffmpeg: {e}")
      sys.exit(1)


def check_hf_token():
  token = os.getenv("HUGGING_FACE_AUTH_TOKEN")
  if not token:
    print("❌ HUGGING_FACE_AUTH_TOKEN environment variable is not set.")
    print("👉 Run: export HUGGING_FACE_AUTH_TOKEN=your_token_here")
    sys.exit(1)
  return token


def check_hf_token_graceful():
  """Check for HF token without exiting - for web server mode"""
  token = os.getenv("HUGGING_FACE_AUTH_TOKEN")
  return token


def check_models(token):
  from huggingface_hub import HfApi
  try:
    api = HfApi()
    # Make sure we can list the model
    _ = api.model_info("pyannote/speaker-diarization-community-1", token=token)
    print("✅ Hugging Face model 'pyannote/speaker-diarization-community-1' is accessible.")
  except Exception as e:
    print(f"❌ Could not access pyannote/speaker-diarization-community-1: {e}")
    sys.exit(1)


def report_pyannote_version():
  try:
    import pyannote.audio  # type: ignore

    version = getattr(pyannote.audio, "__version__", "unknown")
    print(f"🎧 pyannote.audio version: {version}")
    return version
  except Exception as exc:
    print(f"❌ pyannote.audio is not available: {exc}")
    sys.exit(1)


def run_preflight():
  print("🔎 Running preflight checks...")
  check_ffmpeg()

  # Check if we're in web server mode (skip token validation for graceful startup)
  if os.getenv("WEB_SERVER_MODE") == "1":
    token = check_hf_token_graceful()
    if token:
      check_models(token)
    else:
      print("⚠️  No HF token found - web server will guide users through setup.")
  else:
    token = check_hf_token()
    check_models(token)

  report_pyannote_version()
  check_platform_notes()
  print("✅ All checks passed!\n")


def should_run_preflight() -> bool:
  """Return True if preflight checks should run in this context."""

  if os.getenv("SKIP_PREFLIGHT_CHECKS"):
    return False
  if os.getenv("SKIP_HF_STARTUP_CHECK"):
    return False
  if os.getenv("PYTEST_CURRENT_TEST"):
    return False
  if os.getenv("WEB_SERVER_MODE"):
    return False

  cli_args = sys.argv[1:] if hasattr(sys, "argv") else []
  if any(arg == "--version" for arg in cli_args):
    return False

  if hasattr(sys, "argv") and sys.argv:
    try:
      argv0_normalized = sys.argv[0].replace("\\", "/")
      if "transcribe_with_whisper/server_app.py" in argv0_normalized:
        return False
    except Exception:
      pass

  return True


def ensure_preflight() -> None:
  """Run preflight checks if allowed for the current context."""

  if should_run_preflight():
    run_preflight()


from pyannote.audio import Pipeline
from pydub import AudioSegment

# Check pyannote.audio version for API compatibility
try:
  import pyannote.audio
  _PYANNOTE_VERSION = pyannote.audio.__version__
  _PYANNOTE_MAJOR = int(_PYANNOTE_VERSION.split('.')[0])
except Exception:
  # Fallback: assume version 4.x if import fails
  _PYANNOTE_MAJOR = 4


def millisec(timeStr):
  spl = timeStr.split(":")
  s = int((int(spl[0]) * 3600 + int(spl[1]) * 60 + float(spl[2])) * 1000)
  return s


def format_time(seconds):
  hours = int(seconds // 3600)
  minutes = int((seconds % 3600) // 60)
  secs = seconds % 60
  return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"


def transcribe_video(inputfile, speaker_names=None):
  basename = os.path.splitext(inputfile)[0]
  inputWav = basename + '.wav'

  # Convert video to WAV if it doesn't exist
  if not os.path.isfile(inputWav):
    subprocess.run(["ffmpeg", "-i", inputfile, inputWav])

  # Prepare working directory
  if not os.path.isdir(basename):
    os.mkdir(basename)
  os.chdir(basename)

  inputWavCache = f'{basename}.cache.wav'
  if not os.path.isfile(inputWavCache):
    audio_temp = AudioSegment.from_wav("../" + inputWav)
    audio_temp.export(inputWavCache, format='wav')

  # Hugging Face auth
  auth_token = os.getenv('HUGGING_FACE_AUTH_TOKEN')
  if not auth_token:
    raise ValueError("HUGGING_FACE_AUTH_TOKEN environment variable is required")

  # Use appropriate API based on pyannote.audio version
  if _PYANNOTE_MAJOR >= 4:
    # pyannote.audio 4.0.0+ API
    pipeline = Pipeline.from_pretrained('pyannote/speaker-diarization-community-1',
                                        token=auth_token)
  else:
    # pyannote.audio 3.x API
    pipeline = Pipeline.from_pretrained('pyannote/speaker-diarization-3.1',
                                        use_auth_token=auth_token)
  DEMO_FILE = {'uri': 'blabla', 'audio': inputWavCache}

  diarizationFile = f'{basename}-diarization.txt'
  if not os.path.isfile(diarizationFile):
    dz = pipeline(DEMO_FILE)
    # In pyannote.audio 4.0, pipeline returns an object with .speaker_diarization attribute
    diarization = dz.speaker_diarization if hasattr(dz, 'speaker_diarization') else dz
    with open(diarizationFile, "w") as text_file:
      text_file.write(str(diarization))

  # Process speakers
  speakers = {}
  if speaker_names:
    for i, name in enumerate(speaker_names):
      speakers[f"SPEAKER_{i:02d}"] = (name, 'lightgray', 'darkorange')
  else:
    speakers = {
        'SPEAKER_00': ('Speaker 1', 'lightgray', 'darkorange'),
        'SPEAKER_01': ('Speaker 2', '#e1ffc7', 'darkgreen'),
        'SPEAKER_02': ('Speaker 3', '#e1ffc7', 'darkblue'),
    }

  # (Insert the rest of your script logic here: spacing audio, splitting segments,
  # transcribing with WhisperModel, generating HTML)
  print("Transcription logic would run here...")


def main():
  if len(sys.argv) < 2:
    print("Usage: whisper-transcribe <video_file> [speaker_names...]")
    sys.exit(1)

  inputfile = sys.argv[1]
  speaker_names = sys.argv[2:]  # any extra args are speaker names

  # Default speaker labels
  # If user provides names, override defaults
  for i, name in enumerate(speaker_names):
    if i < len(default_speakers):
      default_speakers[i] = name
    transcribe_video(inputfile, default_speakers)


if __name__ == "__main__":
  main()
