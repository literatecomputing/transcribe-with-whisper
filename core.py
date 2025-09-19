import os
from .main import transcribe_logic   # you'll rename your current main logic

def transcribe_file(input_path, output_html, speaker_names=None, model_size="small"):
    """
    Transcribe an audio/video file and write HTML output.
    """
    return transcribe_logic(
        input_path=input_path,
        output_html=output_html,
        speaker_names=speaker_names,
        model_size=model_size,
    )
