# transcribe_with_whisper/main.py
import argparse
from .core import transcribe_file


def main():
    parser = argparse.ArgumentParser(
        description="Transcribe audio/video files with Whisper + diarization, output as HTML"
    )
    parser.add_argument("input_path", help="Path to input audio or video file")
    parser.add_argument("output_html", help="Path to output HTML file")
    parser.add_argument(
        "--speaker-names",
        nargs="+",
        help="Optional list of speaker names to label speakers (in order)",
    )
    parser.add_argument(
        "--model-size",
        default="small",
        help="Whisper model size (default: small)",
    )

    args = parser.parse_args()

    transcribe_file(
        input_path=args.input_path,
        output_html=args.output_html,
        speaker_names=args.speaker_names,
        model_size=args.model_size,
    )
