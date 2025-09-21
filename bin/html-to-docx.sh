#!/usr/bin/env bash
# Convert an HTML file to DOCX using Pandoc in Docker, stripping links and any <div class="html-only"> blocks.
# Usage: html-to-docx.sh input.html [output.docx]
set -euo pipefail

# Ensure docker is available
if ! command -v docker >/dev/null 2>&1; then
  echo "Error: docker is required but not found in PATH." >&2
  exit 1
fi

if [ $# -lt 1 ] || [ $# -gt 2 ]; then
  echo "Usage: $(basename "$0") input.html [output.docx]" >&2
  exit 1
fi

in_path="$1"
if [ ! -f "$in_path" ]; then
  echo "Error: input file not found: $in_path" >&2
  exit 1
fi

# Compute absolute paths without relying on readlink -f
if [[ "$in_path" = /* ]]; then
  in_abs="$in_path"
else
  in_abs="$PWD/$in_path"
fi
in_dir="$(dirname "$in_abs")"
in_base="$(basename "$in_abs")"

if [ $# -eq 2 ]; then
  out_path="$2"
else
  # Default output next to input with .docx extension
  out_path="${in_dir}/${in_base%.*}.docx"
fi

if [[ "$out_path" = /* ]]; then
  out_abs="$out_path"
else
  out_abs="$PWD/$out_path"
fi
out_dir="$(dirname "$out_abs")"
out_base="$(basename "$out_abs")"

mkdir -p "$out_dir"

# Create a temporary Lua filter accessible to the container
lua_tmp="$(mktemp)"
cat >"$lua_tmp" <<'LUA'
function Link(el)
  -- Drop link wrapper, keep text
  return el.content
end

function Div(el)
  -- Remove any block with class "html-only"
  for _, cls in ipairs(el.classes) do
    if cls == "html-only" then
      return {}
    end
  end
  return nil
end
LUA

# Choose container image (override with PANDOC_IMAGE if desired)
image="${PANDOC_IMAGE:-pandoc/core:latest}"

# Run Pandoc inside Docker. Mount input file, output dir, and lua filter.
docker run --rm \
  -u "$(id -u)":"$(id -g)" \
  -v "$in_abs":/work/input.html:ro \
  -v "$out_dir":/out \
  -v "$lua_tmp":/filter.lua:ro \
  "$image" \
  /work/input.html --lua-filter /filter.lua -o "/out/$out_base"

status=$?
rm -f "$lua_tmp"
exit $status
