# whisper-transcribe-to-html

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

## 🛠️ What you need to make this work

These are tools and services required. These are Open Source tools that are available for all operating systems. Though they may seem confusing to install, I've tried to make the process as clear and simple as possible.

The script checks to see what may be missing, so there's no harm in running it just to see if it works. When it doesn't you can come back and follow this guide. Also the commands that install the various pieces won't hurt anything if you run them when the tool is already installed.

The Windows installation instructions are written by ChatGPT and are not tested. The last version of Windows that I used for more than 15 minutes at a time was [Windows 95](https://en.wikipedia.org/wiki/Windows_95), and that was mostly to make it work for other people.


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



1. Go to [huggingface.co](huggingface.co) and **create a free account** if you don’t already have one.
2. Request access to these models (you may need to accept licensing terms or fill out a request form):
  * [`pyannote/speaker-diarization-3.1`](https://huggingface.co/pyannote/speaker-diarization-3.1)
  * [`pyannote/segmentation`](https://huggingface.co/pyannote/segmentation)

3. Generate an **Access Token**:
  * Log in to your Hugging Face account
  * Go to [Settings → Access Tokens](https://huggingface.co/settings/tokens)
  * Click **“Create new token”** — you can name it anything (e.g. “transcribe-tool”)
  * Grant **read** access (click "read" right next to "Fine-grained")
  * Copy the token somewhere safe (you’ll use it soon and it won't show it again!)

---

### 3. Configure your token on your computer

You need to tell your computer what your Hugging Face token is. This is so the script can access the models when it runs.

* **macOS / Linux** (in Terminal)

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
