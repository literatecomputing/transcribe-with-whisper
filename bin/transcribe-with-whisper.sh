#!/usr/bin/env bash
set -euo pipefail

IMAGE="${TWW_WEB_IMAGE:-ghcr.io/literatecomputing/transcribe-with-whisper-web:latest}"
PORT="${TWW_PORT:-5001}"

# if TRANSCRIPTION_DIR is set, use it
# else use $(pwd)/transcription-files as default
TRANSCRIPTION_DIR="${TRANSCRIPTION_DIR:-$(pwd)/transcription-files}"


if ! command -v docker >/dev/null 2>&1; then
  echo "Error: docker is not installed or not in PATH." >&2
  exit 1
fi

if [[ -z "${HUGGING_FACE_AUTH_TOKEN:-}" ]]; then
  echo "Error: HUGGING_FACE_AUTH_TOKEN is not set." >&2
  echo "Export it or run with: HUGGING_FACE_AUTH_TOKEN=hf_xxx $0" >&2
  exit 1
fi

mkdir -p "${TRANSCRIPTION_DIR}"

echo "Starting web UI on http://localhost:${PORT}"
exec docker run --rm \
  -p "${PORT}:5001" \
  -e "HUGGING_FACE_AUTH_TOKEN=${HUGGING_FACE_AUTH_TOKEN}" \
  -e "TRANSCRIPTION_DIR=/app/transcription-files" \
  -v "${TRANSCRIPTION_DIR}:/app/transcription-files" \
  "${IMAGE}"
