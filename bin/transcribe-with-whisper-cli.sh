#!/usr/bin/env bash
set -euo pipefail

IMAGE="ghcr.io/literatecomputing/transcribe-with-whisper-cli:latest"
MOUNT_DIR="${TWW_CLI_MOUNT_DIR:-$(pwd)}"

if ! command -v docker >/dev/null 2>&1; then
  echo "Error: docker is not installed or not in PATH." >&2
  exit 1
fi

if [[ -z "${HUGGING_FACE_AUTH_TOKEN:-}" ]]; then
  echo "Error: HUGGING_FACE_AUTH_TOKEN is not set." >&2
  echo "Export it or run with: HUGGING_FACE_AUTH_TOKEN=hf_xxx $0 <file> [speakers...]" >&2
  exit 1
fi

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <media-file> [Speaker1 Speaker2 ...]" >&2
  exit 1
fi

sudo docker run --network=host --rm -it \
  -e "HUGGING_FACE_AUTH_TOKEN=${HUGGING_FACE_AUTH_TOKEN}" \
  -v "${MOUNT_DIR}:/data" \
  "${IMAGE}" "$@"
