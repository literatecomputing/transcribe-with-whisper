#!/usr/bin/env bash
set -euo pipefail

# Usage: ./bin/test-upload.sh [BASE_URL] [MEDIA_FILE]
# Defaults: BASE_URL=http://127.0.0.1:5001, MEDIA_FILE=examples/test-audio.mp3

BASE_URL=${1:-http://127.0.0.1:5001}
MEDIA_FILE=${2:-examples/test-audio.mp3}

if [[ ! -f "$MEDIA_FILE" ]]; then
  echo "❌ Media file not found: $MEDIA_FILE" >&2
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "❌ curl is required" >&2
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "❌ jq is required" >&2
  echo "   Install jq or adjust the script to use python for JSON parsing." >&2
  exit 1
fi

BASE_URL=${BASE_URL%/}
UPLOAD_URL="$BASE_URL/upload"
HEADERS_FILE=$(mktemp)
trap 'rm -f "$HEADERS_FILE"' EXIT

echo "📤 Uploading $MEDIA_FILE to $UPLOAD_URL"

curl -sS -D "$HEADERS_FILE" -o /dev/null \
  -F "file=@${MEDIA_FILE}" \
  "$UPLOAD_URL"

PROGRESS_PATH=$(awk 'tolower($1)=="location:" {print $2}' "$HEADERS_FILE" | tr -d '\r')
if [[ -z "$PROGRESS_PATH" ]]; then
  echo "❌ Upload response did not include a redirect Location header." >&2
  exit 1
fi

if [[ "$PROGRESS_PATH" == http* ]]; then
  PROGRESS_URL="$PROGRESS_PATH"
else
  PROGRESS_URL="$BASE_URL${PROGRESS_PATH}"
fi

JOB_ID=${PROGRESS_URL##*/}
JOB_API="$BASE_URL/api/job/$JOB_ID"

cat <<INFO
✅ Upload accepted.
   Progress page: $PROGRESS_URL
   Polling status via $JOB_API
INFO

while true; do
  RESPONSE=$(curl -sS "$JOB_API")
  STATUS=$(jq -r '.status // ""' <<<"$RESPONSE")
  PROGRESS=$(jq -r '.progress // 0' <<<"$RESPONSE")
  MESSAGE=$(jq -r '.message // ""' <<<"$RESPONSE")
  ERROR_TEXT=$(jq -r '.error // ""' <<<"$RESPONSE")

  printf '%s [%s] %3s%% %s\n' "$(date '+%H:%M:%S')" "$STATUS" "$PROGRESS" "$MESSAGE"

  case "$STATUS" in
    completed)
      RESULT=$(jq -r '.result // ""' <<<"$RESPONSE")
      break
      ;;
    error)
      echo "❌ Job failed: $ERROR_TEXT" >&2
      exit 1
      ;;
    *)
      sleep 5
      ;;
  esac
done

if [[ -n "$RESULT" ]]; then
  if [[ "$RESULT" == http* ]]; then
    RESULT_URL="$RESULT"
  else
    RESULT_URL="$BASE_URL${RESULT}"
  fi
  echo "🎉 Transcription complete!"
  echo "    HTML transcript: $RESULT_URL"
else
  echo "✅ Job completed, but no result URL was provided."
fi
