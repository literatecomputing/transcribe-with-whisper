  docker rm -f mercuryscribe || true
  docker pull ghcr.io/literatecomputing/transcribe-with-whisper-web:latest
  docker run --rm -p 5001:5001 \
   -v "$HOME/mercuryscribe:/app/mercuryscribe" \
   -e HUGGING_FACE_AUTH_TOKEN=$HUGGING_FACE_AUTH_TOKEN \
   --name mercuryscribe \
   -d \
   ghcr.io/literatecomputing/transcribe-with-whisper-web:latest


   cd ~/mercuryscribe
   rm -rf test-audio*
   cp ~/src/literatecomputing/transcribe-with-whisper/examples/test-audio.mp3 .

   sleep 15



# --- Poll-and-verify function
# poll_and_check <phrase>
poll_and_check() {
  local PHRASE="$1"
  local JOB_TIMEOUT_SECS=600

  echo "Starting polling for transcription job..."
  RESP_HEADERS=$(curl -s -i -X POST 'http://127.0.0.1:5001/rerun' -H 'Content-Type: application/x-www-form-urlencoded' --data-raw 'filename=test-audio.mp3' || true)
  echo "POST /rerun response headers:"; echo "$RESP_HEADERS" | sed -n '1,120p'

  LOCATION=$(printf "%s" "$RESP_HEADERS" | awk '/^[Ll]ocation: /{print $2}' | tr -d '\r')
  if [ -z "$LOCATION" ]; then
    echo "No Location header found; cannot determine job id. Aborting."
    return 1
  fi
  JOBID=$(basename "$LOCATION")
  echo "Detected job id: $JOBID (location: $LOCATION)"

  API_URL="http://127.0.0.1:5001/api/job/$JOBID"
  START_TS=$(date +%s)

  while true; do
    if [ $(( $(date +%s) - START_TS )) -gt $JOB_TIMEOUT_SECS ]; then
      echo "Timed out waiting for job $JOBID to finish after ${JOB_TIMEOUT_SECS}s"
      return 2
    fi

    JOUT=$(curl -s "$API_URL" || true)
    if [ -z "$JOUT" ]; then
      echo "Empty response from $API_URL — retrying..."
      sleep 2
      continue
    fi

    STATUS=$(printf "%s" "$JOUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))")
    PROG=$(printf "%s" "$JOUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('progress',''))")
    echo "Job $JOBID status=$STATUS progress=$PROG"

    if [ "$STATUS" = "completed" ]; then
      echo "Job $JOBID completed"
      break
    fi
    if [ "$STATUS" = "error" ]; then
      echo "Job $JOBID errored — details:"
      printf "%s\n" "$JOUT"
      return 3
    fi

    sleep 2
  done

  BASE=$(printf "%s" "$JOUT" | python3 -c "import sys,json; j=json.load(sys.stdin); print(j.get('basename','test-audio'))")
  HTML_URL="http://127.0.0.1:5001/files/${BASE}.html"
  DOCX_URL="http://127.0.0.1:5001/files/${BASE}.docx"

  echo "Downloading generated HTML: $HTML_URL -> /tmp/${BASE}.html"
  curl -sS "$HTML_URL" -o "/tmp/${BASE}.html" || { echo "Failed to download HTML"; return 4; }

  echo "Downloading generated DOCX: $DOCX_URL -> /tmp/${BASE}.docx"
  if ! curl -sS -f "$DOCX_URL" -o "/tmp/${BASE}.docx"; then
    echo "DOCX not available at $DOCX_URL"; return 5
  fi

  echo "Checking HTML for phrase..."
  if grep -qiF "$PHRASE" "/tmp/${BASE}.html"; then
    echo "HTML contains the phrase"
  else
    echo "HTML does NOT contain the phrase"
  fi

  echo "Checking DOCX for phrase..."
  if command -v pandoc >/dev/null 2>&1; then
    if pandoc "/tmp/${BASE}.docx" --output=- 2>/dev/null | grep -qiF "$PHRASE"; then
      echo "DOCX contains the phrase (via pandoc)"
    else
      echo "DOCX does NOT contain the phrase (via pandoc)"
    fi
  else
    echo "pandoc not found; inspecting DOCX xml contents"
    python3 - <<PY
from zipfile import ZipFile
import re,html,sys
p='/tmp/${BASE}.docx'
try:
  with ZipFile(p) as zf:
    xml=zf.read('word/document.xml').decode('utf-8',errors='ignore')
    text=re.sub(r'<[^>]+>','',xml)
    text=html.unescape(text)
    print('DOCX contains the phrase' if '${PHRASE}'.lower() in text.lower() else 'DOCX does NOT contain the phrase')
except Exception as e:
  print('Failed to inspect DOCX:',e); sys.exit(6)
PY
  fi

  echo "Done. Artifacts saved to /tmp/${BASE}.html and /tmp/${BASE}.docx"
  return 0
}

# Call once with the original phrase
ORIG_PHRASE='This is our deep dive into the documentation'
poll_and_check "$ORIG_PHRASE"

# Now modify the VTT and run again
if [ -d test-audio ]; then
  echo "Patching test-audio/0.vtt: replacing 'critical' -> 'bananas'"
  sed -i "s/critical/bananas/" test-audio/0.vtt || echo "sed failed (file may not exist)"
else
  echo "Warning: test-audio directory not found; skipping sed edit"
fi

poll_and_check "Okay, so today we're diving into something pretty bananas"

