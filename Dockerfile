FROM python:3.11-slim

WORKDIR /app

# Install ffmpeg and pandoc for audio/video processing and DOCX generation
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        pandoc \
        texlive-latex-recommended \
        texlive-fonts-recommended \
        texlive-latex-extra \
    && rm -rf /var/lib/apt/lists/*

# Copy the project
COPY . /app

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -e .

# Runtime env and directories (new default directory name)
ENV TRANSCRIPTION_DIR=/app/transcription-files \
    PYTHONUNBUFFERED=1
RUN mkdir -p ${TRANSCRIPTION_DIR}

# Expose FastAPI port
EXPOSE 5001

# Start the FastAPI web server
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "5001"]
