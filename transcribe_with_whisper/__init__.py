#!/usr/bin/env python3
import sys
import os
import importlib
import subprocess
import shutil
import platform

REQUIRED_LIBS = [
    "pyannote.audio",
    "pydub",
    "faster_whisper",
    "webvtt",
]

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

def check_models(token):
    from huggingface_hub import HfApi
    try:
        api = HfApi()
        # Make sure we can list the model
        _ = api.model_info("pyannote/speaker-diarization", token=token)
        print("✅ Hugging Face model 'pyannote/speaker-diarization' is accessible.")
    except Exception as e:
        print(f"❌ Could not access pyannote/speaker-diarization: {e}")
        sys.exit(1)

def run_preflight():
    print("🔎 Running preflight checks...")
    check_ffmpeg()
    token = check_hf_token()
    check_models(token)
    check_platform_notes()
    print("✅ All checks passed!\n")

# Skip preflight checks in test environments or when explicitly disabled
if not os.getenv("SKIP_PREFLIGHT_CHECKS") and not os.getenv("PYTEST_CURRENT_TEST"):
    run_preflight()

import sys
import os
from pathlib import Path
from pyannote.audio import Pipeline
from pydub import AudioSegment
from faster_whisper import WhisperModel
import webvtt
import subprocess
import re


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
        audio_temp = AudioSegment.from_wav("../"+inputWav)
        audio_temp.export(inputWavCache, format='wav')

    # Hugging Face auth
    auth_token = os.getenv('HUGGING_FACE_AUTH_TOKEN')
    if not auth_token:
        raise ValueError("HUGGING_FACE_AUTH_TOKEN environment variable is required")

    pipeline = Pipeline.from_pretrained('pyannote/speaker-diarization', use_auth_token=auth_token)
    DEMO_FILE = {'uri': 'blabla', 'audio': inputWavCache}

    diarizationFile = f'{basename}-diarization.txt'
    if not os.path.isfile(diarizationFile):
        dz = pipeline(DEMO_FILE)
        with open(diarizationFile, "w") as text_file:
            text_file.write(str(dz))

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
