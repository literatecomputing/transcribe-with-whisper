import sys
import os
from pathlib import Path
from pyannote.audio import Pipeline
from pydub import AudioSegment
from faster_whisper import WhisperModel
import webvtt
import subprocess
import re
import warnings

warnings.filterwarnings("ignore", message="Model was trained with")
warnings.filterwarnings("ignore", message="Lightning automatically upgraded")

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
