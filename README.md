# whisper-transcribe-to-html

A tool that creates speaker-aware transcripts from video files, and outputs an HTML file where you can click on the transcript to jump to the video.
Works on macOS (Intel & Apple Silicon), Linux, and Windows.

---

## 🎯 What this does

- Takes a video file (.mp4, .mov, or .mkv)
- Separates who is speaking when (speaker diarization)
- Transcribes each speaker's speech
- Produces an HTML file: you click on parts of the transcript, the video jumps to that moment

---

## 🛠️ What you need to make this work

These are tools and services required. Even if you are not technically experienced, following the steps below carefully should get things working.

| Requirement | Why it's needed |
|-------------|------------------|
| **Python 3** | The script is written in Python. |
| **ffmpeg** | To convert video/audio files so the script can read them. |
| **Hugging Face account + access token** | For using the speech / speaker models. |
| **Access to specific Hugging Face models** | Some models have terms or require you to request access. |
| **Some Python package-manager experience** | Installing dependencies (but instructions are given). |

---

## ✅ Installation & Setup — Step by Step

Below are clear steps by platform. Do them in order. Each “terminal / command prompt” line is something you type and run.

---

### 1. Install basic tools

#### **macOS** (Intel or Apple Silicon)

1. Install **Homebrew** (if you don’t already have it):
   Open Terminal and paste:

   ```bash
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
