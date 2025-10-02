FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (including build tools for ARM64 torchcodec build)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        pandoc \
        texlive-latex-recommended \
        texlive-fonts-recommended \
        texlive-latex-extra \
        build-essential \
        git \
        cmake \
        pkg-config \
        libavcodec-dev \
        libavformat-dev \
        libavutil-dev \
        libswscale-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better layer caching
COPY requirements.txt /app/requirements.txt

# Install Python dependencies
# For ARM64: Build torchcodec from source since wheels aren't available
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && if [ "$(uname -m)" = "aarch64" ]; then \
        echo "Building for ARM64 - installing PyTorch first, then torchcodec from source..."; \
        pip install --no-cache-dir torch==2.8.0; \
        pip install --no-cache-dir git+https://github.com/pytorch/torchcodec.git; \
    fi \
    && pip install --no-cache-dir -r requirements.txt

# Copy the rest of the project
COPY . /app

# Install the project itself
RUN pip install --no-cache-dir -e . --no-deps

# Runtime env and directories (new default directory name)
ENV TRANSCRIPTION_DIR=/app/transcription-files \
    PYTHONUNBUFFERED=1 \
    WEB_SERVER_MODE=1
RUN mkdir -p ${TRANSCRIPTION_DIR}

# Expose FastAPI port
EXPOSE 5001

# Start the FastAPI web server
CMD ["uvicorn", "transcribe_with_whisper.server_app:app", "--host", "0.0.0.0", "--port", "5001"]
