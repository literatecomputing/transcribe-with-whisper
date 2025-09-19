# transcribe_with_whisper/core.py
import os
import torch
import torchaudio
from faster_whisper import WhisperModel
from pyannote.audio import Pipeline
from jinja2 import Template


def transcribe_file(input_path, output_html, speaker_names=None, model_size="small"):
    """
    Transcribe an audio/video file with faster-whisper and diarization, output HTML.
    """

    # Pick device
    device = "cuda" if torch.cuda.is_available() else "cpu"

    # Load Whisper model
    model = WhisperModel(model_size, device=device)

    # Get audio metadata
    info = torchaudio.info(input_path, backend="soundfile")

    # Run transcription
    segments, transcription_info = model.transcribe(input_path)

    # Run speaker diarization
    diarization_pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization")
    diarization = diarization_pipeline(input_path)

    # Build speaker mapping
    if speaker_names:
        speaker_map = {i: name for i, name in enumerate(speaker_names)}
    else:
        speaker_map = {}

    # Merge transcription + diarization
    results = []
    for seg in segments:
        speaker = None
        for turn, _, spk in diarization.itertracks(yield_label=True):
            if seg.start >= turn.start and seg.end <= turn.end:
                speaker = spk
                break
        results.append({
            "start": seg.start,
            "end": seg.end,
            "text": seg.text,
            "speaker": speaker
        })

    # HTML template (from your repo)
    template = Template(
        """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Transcription</title>
            <style>
                body { font-family: sans-serif; max-width: 800px; margin: auto; line-height: 1.6; }
                .segment { margin-bottom: 1em; }
                .speaker { font-weight: bold; margin-right: 0.5em; }
                .timestamp { color: gray; font-size: 0.9em; margin-right: 0.5em; }
            </style>
        </head>
        <body>
            <h1>Transcription</h1>
            {% for seg in results %}
                <div class="segment">
                    <span class="timestamp">[{{ "%.2f"|format(seg.start) }} - {{ "%.2f"|format(seg.end) }}]</span>
                    {% if seg.speaker %}
                        <span class="speaker">{{ speaker_map.get(seg.speaker, seg.speaker) }}:</span>
                    {% endif %}
                    <span class="text">{{ seg.text }}</span>
                </div>
            {% endfor %}
        </body>
        </html>
        """
    )

    html = template.render(results=results, speaker_map=speaker_map)

    # Write HTML to file
    with open(output_html, "w", encoding="utf-8") as f:
        f.write(html)

    return output_html
