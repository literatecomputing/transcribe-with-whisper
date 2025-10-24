# transcribe-with-whisper

This set of tools is for people who need to transcribe video (or audio) files, but must protect the privacy of the people in the data set. This uses free AI tools and models to transcribe video and audio files to an HTML file that will show the transcript in your web browser and let you click on a word to be taken to that section of the original data file. A script to convert the HTML to docx is also included.

The `docx` files created include the speaker and timestamp so that it should be compatible with MAXQDA's [timestamps](https://www.maxqda.com/help-mx24/import/transcripts).

It works on macOS (Intel & Apple Silicon), Linux, and Windows (not well tested).

I've tried very hard to make it work for people whose computer expertise includes little more than being able to install computer programs from a web page and click on stuff in a web browser.

---

## Quick start

Two ways to use this project:

- MercuryScribe (Web UI)

  - Best for editing and reviewing in your browser
  - Programmer Install: `pip install "transcribe-with-whisper[web]"`
  - Docker Install:

  ```
  docker run --rm -p 5001:5001 \
   -v "$(pwd)/mercuryscribe:/app/mercuryscribe" \
   ghcr.io/literatecomputing/transcribe-with-whisper-web:latest
  ```

  - Run: `mercuryscribe` then open http://localhost:5001
  - More: see `docs/README-mercuryscribe.md`

  The web interface will walk you through getting an access token from Hugging Face (described more fully below).

- transcribe-with-whisper (CLI)
  - Best for batch processing from the command line
  - Install: `pip install transcribe-with-whisper`
  - Run: `transcribe-with-whisper yourfile.mp4 [Speaker1 Speaker2 ...]`
  - More: see `docs/README-transcribe-with-whisper.md`

## Releases

We publish three main kinds of distributable artifacts for this project:

- Docker images (multi-arch) pushed to GitHub Container Registry (GHCR) — these include `-web` and `-cli` images.
- Windows bundle (a packaged Python distribution containing `MercuryScribe.exe`, a `start-server.bat`, and helper files) — produced by the Windows PyInstaller job and attached as build artifacts / release assets.
- Python package on PyPI (`transcribe-with-whisper`) — sdist and wheel uploaded to PyPI on release.

How releases are triggered
-------------------------

There are two common ways CI publishes these artifacts:

- Git tag pushes (recommended): create an annotated tag like `v1.2.3` and push it (`git tag -a v1.2.3 -m "Release v1.2.3" && git push origin v1.2.3`). Workflows that listen for tag pushes (refs/tags/v*) will build and publish artifacts.
- GitHub Releases: creating a Release in the GitHub UI (which normally creates a tag for you). Workflows that listen for the `release.published` event will run and publish artifacts.

Which to use?

- Recommended: push an annotated tag. Tags are explicit, scriptable, and reproducible. Creating releases from the tag is fine (the CI will pick up either event if configured).
- If you prefer the GitHub UI, create a Release and publish it there — CI workflows that listen for `release.published` will behave the same as tag pushes if configured.

Manual and pre-release checks
-----------------------------

- All artifact-producing workflows in this repository are designed to run validation on pull requests (so PRs validate buildability), but they will not upload or publish artifacts for PR runs. This prevents large artifacts from appearing on PRs and keeps publishing gated to releases.
- Maintainers can run builds manually via `workflow_dispatch`. Whether manual runs publish artifacts is decided per-workflow; in general, manual runs can be used to produce artifacts for debugging or to create a release candidate.

Where to find published artifacts
---------------------------------

- Docker images: GHCR under `ghcr.io/literatecomputing/` (image names include `transcribe-with-whisper-web` and `transcribe-with-whisper-cli`). See the Actions run logs for exact tag names (e.g., `latest-amd64`, `v1.2.3`).
- Windows bundle: attached as an artifact on the GitHub Actions run and typically added to a GitHub Release as an asset.
- PyPI package: uploaded to PyPI as `transcribe-with-whisper`.

Policy and details
------------------

See `.github/trigger-policy.md` for the CI trigger policy, a recommended guard expression to protect upload/publish steps, and examples for guarding Docker pushes and artifact uploads.


## What transcribe-with-whisper Does

TL;DR: takes a video file, makes an HTML page that tracks the transcription with the playing video and makes video jump to text that you click. A `.docx` file with timestamps, which should be suitable for use with packages like MAXQDA is also created.

## What mercuryScribe Does

MercuryScribe is a web-based front end (the web server runs on your computer if you follow the instructions above) for transcribe-with-whisper. The server lets you make edits to the transcript in your web browser, and save them to the `.VTT` files that transcribe-with-whisper produced (and some software might find useful). You can then click a button to regenerate the HTML and DOCX files to pull those changes into updated HTML and DOCX files.

## What does it look like?

Well, there have been a few changes since this image was taken, but very much like this:

![NotebookLM Nonsense Demo](examples/notebooklm-nonsense.png)

If you'd like to see a live demo (that does not allow you to save your changes), check this out!

**[📺 View Live Demo](https://raw.githack.com/literatecomputing/transcribe-with-whisper/main/examples/notebooklm-nonsense.html)** - Interactive HTML transcription with synchronized video playback

## Are there boring details that most people would rather not know about?

Why yes! Here's what happens under the hood.

- **Convert to a .wav file.** The script takes a video file (.mp4, .mov, or .mkv) and creates an audio-only file (.wav) for Whisper to process. I think that only mp4 files are likely to display in your browser, but don't know right now. It also works for mp3 (and probably other audio formats).

- **Separate who is speaking when** (speaker diarization using [pyannote/speaker-diarization-community-1](https://huggingface.co/pyannote/speaker-diarization-community-1), a free AI model). This splits the file into multiple audio files that get deleted before you notice them.

- **Do the Transcription** Transcribes each speaker's speech using the [Faster Whisper](https://github.com/SYSTRAN/faster-whisper) Python library

- **Produces an HTML file**. The HTML file includes not only the text, but some Javascript that makes it possible to edit in your browser (but the mercurytScribe server is required to process those edits). You click on parts of the transcript, the video jumps to that moment so you can check the transcription, or jump to the parts you want to listen to. The original video file needs to be in the same folder/directory in order for the video to display in your browser.

---

## What Is Required? An Overview

tl;dr:

- A Hugging Face Auth Token
- [Python](https://www.python.org/) or [Docker](https://docs.docker.com/desktop/)

However you use this, you need to have a Hugging Face Auth Token to download the AI model ([What is a model?](https://huggingface.co/docs/hub/en/models)) that does diarization (distinguishing multiple speakers in the transcript). Details below.

This is a Python package. If you're comfortable with Python, you can probably just `pip3 install transcribe-with-whisper` and the rest (like installing `ffmpeg` with `brew`) will make sense. After you install you would do something like "transcribe-with-whisper myvideofile.mp4 Harper Jordan Riley" and it'll create an HTML file with the transcript and a player for the video.

If you're not comfortable with Python, you can install [Docker Desktop](https://docs.docker.com/desktop/) (or Docker engine) and use a Docker container that's updated automatically, and similarly run a command, or start up a container that will let you provide the file and speaker names in your web browser.

If you don't know which of those you are more comfortable with, the answer is probably Docker. If you don't know what [`brew`](https://brew.sh/) is, you probably want Docker.

### Hugging Face Auth Token is required (You have to read this!)

A couple of AI Models available at [Hugging Face](https://huggingface.co/) are required to make this work. Hugging Face requires you to create an account and request permission to use these models (permission is granted immediately). An Auth Token (a fancy name for a combined username and password, sort of) is required for this program to download those models. Here's how to get the HUGGING_FACE_AUTH_TOKEN.

1. Create a free Hugging Face account

- https://huggingface.co/join

2. Request access to each of the required models—click "Use this model" for pyannote.audio and accept their terms.

On each model page linked below, click “Use this model” and select "pyannote.audio" (pyannote.audio is a Python library). After you have accepted their terms, you should see "**Gated Model** You have been granted access to this model". You can also check which models you have access to at https://huggingface.co/settings/gated-repos.

#### Request Access for these Models!

- Required: pyannote/speaker-diarization-community-1 → https://huggingface.co/pyannote/speaker-diarization-community-1
- Required: pyannote/segmentation-3.0 → https://huggingface.co/pyannote/segmentation-3.0

3. Create a read-access token

- Go to https://huggingface.co/settings/tokens
- Click “Create new token” and then select the "Read" token type.
- Enter a token name (maybe the computer you're using and/or the date) and click the "Create token" button.
- Copy the token (looks like `hf_...`) and paste it somewhere safe. Keep it private. It will not be displayed again, so if you lose it, you have to get another one (if that happens, there's an option in invalidate and refresh; it's not a big deal).

4. Set the token as an environment variable

- Linux/Windows WSL (bash):

```bash
export HUGGING_FACE_AUTH_TOKEN=hf_your_token_here
echo "export HUGGING_FACE_AUTH_TOKEN=$HUGGING_FACE_AUTH_TOKEN" >> ~/.bashrc
```

- For Mac (which uses zsh by default) use this to have it automatically added to your environment

```bash
export HUGGING_FACE_AUTH_TOKEN=hf_your_token_here
echo "export HUGGING_FACE_AUTH_TOKEN=$HUGGING_FACE_AUTH_TOKEN" >> ~/.zshrc
```

For both of the above examples, the first line sets the variable for the current terminal session and the second one adds it to a file that is read so that it will be set automatically in new terminal sessions.

- Windows (Command Prompt/PowerShell):

```cmd
set HUGGING_FACE_AUTH_TOKEN="hf_your_token_here"
setx HUGGING_FACE_AUTH_TOKEN "%HUGGING_FACE_AUTH_TOKEN%"
```

_Note: The `set` command sets the value for the current session, the `setx` command copies that value to make it permanent for future sessions._

Notes

- Only the pyannote diarization pipeline and segmentation requires the token; Faster-Whisper itself does not use Hugging Face auth.
- If you see a 401/403 error, ensure the token is set in your environment and that you accepted the model terms above.

### Got Docker? (It's Easier for most people)

If you don't have Docker installed. You should head over to the [Docker Desktop](https://docs.docker.com/desktop/) page and find the installation instructions. Maybe you don't care what Docker is and just want the download instructions for [Mac](https://docs.docker.com/desktop/setup/install/mac-install/), [Windows](https://docs.docker.com/desktop/setup/install/windows-install/), or [Linux](https://docs.docker.com/desktop/setup/install/linux/.)

If you use Windows, Docker requires you to install WSL ([https://learn.microsoft.com/en-us/windows/wsl/about](Windows Subsystem for Linux)). Instructions below assume that you are running `bash` as your shell; apparently, if you install [Windows Terminal](https://apps.microsoft.com/detail/9n0dx20hk701?wtExtndSource=cfm_UASTLP_myATT_LFM_MicrosoftStore&hl=en-US&gl=US) then, well, I don't know.

Remember above when it said that you needed to do this?

```
export HUGGING_FACE_AUTH_TOKEN=hf_your_token_here
```

Well, that's what makes the second line of the command below work.

You'll need to open a terminal and paste this in. On a Mac you can type "command-space" and then "terminal".

#### Web User Interface

**Linux/Mac/WSL (bash/zsh):**

```bash
docker pull ghcr.io/literatecomputing/transcribe-with-whisper-web:latest
docker run --rm -p 5001:5001 \
   -v "$(pwd)/mercuryscribe:/app/mercuryscribe" \
   ghcr.io/literatecomputing/transcribe-with-whisper-web:latest
```

Once that's running, go to http://localhost:5001 and you should be on your way!

**Windows (PowerShell):**

If you can't figure out how to get Windows Terminal to run `bash`, this should work in PowerShell.

```powershell
docker pull ghcr.io/literatecomputing/transcribe-with-whisper-web:latest
docker run --rm -p 5001:5001 `
   -v "${PWD}/mercuryscribe:/app/mercuryscribe" `
   ghcr.io/literatecomputing/transcribe-with-whisper-web:latest
```

Once that's running, go to http://localhost:5001 and you should be on your way!

After that, you can open http://localhost:5001 in your web browser. The transcribed file will open in your browser and also be in the mercuryscribe folder that is created in the folder/directory where you run the above command. Both HTML and DOCX files are automatically generated for each transcription.

#### Command Line Interface

You do not need to edit this line, it uses the HUGGING_FACE_AUTH_TOKEN set above.

```bash
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
- `bin/html-to-docx.sh` -- converts the html file into a docx

Usage:

```
# Make sure they’re executable (first time only)
chmod +x bin/*.sh

# Web UI (then open http://localhost:5001)
export HUGGING_FACE_AUTH_TOKEN=hf_xxx
./bin/transcribe-with-whisper.sh

# CLI
export HUGGING_FACE_AUTH_TOKEN=hf_xxx
./bin/transcribe-with-whisper-cli.sh myfile.mp4 "Speaker 1" "Speaker 2"
```

Environment overrides:

- `TWW_PORT` — web port (default: 5001)
- `TWW_mercuryscribe_DIR` — host mercuryscribe directory for the web server (default: `./mercuryscribe`)
- `TWW_CLI_MOUNT_DIR` — host directory to mount at `/data` for the CLI (default: current directory)

These scripts pull and run the prebuilt multi-arch images from GHCR, so you don’t need to build locally.

## 🛠️ Running without Docker

If you know a bit about Python and command lines, you might prefer to use the Python version and skip the overhead of Docker (and see that dependencies are handled yourself!)

On a fresh Ubuntu 24.04 installation, this works:

```bash
apt update
apt install -y python3-pip python3.12-venv ffmpeg
python3 -m venv venv
source venv/bin/activate
pip install transcribe-with-whisper
```

This should work on a Mac:

```bash
brew update
brew install python ffmpeg
python3 -m venv venv
source venv/bin/activate
pip install transcribe-with-whisper
```

You can safely copy/paste the above, but these (same on all platforms) need for you to pay attention and insert your own token and filename.

```bash
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

I think that if you install WSL the Ubuntu instructions should work without changes.

---

### 3. Configure your token on your computer

You need to tell your computer what your Hugging Face token is. This is so the script can access the models when it runs. Hopefully you got the token above and already did the "export" part once. The instructions below will put that in a place that will automatically get executed when you open a new terminal.

- **macOS / Linux** (in Terminal)

**PAY ATTENTION HERE!** See where it says "your_token_here" in the section below? You'll need to edit the the commands below. The easiest way is to paste this and then hit the up arrow to get back to the "export" command, use the arrow keys (**YOUR MOUSE WILL NOT WORK!!!**), and paste (using the command-V key) the token there "your_token_here" was.

```
echo 'export HUGGING_FACE_AUTH_TOKEN=your_token_here' >> ~/.zshrc
source ~/.zshrc
```

If you use Linux or WSL, you use `bash` instead of `zsh` , so do this instead:

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

##

- The first time you run this, it may download some large model files. That is normal; it might take a few minutes depending on your internet speed. Subsequent runs will be much faster since those files will already have been downloaded.

- On Macs with Apple Silicon (M1/M2/M3/M4), the default setup will still work, but performance may be slower than if you install optional “GPU / CoreML”-enabled packages (and have any idea what that means).

- If something fails (missing library, inaccessible model, missing token), the script will try to give a friendly error message. If you see a message you don’t understand, you can share it with someone technical or open an issue.

## Converting the HTML to a Word Processing document

While the HTML is great for viewing the data, it's not convenient for other tools you might want to use. There is an `html-to-docx` script available that will convert the HTML into a docx file by default (you can also specify other formats like `html-to-docx file.html file.odt` or `html-to-docx file.html file.pdf`).

Note that some tools can work with the `.vtt` files that are created in the directory created with the same name as the original file (without the filename extension). If you want to edit the `.vtt` files, you can re-run the script and it'll create a new HTML file with the contents from the `.vtt` files. The `.vtt` files, however, do not include information about the speaker, which makes them less desirable.

## Recent Updates

- ✅ **Auto-DOCX Generation**: The web interface now automatically creates a `.docx` file alongside the HTML transcript
- ✅ **Fixed Video Player**: Video player stays pinned at the top of the browser window while scrolling through transcripts
- ✅ **Enhanced Timestamps**: Transcripts include speaker names and timestamps for better DOCX export

## TODO
why is sqlite3 and sqlalchemy and pandas hooks all included? We're not using those.