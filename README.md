# transcribe-with-whisper

This script creates speaker-aware transcripts from video files, and
outputs an HTML file where you can click on the transcript to jump to
the video. Works on macOS (Intel & Apple Silicon), Linux, and Windows.

---

## What this does

- Takes a video file (.mp4, .mov, or .mkv) and creates an audio-only file (.wav)
- Separates who is speaking when (speaker diarization using [pyannote/speaker-diarization](https://huggingface.co/pyannote/speaker-diarization), a free AI model)
- Transcribes each speaker's speech using the [Faster Whisper](https://github.com/SYSTRAN/faster-whisper) Python library
- Produces an HTML file: you click on parts of the transcript, the video jumps to that moment
- The HTML file and the original video file are required to view the transcription in a web browser

---

## Making it work

There are instructions here for 3 different ways to use this package. The requirements to make the Python package (`pip install transcribe-with-whisper`) work on a Mac are fairly complex for novices (a particular Python version is required and `brew` is required to install ffmpeg).

An alternative is to use a pre-built docker container that is automatically updated whenever a new version of this package is pushed to github. For those not familiar with Docker, scripts that will run it are also included.

### Hugging Face Auth Token is required

Since you're running this on your own computer, you need a Hugging Face account, a read-access token, and access to the models used for speaker diarization. Follow these steps:

1. Create a free Hugging Face account

- https://huggingface.co/join

2. Request access to the required models (accept their terms)

- Required: pyannote/speaker-diarization-3.1 → https://huggingface.co/pyannote/speaker-diarization-3.1
- Required: pyannote/segmentation → https://huggingface.co/pyannote/segmentation
- On each model page, click Use this model” and select "pyannote.audio". Access is typically approved instantly for free use. After you have accepted it, you should see "**Gated Model** You have been granted access to this model". You can also check which models you have access to at https://huggingface.co/settings/gated-repos.

3. Create a read-access token

- Go to https://huggingface.co/settings/tokens
- Click “Create new token” and then Read
- Enter a token name (maybe the computer you're using and/or the date) and click the "Create token" button.
- Copy the token (looks like `hf_...`) and paste it somewhere safe. Keep it private. It will not be displayed again, so if you lose it, you have to get another one (if that happens, there's an option in invalidate and refresh)

4. Set the token as an environment variable

- macOS/Linux (bash/zsh):
  - export HUGGING_FACE_AUTH_TOKEN=hf_your_token_here
  - To have it automatically set in the future, you can use `echo "export HUGGING_FACE_AUTH_TOKEN=hf_your_token_here" >> ~/.zshrc`
- Windows PowerShell (This is AI-generated. Use at your own risk. I'd use WSL instead):
  - setx HUGGING_FACE_AUTH_TOKEN "hf_your_token_here"

Notes

- Only the pyannote diarization pipeline and segmentation requires the token; Faster-Whisper itself does not use Hugging Face auth.
- If you see a 401/403 error, ensure the token is set in your environment and that you accepted the model terms above.

### Run from GitHub Container Registry (no build or download required)

Prebuilt multi-arch Docker images (amd64 + arm64) are published to Github's GHCR. Replace the token below with your own. You'll need to figure out how to install Docker or Docker Desktop yourself.

When you've got it, here are docker commands to run the web interface and CLI:

Web UI:

```
docker run --rm -p 5000:5000 \
   -e HUGGING_FACE_AUTH_TOKEN=$HUGGING_FACE_AUTH_TOKEN \
   -v "$(pwd)/uploads:/app/uploads" \
   ghcr.io/literatecomputing/transcribe-with-whisper-web:latest
```

After that, you can open http://localhost:5000 in your web browser.

CLI:

```
docker run --rm -it \
   -e HUGGING_FACE_AUTH_TOKEN=$HUGGING_FACE_AUTH_TOKEN \
   -v "$(pwd):/data" \
   ghcr.io/literatecomputing/transcribe-with-whisper-cli:latest \
   myfile.mp4 "Speaker 1" "Speaker 2"
```

This assumes that "myfile.mp4" is in the same directory/folder that you are in when you run that command (the `-v $(pwd):/data` part gives docker access to the current directory).

### Shell scripts exist in (bin/) -- Available if you have cloned this repo

These are some shortcuts that will run the commands above. The above are more flexible, but these have sensible defaults and don't require you to know anything.

- `bin/transcribe-with-whisper.sh` — runs the Web UI
- `bin/transcribe-with-whisper-cli.sh` — runs the CLI

Usage:

```
# Make sure they’re executable (first time only)
chmod +x bin/*.sh

# Web UI (then open http://localhost:5000)
export HUGGING_FACE_AUTH_TOKEN=hf_xxx
./bin/transcribe-with-whisper.sh

# CLI
export HUGGING_FACE_AUTH_TOKEN=hf_xxx
./bin/transcribe-with-whisper-cli.sh myfile.mp4 "Speaker 1" "Speaker 2"
```

Environment overrides:

- `TWW_PORT` — web port (default: 5000)
- `TWW_UPLOADS_DIR` — host uploads directory for the web server (default: `./uploads`)
- `TWW_CLI_MOUNT_DIR` — host directory to mount at `/data` for the CLI (default: current directory)

These scripts pull and run the prebuilt multi-arch images from GHCR, so you don’t need to build locally.

## 🛠️ Running without Docker

If you know a bit about Python and command lines, you might prefer to use the Python version and skip fooling with Docker.

On a fresh Ubuntu 24.04 installation, this works:

```
apt update
apt install -y python3-pip python3.12-venv ffmpeg
python3 -m venv venv
source venv/bin/activate
pip install transcribe-with-whisper
```

These need to be modified:

```
export HUGGING_FACE_AUTH_TOKEN=hf_your_access_token
transcribe-with-whisper your-video.mp4
```

The script checks to see what may be missing, so there's no harm in running it just to see if it works. When it doesn't you can come back and follow this guide. Also the commands that install the various pieces won't hurt anything if you run them when the tool is already installed.

The Windows installation instructions are written by ChatGPT and are not tested. The last version of Windows that I used for more than 15 minutes at a time was [Windows 95](https://en.wikipedia.org/wiki/Windows_95), and that was mostly to make it work for other people.

| Requirement                                | Why it's needed                                           |
| ------------------------------------------ | --------------------------------------------------------- |
| **Python 3**                               | The script is written in Python.                          |
| **ffmpeg**                                 | To convert video/audio files so the script can read them. |
| **Hugging Face account + access token**    | For using the speech / speaker models.                    |
| **Access to specific Hugging Face models** | Some models have terms or require you to request access.  |
| **Some Python package-manager experience** | Installing dependencies (but instructions are given).     |

---

## ✅ Installation & Setup — Step by Step

Below are clear steps by platform. Do them in order. Each “terminal / command prompt” line is something you type and run.

To open a Terminal on a Mac, you can type a command-space and type "terminal". This will open what some people call a "black box" where you type commands that the system processes.

---

### 1. Install basic tools

#### **macOS** (Intel or Apple Silicon)

1. Install **Homebrew** (if you don’t already have it):
   Open Terminal and paste:

   ```bash
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   ```

````

2. Use Homebrew to install `ffmpeg`:

```
brew install ffmpeg
```

3. Make sure you have Python 3:

```
brew install python
```

---

#### **Linux** (Ubuntu / Debian)

Open Terminal and run:

```
sudo apt update
sudo apt install ffmpeg python3 python3-pip -y
```

---

#### **Windows**

1. Install **Python 3** from [python.org](https://www.python.org/downloads/). During setup, choose the option to **Add Python to PATH**.
2. Install **ffmpeg**:

- Option A: use **Chocolatey** (if you have it)

```
choco install ffmpeg
```

- Option B: go to [ffmpeg.org/downloads](https://ffmpeg.org/download.html), download the build for Windows, and follow their instructions to put `ffmpeg.exe` somewhere in your PATH.

---

### 2. Get a Hugging Face account and access

1. Go to [huggingface.co](huggingface.co) and **create a free account** if you don’t already have one.
2. Request access to these models (you may need to accept licensing terms or fill out a request form):

- [`pyannote/speaker-diarization-3.1`](https://huggingface.co/pyannote/speaker-diarization-3.1)
- [`pyannote/segmentation`](https://huggingface.co/pyannote/segmentation)

3. Generate an **Access Token**:

- Log in to your Hugging Face account
- Go to [Settings → Access Tokens](https://huggingface.co/settings/tokens)
- Click **“Create new token”** — you can name it anything (e.g. “transcribe-tool”)
- Grant **read** access (click "read" right next to "Fine-grained")
- Copy the token somewhere safe (you’ll use it soon and it won't show it again!)

---

### 3. Configure your token on your computer

You need to tell your computer what your Hugging Face token is. This is so the script can access the models when it runs.

- **macOS / Linux** (in Terminal)

**PAY ATTENTION HERE!** See where it says "your_token_here" in the section below? You'll need to edit the the commands below. The easiest way is to paste this and then hit the up arrow to get back to the "export" command, use the arrow keys (**YOUR MOUSE WILL NOT WORK!!!**), and paste (using the command-V key) the token there "your_token_here" was.

```
echo 'export HUGGING_FACE_AUTH_TOKEN=your_token_here' >> ~/.zshrc
source ~/.zshrc
```

If you use `bash` instead of `zsh` (you would know if you did; zsh has been the default since Catalina in 2019) you can use this instead (and this won't hurt if you are not reading these instructions; you'll still need to use your actual token and not the words "your_token_here)

```
echo 'export HUGGING_FACE_AUTH_TOKEN=your_token_here' >> ~/.bashrc
source ~/.bashrc
```

- **Windows** (PowerShell)

```
setx HUGGING_FACE_AUTH_TOKEN "your_token_here"
```

Replace `your_token_here` with **your actual token** (that you copied from Hugging Face).

---

### 4. Install the Python dependencies

Open Terminal or Command Prompt (depending on your OS), navigate to the folder where this tool is, then run:

```
pip install pyannote.audio pydub faster-whisper webvtt-py huggingface_hub
```

---

### 5. Run the program

Put your video file in the same folder as the script. Then run:

```
python3 transcribe.py myvideo.mp4
```

If you want to name the speakers yourself, you can provide names after the filename. For example:

```
python3 transcribe.py myvideo.mp4 Alice Bob Charlie
```

- The script will then label speakers using **Alice**, **Bob**, **Charlie** instead of “Speaker 1”, “Speaker 2”, etc.
- If you don’t provide names, it will default to Speaker 1, 2, 3.

---

## 📂 What you get

After the script runs:

- An HTML file, e.g. `myvideo.html` — open this in your web browser
- The resulting page will show the video plus a transcript; clicking on transcript sections jumps the video to that moment

---

## ⚠️ Some helpful notes

- The first time you run this, it may download some large model files. That is normal; it might take a few minutes depending on your internet speed.

- On Macs with Apple Silicon (M1/M2/M3/M4), the default setup will still work, but performance may be slower than if you install optional “GPU / CoreML”-enabled packages.

- If something fails (missing library, inaccessible model, missing token), the script will try to give a friendly error message. If you see a message you don’t understand, you can share it with someone technical or open an issue.

---

## ✅ Summary Checklist

- Installed ffmpeg
- Installed Python 3 + pip
- Made a Hugging Face account
- Requested access to required models
- Created a Hugging Face token
- Set the environment variable `HUGGING_FACE_AUTH_TOKEN`
- Installed Python dependencies
- Ran the script (with optional speaker names)

---

Thanks for using this tool! If you share feedback, suggestions, or report problems, happy to help.

### Optional GPU Support (for NVIDIA users)

If you have an NVIDIA GPU and want faster transcription:

1. Install the GPU PyTorch wheels manually:

```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

## Docker

Two Docker images are provided to avoid local dependency hassles (especially on macOS):

- Web server (FastAPI): Dockerfile
- CLI runner: Dockerfile.cli

Build:

```
docker build -t tww-web -f Dockerfile .
docker build -t tww-cli -f Dockerfile.cli .
```

Run the web UI (browse to http://localhost:5000):

```
docker run --rm -p 5000:5000 \
   -e HUGGING_FACE_AUTH_TOKEN=$HUGGING_FACE_AUTH_TOKEN \
   -v $(pwd)/uploads:/app/uploads \
   tww-web
```

Run the CLI in a container:

```
docker run --rm -it \
   -e HUGGING_FACE_AUTH_TOKEN=hf_xxx \
   -v $(pwd):/data \
   tww-cli myfile.mp4 "Speaker 1" "Speaker 2"
```

The output HTML will appear in your mounted directory (`uploads/` for the web server, or the same folder as your media for CLI).
````
