# whisper-transcribe-to-html

This script creates speaker-aware transcripts from video files, and
outputs an HTML file where you can click on the transcript to jump to
the video. Works on macOS (Intel & Apple Silicon), Linux, and Windows.

---

## What this does

- Takes a video file (.mp4, .mov, or .mkv) and creates an audio-only file (.wav)
- Separates who is speaking when (speaker diarization using [pyannote/speaker-diarization](https://huggingface.co/pyannote/speaker-diarization), a free AI model)
- Transcribes each speaker's speech using the Faster Whisper Python library
- Produces an HTML file: you click on parts of the transcript, the video jumps to that moment
- The HTML file and the original video file are required to view the transcription in a web browser

---

## 🛠️ What you need to make this work

These are tools and services required. These are Open Source tools that are available for all operating systems. Though they may seem confusing to install, I've tried to make the process as clear and simple as possible.


| Requirement                                | Why it's needed                                           |
|--------------------------------------------|-----------------------------------------------------------|
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
  * Option A: use **Chocolatey** (if you have it)

```
choco install ffmpeg
```

  * Option B: go to [ffmpeg.org/downloads](https://ffmpeg.org/download.html), download the build for Windows, and follow their instructions to put `ffmpeg.exe` somewhere in your PATH.

---

### 2. Get a Hugging Face account and access

1. Go to huggingface.co and **create a free account** if you don’t already have one.
2. Request access to these models (you may need to accept licensing terms or fill out a request form):
  * `pyannote/speaker-diarization`
  * `pyannote/segmentation`
3. Generate an **Access Token**:
  * Log in to your Hugging Face account
  * Go to Settings → Tokens
  * Click **“New Token”** — you can name it anything (e.g. “transcribe-tool”)
  * Grant **read** access
  * Copy the token somewhere safe (you’ll use it soon)

---

### 3. Configure your token on your computer

You need to tell your computer what your Hugging Face token is. This is so the script can access the models when it runs.

* **macOS / Linux** (in Terminal)

```
echo 'export HUGGING_FACE_AUTH_TOKEN=your_token_here' >> ~/.bashrc
source ~/.bashrc
```

* **Windows** (PowerShell)

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

* The script will then label speakers using **Alice**, **Bob**, **Charlie** instead of “Speaker 1”, “Speaker 2”, etc.
* If you don’t provide names, it will default to Speaker 1, 2, 3.

---

## 📂 What you get

After the script runs:

* An HTML file, e.g. `myvideo.html` — open this in your web browser
* The resulting page will show the video plus a transcript; clicking on transcript sections jumps the video to that moment

---

## ⚠️ Some helpful notes

* The first time you run this, it may download some large model files. That is normal; it might take a few minutes depending on your internet speed.
* On Macs with Apple Silicon (M1/M2/M3/M4), the default setup will still work, but performance may be slower than if you install optional “GPU / CoreML”-enabled packages.
* If something fails (missing library, inaccessible model, missing token), the script will try to give a friendly error message. If you see a message you don’t understand, you can share it with someone technical or open an issue.

---

## 🧰 Optional (for more advanced users)

* You can add a `requirements.txt` so people can run:

```
pip install -r requirements.txt
```

* You might package this as a Python package so it’s installable via `pip install .`

---

## ✅ Summary Checklist

* Installed ffmpeg
* Installed Python 3 + pip
* Made a Hugging Face account
* Requested access to required models
* Created a Hugging Face token
* Set the environment variable `HUGGING_FACE_AUTH_TOKEN`
* Installed Python dependencies
* Ran the script (with optional speaker names)

---

Thanks for using this tool! If you share feedback, suggestions, or report problems, happy to help.

```
---

Do you want me to also generate a **`requirements.txt`** for this project so users can skip manually installing each dependency?
```
