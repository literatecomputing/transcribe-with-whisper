#!/bin/bash
# Development wrapper for transcribe-with-whisper CLI
# This runs the CLI using your local development code with all changes

cd $(dirname $0)
exec python3 -m transcribe_with_whisper.main "$@"
