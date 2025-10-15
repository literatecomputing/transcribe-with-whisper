MercuryScribe (Windows bundle)

Quick start:
1. Unzip the archive you downloaded.
2. Double-click `start-server.bat` to start MercuryScribe.
3. Your browser should open to http://127.0.0.1:5001/. If it does not, open that URL manually.

Notes and troubleshooting:
- If the server fails to start, check the log at %LOCALAPPDATA%\MercuryScribe\mercuryscribe.log
- The app will prompt you for a Hugging Face access token on first run. Follow the in-app instructions.
- ffmpeg is bundled in the same folder as the exe; the bundle will use the included ffmpeg.
- This bundle does not include gated HF models. Use the web UI to provide a token with model access.
