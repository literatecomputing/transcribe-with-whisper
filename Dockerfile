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
COPY requirements.txt /app/requirements.txt

# Install Python dependencies
# For ARM64: Install PyTorch first, then attempt torchcodec from source
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# ARM64-specific: Build torchcodec from source
RUN if [ "$(uname -m)" = "aarch64" ]; then \
        echo "Building for ARM64 - installing PyTorch from PyPI (has aarch64 wheels)..."; \
        pip install --no-cache-dir torch==2.8.0 torchvision torchaudio; \
        echo "Building torchcodec from source..."; \
        pip install --no-cache-dir pybind11 numpy; \
        BUILD_AGAINST_ALL_FFMPEG_FROM_S3=1 pip install --no-cache-dir --no-build-isolation git+https://github.com/pytorch/torchcodec.git; \
    fi

# Install main requirements
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the project
COPY . /app

# Install the project itself
RUN pip install --no-cache-dir -e . --no-deps

# Runtime env and directories
ENV TRANSCRIPTION_DIR=/app/transcription-files \
    PYTHONUNBUFFERED=1 \
    WEB_SERVER_MODE=1
RUN mkdir -p ${TRANSCRIPTION_DIR}

# Expose FastAPI port
EXPOSE 5001

# Start the FastAPI web server
CMD ["uvicorn", "transcribe_with_whisper.server_app:app", "--host", "0.0.0.0", "--port", "5001"]
