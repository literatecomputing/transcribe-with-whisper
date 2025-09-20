# transcribe-with-whisper

This script creates speaker-aware transcripts from video files, and
outputs an HTML file where you can click on the transcript to jump to
the video. Works on macOS (Intel & Apple Silicon), Linux, and Windows.

I've tried very hard to make it work for people whose computer expertise includes little more than being able to install computer programs from a web page and click on stuff in a web browser.

---

## What this does

- Takes a video file (.mp4, .mov, or .mkv) and creates an audio-only file (.wav) for Whisper to process. I think that only mp4 files are likely to display in your browser, but don't know right now.
- Separates who is speaking when (speaker diarization using [pyannote/speaker-diarization](https://huggingface.co/pyannote/speaker-diarization), a free AI model)
- Transcribes each speaker's speech using the [Faster Whisper](https://github.com/SYSTRAN/faster-whisper) Python library
- Produces an HTML file: you click on parts of the transcript, the video jumps to that moment
- The HTML file and the original video file are required to view the transcription in a web browser

Faster-Whisper doesn't know about different speakers, so the code uses another model to split the transcript into pieces by speaker that are then handed off to Whisper.

I can't find a good source what languages are supported, but something that seemed only mildly dubious claimed it was close to 100.

---

## What Is Required? An Overview

- A Hugging Face Auth Token
- Python or Docker

However you use this, you need to have a Hugging Face Auth Token to download the AI model that does diarization (distinguishing multiple speakers in the transcript). Details below.

This is a Python package. If you're comfortable with Python, you can probably just `pip3 install transcribe-with-whisper` and the rest (like installing ffmpep) will make sense. After you install you would do something like "transcribe-with-whisper myvideofile.mp4 Harper Jordan Riley" and it'll create an HTML file with the transcript and a player for the video.

If you're not comfortable with Python, you can install [Docker Desktop](https://docs.docker.com/desktop/) (or Docker engine) and use a Docker container that's updated automatically, and similarly run a command, or start up a container that will let you provide the file and speaker names in your web browser.

If you don't know which of those you are more comfortable with, the answer is probably Docker. If you don't know what [`brew`](https://brew.sh/) is, you probably want Docker.

### Hugging Face Auth Token is required

A couple of AI Models available at [Hugging Face](https://huggingface.co/) are required to make this work. Hugging Face requires you to create an account and request permission to use these models (permission is granted immediately). An Auth Token (a fancy name for a combined username and password, sort of) is required for this program to download those models. Here's how to get the HUGGING_FACE_AUTH_TOKEN.

1. Create a free Hugging Face account

- https://huggingface.co/join

2. Request access to each of the required models--click "Use this model" for Pyannote.audio and accept their terms.

- Required: pyannote/speaker-diarization-3.1 → https://huggingface.co/pyannote/speaker-diarization-3.1
- Required: pyannote/segmentation → https://huggingface.co/pyannote/segmentation
- On each model page, click Use this model” and select "pyannote.audio". Access is typically approved instantly for free use. After you have accepted it, you should see "**Gated Model** You have been granted access to this model". You can also check which models you have access to at https://huggingface.co/settings/gated-repos.

3. Create a read-access token

- Go to https://huggingface.co/settings/tokens
- Click “Create new token” and then Read
- Enter a token name (maybe the computer you're using and/or the date) and click the "Create token" button.
- Copy the token (looks like `hf_...`) and paste it somewhere safe. Keep it private. It will not be displayed again, so if you lose it, you have to get another one (if that happens, there's an option in invalidate and refresh; it's not a big deal).

4. Set the token as an environment variable

- macOS/Linux (bash/zsh):
  - export HUGGING_FACE_AUTH_TOKEN=hf_your_token_here
  - To have it automatically set in the future, you can use `echo "export HUGGING_FACE_AUTH_TOKEN=hf_your_token_here" >> ~/.zshrc`
- Windows PowerShell (This is AI-generated. Use at your own risk. I'd use WSL instead):
  - setx HUGGING_FACE_AUTH_TOKEN "hf_your_token_here"

Notes

- Only the pyannote diarization pipeline and segmentation requires the token; Faster-Whisper itself does not use Hugging Face auth.
- If you see a 401/403 error, ensure the token is set in your environment and that you accepted the model terms above.

### Got Docker?

If you don't have Docker installed. You should head over to the [Docker Desktop](https://docs.docker.com/desktop/) page and find the installation instructions. Maybe you don't care what Docker is and just want the download instructions for [Mac](https://docs.docker.com/desktop/setup/install/mac-install/), [Windows](https://docs.docker.com/desktop/setup/install/windows-install/), or [Linux](https://docs.docker.com/desktop/setup/install/linux/.)

Remember above when it said that you needed to do this?

```
export HUGGING_FACE_AUTH_TOKEN=hf_your_token_here
```

Well, that's what makes the second line of the command below work.

You'll need to open a terminal and paste this in. On a Mac you can type "command-space" and then "termin" for it to suggest the terminal program.

#### Web User Interface

```
docker run --rm -p 5000:5000 \
   -e HUGGING_FACE_AUTH_TOKEN=$HUGGING_FACE_AUTH_TOKEN \
   -v "$(pwd)/uploads:/app/uploads" \
   ghcr.io/literatecomputing/transcribe-with-whisper-web:latest
```

After that, you can open http://localhost:5000 in your web browser. The transcribed file will open in your browser and also be in the uploads folder that is created in the folder/directory where you run the above command.

#### Command Line Interface

```
docker run --rm -it \
   -e HUGGING_FACE_AUTH_TOKEN=$HUGGING_FACE_AUTH_TOKEN \
   -v "$(pwd):/data" \
   ghcr.io/literatecomputing/transcribe-with-whisper-cli:latest \
   myfile.mp4 "Speaker 1" "Speaker 2"
```

This assumes that "myfile.mp4" is in the same directory/folder that you are in when you run that command (pro tip: the `-v $(pwd):/data` part gives docker access to the current directory).

### Shell scripts exist in (bin/)

These are some shortcuts that will run the commands above. The above are more flexible, but these have sensible defaults and don't require you to know anything. If you don't know how to clone this repository, then just download the file you want from [here](https://github.com/literatecomputing/transcribe-with-whisper/tree/main/bin).

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

You can safely copy/paste the above, but these need for you to pay attention.

```
export HUGGING_FACE_AUTH_TOKEN=hf_your_access_token
transcribe-with-whisper your-video.mp4
```

The script checks to see what may be missing, and tries to tell you what to do, so there's no harm in running it just to see if it works. When it doesn't you can come back and follow this guide. Also the commands that install the various pieces won't hurt anything if you run them when the tool is already installed.

The Windows installation instructions are written by ChatGPT and are not tested. The last version of Windows that I used for more than 15 minutes at a time was [Windows 95](https://en.wikipedia.org/wiki/Windows_95), and that was mostly to make it work for other people.

| Requirement                                | Why it's needed                                           |
| ------------------------------------------ | --------------------------------------------------------- |
| **Python 3**                               | The script is written in Python.                          |
| **ffmpeg**                                 | To convert video/audio files so the script can read them. |
| **Hugging Face account + access token**    | For using the speech / speaker models.                    |
| **Access to specific Hugging Face models** | Some models have terms or require you to request access.  |
| **Some Python package-manager experience** | You might have to fuss with dependencies                  |

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

I had some instructions written by an AI, but they looked pretty bogus, so I deleted them. I think you'd want to use [WSL](https://learn.microsoft.com/en-us/windows/wsl/install), and then follow the above Linux instructions, but since WSL didn't exist in Windows 95, I don't know much about it.

---

### 3. Configure your token on your computer

You need to tell your computer what your Hugging Face token is. This is so the script can access the models when it runs. Hopefully you got the token above and already did the "export" part once. The instructions below will put that in a place that will automatically get executed when you open a new terminal.

- **macOS / Linux** (in Terminal)

**PAY ATTENTION HERE!** See where it says "your_token_here" in the section below? You'll need to edit the the commands below. The easiest way is to paste this and then hit the up arrow to get back to the "export" command, use the arrow keys (**YOUR MOUSE WILL NOT WORK!!!**), and paste (using the command-V key) the token there "your_token_here" was.

```
echo 'export HUGGING_FACE_AUTH_TOKEN=your_token_here' >> ~/.zshrc
source ~/.zshrc
```

If you use Linux, you use `bash` instead of `zsh` , so do this instead:

```
echo 'export HUGGING_FACE_AUTH_TOKEN=your_token_here' >> ~/.bashrc
source ~/.bashrc
```

---

## What you get

After the script runs:

- An HTML file, e.g. `myvideo.html` — open this in your web browser
- The resulting page will show the video plus a transcript; clicking on transcript sections jumps the video to that moment

---

## ⚠️ Some helpful notes

- The first time you run this, it may download some large model files. That is normal; it might take a few minutes depending on your internet speed.

- On Macs with Apple Silicon (M1/M2/M3/M4), the default setup will still work, but performance may be slower than if you install optional “GPU / CoreML”-enabled packages.

- If something fails (missing library, inaccessible model, missing token), the script will try to give a friendly error message. If you see a message you don’t understand, you can share it with someone technical or open an issue.
