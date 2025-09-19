FROM python:3.11-slim

WORKDIR /app

# Install ffmpeg for audio/video processing
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy the project
COPY . /app

# Install Python dependencies (server + package + CLI)
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir fastapi uvicorn[standard] python-multipart \
    && pip install --no-cache-dir transcribe-with-whisper

# Runtime env and directories
ENV UPLOAD_DIR=/app/uploads \
    PYTHONUNBUFFERED=1
RUN mkdir -p ${UPLOAD_DIR}

# Expose FastAPI port
EXPOSE 5000

# Start the FastAPI web server
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "5000"]
