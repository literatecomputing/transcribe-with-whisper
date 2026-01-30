FROM ubuntu:22.04

WORKDIR /app

# Install system dependencies including Python
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3.11 \
        python3.11-venv \
        python3-pip \
        ffmpeg \
        pandoc \
        build-essential \
        git \
        cmake \
        ninja-build \
        pkg-config \
        libavcodec-dev \
        libavformat-dev \
        libavutil-dev \
        libavdevice-dev \
        libavfilter-dev \
        libswscale-dev \
        libswresample-dev \
    && rm -rf /var/lib/apt/lists/*

# Create Python virtual environment
RUN python3.11 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements first for better layer caching
COPY requirements-amd64.txt requirements-arm64.txt /app/

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Install architecture-specific requirements
RUN if [ "$(uname -m)" = "aarch64" ]; then \
        echo "=== Building for ARM64 - using pyannote.audio 3.4.0 (stable) ==="; \
        pip install --no-cache-dir -r requirements-arm64.txt; \
    else \
        echo "=== Building for AMD64 - using pyannote.audio 4.0.0 (with torchcodec) ==="; \
        pip install --no-cache-dir -r requirements-amd64.txt; \
    fi

# Copy the rest of the project
COPY . /app

# Install the project itself
RUN pip install --no-cache-dir -e . --no-deps

# Ensure branding assets ship alongside the installed package (handles editable/non-editable installs)
RUN python - <<'PY'
import pathlib
import shutil
import transcribe_with_whisper

package_root = pathlib.Path(transcribe_with_whisper.__file__).resolve().parent.parent
src = pathlib.Path('/app/branding')
dst = package_root / 'branding'

if not src.is_dir():
    print("⚠️ Branding assets not found at /app/branding; skipping copy.")
elif src.resolve() == dst.resolve():
    print("✅ Branding assets already in destination; skipping copy.")
else:
    try:
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
    except FileNotFoundError:
        print("⚠️ Branding assets missing during copy; skipping.")
    except Exception as exc:
        print(f"⚠️ Unable to copy branding assets: {exc}")
PY

# Runtime env and directories
ENV TRANSCRIPTION_DIR=/app/mercuryscribe \
    PYTHONUNBUFFERED=1 \
    WEB_SERVER_MODE=1
RUN mkdir -p ${TRANSCRIPTION_DIR}

# Expose FastAPI port
EXPOSE 5001

# Start the FastAPI web server
CMD ["uvicorn", "transcribe_with_whisper.server_app:app", "--host", "0.0.0.0", "--port", "5001"]
