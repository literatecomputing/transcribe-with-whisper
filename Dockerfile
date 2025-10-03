FROM continuumio/miniconda3:latest

WORKDIR /app

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        pandoc \
        build-essential \
        git \
    && rm -rf /var/lib/apt/lists/*

# Initialize conda for shell
RUN conda init bash

# Copy requirements first for better layer caching
COPY requirements.txt /app/requirements.txt

# Create conda environment and install dependencies
# For ARM64: Use conda to install PyTorch, then build torchcodec from source
RUN conda create -n transcribe python=3.11 -y \
    && . /opt/conda/etc/profile.d/conda.sh \
    && conda activate transcribe \
    && if [ "$(uname -m)" = "aarch64" ]; then \
        echo "Building for ARM64 - installing PyTorch via conda, cmake, ninja..."; \
        conda install -y pytorch -c pytorch-nightly cmake ninja pybind11; \
        BUILD_AGAINST_ALL_FFMPEG_FROM_S3=1 pip install --no-cache-dir --no-build-isolation git+https://github.com/pytorch/torchcodec.git; \
    else \
        echo "Building for AMD64 - using pip for all packages"; \
        pip install --no-cache-dir --upgrade pip setuptools wheel; \
    fi \
    && pip install --no-cache-dir -r requirements.txt

# Copy the rest of the project
COPY . /app

# Install the project itself in the conda environment
RUN . /opt/conda/etc/profile.d/conda.sh \
    && conda activate transcribe \
    && pip install --no-cache-dir -e . --no-deps

# Runtime env and directories (new default directory name)
ENV TRANSCRIPTION_DIR=/app/transcription-files \
    PYTHONUNBUFFERED=1 \
    WEB_SERVER_MODE=1 \
    PATH=/opt/conda/envs/transcribe/bin:$PATH
RUN mkdir -p ${TRANSCRIPTION_DIR}

# Expose FastAPI port
EXPOSE 5001

# Start the FastAPI web server (using conda environment)
SHELL ["/bin/bash", "-c"]
CMD . /opt/conda/etc/profile.d/conda.sh && conda activate transcribe && uvicorn transcribe_with_whisper.server_app:app --host 0.0.0.0 --port 5001
