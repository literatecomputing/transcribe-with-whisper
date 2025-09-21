#!/usr/bin/env bash
# Convert an HTML file to DOCX, stripping links and any <div class="html-only"> blocks.
# Prefers local pandoc if available; otherwise uses pandoc in Docker.
# Usage: html-to-docx.sh input.html [output.docx]
set -euo pipefail

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
out_ext="${out_base##*.}"
out_ext="${out_ext,,}"

mkdir -p "$out_dir"

# Create a temporary Lua filter (works for both local and Docker pandoc)
lua_tmp="$(mktemp)"
cleanup() { rm -f "$lua_tmp"; }
trap cleanup EXIT

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

if [ "${PANDOC_USE_DOCKER:-0}" != "1" ] && command -v pandoc >/dev/null 2>&1; then
  # Use local pandoc
  if [ "$out_ext" = "pdf" ]; then
    # Prefer wkhtmltopdf if available to avoid LaTeX dependencies
    if command -v wkhtmltopdf >/dev/null 2>&1; then
      pandoc "$in_abs" --lua-filter "$lua_tmp" --pdf-engine wkhtmltopdf -o "$out_abs"
    else
      # Use TeX engine; ensure a language is set to avoid empty \setmainlanguage{}
      pandoc "$in_abs" --lua-filter "$lua_tmp" \
        --pdf-engine "${PDF_ENGINE:-xelatex}" \
        -V lang="${PANDOC_LANG:-en}" \
        -o "$out_abs"
    fi
  else
    pandoc "$in_abs" --lua-filter "$lua_tmp" -o "$out_abs"
  fi
else
  # Fallback to Dockerized pandoc
  if ! command -v docker >/dev/null 2>&1; then
    echo "Error: neither pandoc nor docker is available." >&2
    exit 1
  fi
  # Choose image: PDF requires LaTeX-enabled image
  if [ "$out_ext" = "pdf" ]; then
    image="${PANDOC_IMAGE:-pandoc/latex:latest}"
  else
    image="${PANDOC_IMAGE:-pandoc/core:latest}"
  fi
  docker run --rm \
    -u "$(id -u)":"$(id -g)" \
    -v "$in_abs":/work/input.html:ro \
    -v "$out_dir":/out \
    -v "$lua_tmp":/filter.lua:ro \
    "$image" \
    /work/input.html --lua-filter /filter.lua ${out_ext:+$([ "$out_ext" = pdf ] && echo --pdf-engine "${PDF_ENGINE:-xelatex}") } -o "/out/$out_base"
fi

echo "Wrote: $out_abs"
