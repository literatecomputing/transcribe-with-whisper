#!/usr/bin/env python3
"""
Web server entry point that enables graceful startup without requiring HuggingFace token.
This sets the WEB_SERVER_MODE environment variable before importing other modules.
"""

import os
import sys

# Enable web server mode before any imports to skip preflight token checks
os.environ["WEB_SERVER_MODE"] = "1"

# Now import and run the server
from transcribe_with_whisper.server_app import main

if __name__ == "__main__":
    main()
