# transcribe-with-whisper (CLI)

This is the CLI tool for local, private transcription with diarization.

- Command: `transcribe-with-whisper yourfile.mp4 [Speaker1 Speaker2 ...]`
- Output: `yourfile.html` and a folder `yourfile/` with `.vtt` segments
- Optionally convert to DOCX using `bin/html-to-docx.sh yourfile.html`

See the main README for full setup (Hugging Face token, ffmpeg, etc.).
