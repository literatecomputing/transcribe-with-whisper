#!/usr/bin/env bash
set -euo pipefail

IMAGE="ghcr.io/literatecomputing/transcribe-with-whisper-web:latest"
PORT="${TWW_PORT:-5001}"
UPLOADS_DIR="${TWW_UPLOADS_DIR:-$(pwd)/uploads}"

if ! command -v docker >/dev/null 2>&1; then
  echo "Error: docker is not installed or not in PATH." >&2
  exit 1
fi

if [[ -z "${HUGGING_FACE_AUTH_TOKEN:-}" ]]; then
  echo "Error: HUGGING_FACE_AUTH_TOKEN is not set." >&2
  echo "Export it or run with: HUGGING_FACE_AUTH_TOKEN=hf_xxx $0" >&2
  exit 1
fi

mkdir -p "${UPLOADS_DIR}"

echo "Starting web UI on http://localhost:${PORT}"
exec docker run --rm \
  -p "${PORT}:5001" \
  --network=host \
  -e "HUGGING_FACE_AUTH_TOKEN=${HUGGING_FACE_AUTH_TOKEN}" \
  -v "${UPLOADS_DIR}:/app/uploads" \
  "${IMAGE}"
