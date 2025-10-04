#!/usr/bin/env python3
import sys
import os
import importlib
import subprocess
import shutil
import platform
from pathlib import Path

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
            print("   For GPU acceleration, install the CoreML build:")
            print("      pip install faster-whisper[coreml]")
        else:
            print("💻 Detected Intel Mac (x86_64).")
            print("👉 Running in CPU mode only (no GPU acceleration).")
    elif system == "Linux":
        print("🐧 Detected Linux system.")
        print("👉 If you have an NVIDIA GPU with CUDA installed, faster-whisper can use it.")
    elif system == "Windows":
        print("🪟 Detected Windows system.")
        print("👉 If you have an NVIDIA GPU with CUDA installed, faster-whisper can use it.")
    else:
        print(f"ℹ️ Detected {system} on {machine}. No special notes.")
def check_dependencies():
    missing = []
    for lib in REQUIRED_LIBS:
        try:
            importlib.import_module(lib)
        except ImportError:
            missing.append(lib)
    if missing:
        print("❌ Missing required Python libraries:")
        for m in missing:
            print(f"   - {m}")
        print("👉 Install them with:")
        print(f"   pip install {' '.join(missing)}")
        sys.exit(1)

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

def _hf_token_config_paths() -> list[Path]:
    """Return possible locations for the saved Hugging Face token."""
    candidate_files: list[Path] = []

    env_dir = os.getenv("TRANSCRIPTION_DIR")
    if env_dir:
        candidate_files.append(Path(env_dir) / ".config" / "hf_token")

    repo_transcription = Path(__file__).resolve().parent / "transcription-files"
    candidate_files.append(repo_transcription / ".config" / "hf_token")

    cwd = Path.cwd()
    candidate_files.append(cwd / "transcription-files" / ".config" / "hf_token")
    candidate_files.append(cwd / ".config" / "hf_token")
    # also check relative to /app (for Docker containers)
    candidate_files.append(Path("/app") / "transcription-files" / ".config" / "hf_token")

    unique: list[Path] = []
    seen: set[str] = set()
    for path in candidate_files:
        normalized = str(path)
        if normalized not in seen:
            seen.add(normalized)
            unique.append(path)

    return unique

def _load_hf_token_from_file() -> str | None:
    """Load token from known config file locations."""
    for path in _hf_token_config_paths():
        try:
            if path.exists():
                token = path.read_text(encoding="utf-8").strip()
                if token:
                    print(f"🔐 Using Hugging Face token from {path}")
                    return token
        except (OSError, UnicodeDecodeError):
            continue
    return None

def _resolve_hf_token() -> str | None:
    token = _load_hf_token_from_file()
    if token:
        return token
    return os.getenv("HUGGING_FACE_AUTH_TOKEN")

def check_hf_token():
    token = _resolve_hf_token()
    if not token:
        print("❌ HUGGING_FACE_AUTH_TOKEN environment variable is not set.")
        print("👉 Run: export HUGGING_FACE_AUTH_TOKEN=your_token_here")
        print("   or use the MercuryScribe web UI to store the token in .config/hf_token")
        sys.exit(1)
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

def run_preflight():
    print("🔎 Running preflight checks...")
    check_dependencies()
    check_ffmpeg()
    token = check_hf_token()
    check_models(token)
    check_platform_notes()
    print("✅ All checks passed!\n")

# Run preflight before importing heavy libraries
run_preflight()

# Now safe to import heavy stuff
from pyannote.audio import Pipeline
from pydub import AudioSegment
from faster_whisper import WhisperModel
import webvtt
from datetime import timedelta
import re
import warnings

# Check pyannote.audio version for API compatibility
try:
    import pyannote.audio
    _PYANNOTE_VERSION = pyannote.audio.__version__
    _PYANNOTE_MAJOR = int(_PYANNOTE_VERSION.split('.')[0])
except Exception:
    # Fallback: assume version 4.x if import fails
    _PYANNOTE_MAJOR = 4

# Suppress pyannote version warnings
warnings.filterwarnings("ignore", message="Model was trained with")
warnings.filterwarnings("ignore", message="Lightning automatically upgraded")

#accept the user conditions on both https://hf.co/pyannote/speaker-diarization and https://hf.co/pyannote/segmentation.

if len(sys.argv) < 2:
    print("Usage: script.py <inputfile> [Speaker1] [Speaker2] [Speaker3] ...")
    sys.exit(1)

inputfile = sys.argv[1]
speaker_names = sys.argv[2:]  # any extra args are speaker names

# Default speaker labels
default_speakers = ["Speaker 1", "Speaker 2", "Speaker 3", "Speaker 4", "Speaker 5", "Speaker 6"]

# If user provides names, override defaults
for i, name in enumerate(speaker_names):
    if i < len(default_speakers):
        default_speakers[i] = name

# Get the basename without extension (works for both .mp4 and .mov)
if inputfile.lower().endswith('.mp4'):
    basename = inputfile.replace('.mp4', '')
elif inputfile.lower().endswith('.mov'):
    basename = inputfile.replace('.mov', '')
elif inputfile.lower().endswith('.mkv'):
    basename = inputfile.replace('.mkv', '')
else:
    # For other extensions, remove the last extension
    basename = os.path.splitext(inputfile)[0]

inputWav = basename + '.wav'
video_title = basename

existing_vtt_files = []
if os.path.isdir(basename):
    existing_vtt_files = [
        filename
        for filename in os.listdir(basename)
        if filename.endswith('.vtt') and filename[:-4].isdigit()
    ]
else:
    os.mkdir(basename)

diarization_path = os.path.join(basename, f"{basename}-diarization.txt")
reuse_existing = bool(existing_vtt_files) and os.path.isfile(diarization_path)

if reuse_existing:
    print(f"🔁 Found {len(existing_vtt_files)} existing speaker VTT files. Reusing cached results.")
else:
    print("🎯 No cached VTT files found. Running diarization and transcription pipeline.")
    if not os.path.isfile(inputWav):
        subprocess.run(["ffmpeg", "-i", inputfile, inputWav])

os.chdir(basename)

inputWavCache = f'{basename}.cache.wav'
outputWav = f'{basename}-spaced.wav'
diarizationFile = f'{basename}-diarization.txt'
vttFile = f'{basename}-spaced.vtt'
outputHtml = f'../{basename}.html'
cleanup_files = not reuse_existing
spacermilli = 2000

if not reuse_existing:
    if not os.path.isfile(inputWavCache):
        print(f"Creating cache file: {inputWavCache}")
        audio_temp = AudioSegment.from_wav("../" + inputWav)
        audio_temp.export(inputWavCache, format='wav')
    spacer = AudioSegment.silent(duration=spacermilli)
    audio = AudioSegment.from_wav(inputWavCache)
    audio = spacer.append(audio, crossfade=0)
    audio.export(outputWav, format='wav')

    # Get auth token from saved config or environment
    auth_token = _resolve_hf_token()
    if not auth_token:
        raise ValueError("Hugging Face auth token is required (set HUGGING_FACE_AUTH_TOKEN or store it in .config/hf_token)")

    # Use appropriate API based on pyannote.audio version
    if _PYANNOTE_MAJOR >= 4:
        # pyannote.audio 4.0.0+ API
        pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-community-1", token=auth_token)
    else:
        # pyannote.audio 3.x API
        pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", use_auth_token=auth_token)

    DEMO_FILE = {'uri': 'blabla', 'audio': outputWav}

    if not os.path.isfile(diarizationFile):
        dz = pipeline(DEMO_FILE)
        diarization = dz.speaker_diarization if hasattr(dz, 'speaker_diarization') else dz
        with open(diarizationFile, "w") as text_file:
            text_file.write(str(diarization))

def millisec(timeStr):
  spl = timeStr.split(":")
  s = (int)((int(spl[0]) * 60 * 60 + int(spl[1]) * 60 + float(spl[2]) )* 1000)
  return s

def format_time(seconds):
    """Convert seconds to VTT time format (HH:MM:SS.mmm)"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"

dzs = open(diarizationFile).read().splitlines()

groups = []
g = []
lastend = 0

for d in dzs:
  if g and (g[0].split()[-1] != d.split()[-1]):      #same speaker
    groups.append(g)
    g = []
  g.append(d)
  end = re.findall('[0-9]+:[0-9]+:[0-9]+\.[0-9]+', string=d)[1]
  end = millisec(end)
  if (lastend > end):       #segment engulfed by a previous segment
    groups.append(g)
    g = []
  else:
    lastend = end

if g:
  groups.append(g)

print(*groups, sep='\n')

segments_created = 0

if not reuse_existing:
    audio = AudioSegment.from_wav(outputWav)
    gidx = -1

    for g in groups:
        start = re.findall('[0-9]+:[0-9]+:[0-9]+\.[0-9]+', string=g[0])[0]
        end = re.findall('[0-9]+:[0-9]+:[0-9]+\.[0-9]+', string=g[-1])[1]
        start = millisec(start)
        end = millisec(end)
        print(start, end)
        gidx += 1
        audio[start:end].export(str(gidx) + '.wav', format='wav')

    # Initialize faster-whisper model once
    print("Loading Whisper model...")
    from faster_whisper import WhisperModel

    def load_whisper_model(model_size="base"):
            """Load Whisper model with graceful fallback to CPU."""
            system = platform.system()
            machine = platform.machine()

            print("🔊 Initializing Whisper...")

            try:
                    model = WhisperModel(model_size, device="auto", compute_type="auto")
                    print("✅ Whisper model loaded with device=auto (GPU/Metal/CPU as available).")
                    return model
            except Exception as e:
                    print(f"⚠️ Could not load Whisper with device=auto: {e}")

                    if system == "Darwin" and machine == "arm64":
                            print("👉 Falling back to CPU mode on Apple Silicon (install faster-whisper[coreml] for GPU).")
                            return WhisperModel(model_size, device="cpu", compute_type="int8")

                    print("👉 Falling back to CPU mode.")
                    return WhisperModel(model_size, device="cpu", compute_type="int8")

    model = load_whisper_model("base")

    for i in range(gidx + 1):
        if not os.path.isfile(str(i) + '.vtt'):
            print(f'Processing {str(i) + ".wav"}')

            segments, info = model.transcribe(str(i) + '.wav', language="en")

            with open(str(i) + '.vtt', "w", encoding="utf-8") as f:
                    f.write("WEBVTT\n\n")
                    for segment in segments:
                            start_time = format_time(segment.start)
                            end_time = format_time(segment.end)
                            f.write(f"{start_time} --> {end_time}\n{segment.text.strip()}\n\n")

            print(f"Completed {str(i)}.vtt")

    segments_created = gidx + 1

speakers = {
    "SPEAKER_00": (default_speakers[0], "lightgray", "darkorange"),
    "SPEAKER_01": (default_speakers[1], "#e1ffc7", "darkgreen"),
    "SPEAKER_02": (default_speakers[2], "#e1ffc7", "darkblue"),
}

def_boxclr = 'white'
def_spkrclr = 'orange'


preS = f"""<!DOCTYPE html>\n<html lang="en">\n  <head>\n    <meta charset="UTF-8">\n    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="X-UA-Compatible" content="ie=edge">
    <title>{inputfile}</title>
    """ + """
    <script>
      var vidLinks = document.querySelectorAll('.lt a');
      // for(var i = 0, l = vidLinks.length; ++i) {
      //     makeVideoLink(vidLinks[i]);
      // }

      var v = document.getElementsByTagName('video')[0];
      v.removeAttribute('controls') // '' in Chrome, "true" in FF9 (string)
      v.controls // true
      function jumptoTime(time){
          var v = document.getElementsByTagName('video')[0];

          window.console.log("jumping!!", time);
          window.console.log("this",this);
          window.console.log("vid",v);
          v.currentTime = time;
      }

      function makeVideoLink(element){
          // Extract the `t=` hash from the link
          var timestamp = element.hash.match(/\d+$/,'')[0] * 1000;

          element.addEventListener('click', function videoLinkClick(e){
              jumpToTime(timestamp);

              return false;
          },false)
      }
    </script>
    <style>
        body {
            font-family: sans-serif;
            font-size: 18px;
            color: #111;
            padding: 0 0 1em 0;
	        background-color: #efe7dd;
        }
        table {
             border-spacing: 10px;
        }
        th { text-align: left;}
        .lt {
          color: inherit;
          text-decoration: inherit;
        }
        .l {
          color: #050;
        }
        .s {
            display: inline-block;
        }
        .c {
            display: inline-block;
        }
        .e {
            /*background-color: white; Changing background color */
            border-radius: 20px; /* Making border radius */
            width: fit-content; /* Making auto-sizable width */
            height: fit-content; /* Making auto-sizable height */
            padding: 5px 30px 5px 30px; /* Making space around letters */
            font-size: 18px; /* Changing font size */
            display: flex;
            flex-direction: column;
            margin-bottom: 10px;
            /* white-space: nowrap; */
        }

        .t {
            display: inline-block;
        }
        #player {
            position: sticky;
            top: 20px;
            float: right;
        }
    </style>
</head>
  <body>
   """ + f"""
    <h2>{video_title}</h2>
    <i>Click on a part of the transcription, to jump to its video, and get an anchor to it in the address bar<br></i>
  <video id="player" style="border:none;" width="575" height="240" preload controls>
    <source src="{inputfile}" type="video/mp4; codecs=avc1.42E01E,mp4a.40.2" />
    </video>
  <div  id="player"></div>
<div class="e" style="background-color: white">
"""
postS = '</body></html>'

html = list(preS)
gidx = -1

for g in groups:
  shift = re.findall('[0-9]+:[0-9]+:[0-9]+\.[0-9]+', string=g[0])[0]
  shift = millisec(shift) - spacermilli #the start time in the original video
  shift=max(shift, 0)
  gidx += 1
  captions = [[(int)(millisec(caption.start)), (int)(millisec(caption.end)),  caption.text] for caption in webvtt.read(str(gidx) + '.vtt')]
  if captions:
    speaker = g[0].split()[-1]
    boxclr = def_boxclr
    spkrclr = def_spkrclr
    if speaker in speakers:
      speaker, boxclr, spkrclr = speakers[speaker]
    html.append(f'<div class="e" style="background-color: {boxclr}">\n');
    html.append(f'<span style="color: {spkrclr}">{speaker}</span>\n')
    for c in captions:
      start = shift + c[0]
      start = start / 1000.0   #time resolution ot youtube is Second.
      startStr = '{0:02d}:{1:02d}:{2:02.2f}'.format((int)(start // 3600),
                                              (int)(start % 3600 // 60),
                                              start % 60)
      #html.append(f'<div class="c">')
      #html.append(f'\t\t\t\t<a class="l" href="#{startStr}" id="{startStr}">#</a> \n')
      html.append(f'\t\t\t\t<a href="#{startStr}" id="{startStr}" class="lt" onclick="jumptoTime({int(start)}, this.id)">{c[2]}</a>\n')
      #html.append(f'\t\t\t\t<div class="t"> {c[2]}</div><br>\n')
      #html.append(f'</div>')
    html.append(f'</div>\n');

html.append(postS)
s = "".join(html)

with open(outputHtml, "w") as text_file:
    text_file.write(s)

# Clean up cache files if script completed successfully
if cleanup_files:
    try:
        if os.path.isfile(inputWavCache):
            os.remove(inputWavCache)
            print(f"Cleaned up cache file: {inputWavCache}")

        if os.path.isfile(outputWav):
            os.remove(outputWav)
            print(f"Cleaned up cache file: {outputWav}")

        for i in range(segments_created):
            segment_wav = f"{i}.wav"
            if os.path.isfile(segment_wav):
                os.remove(segment_wav)
                print(f"Cleaned up segment file: {segment_wav}")

    except Exception as e:
        print(f"Note: Could not clean up some cache files: {e}")

print(f"Script completed successfully! Output: {outputHtml}")
