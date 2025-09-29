#!/usr/bin/env python3
"""
Test script to verify progress monitoring works correctly
"""

import os
import sys
import time
import threading
from pathlib import Path

# Add the project directory to Python path
project_dir = Path(__file__).parent
sys.path.insert(0, str(project_dir))

# Set environment variable to skip HF startup checks
os.environ['SKIP_HF_STARTUP_CHECK'] = '1'

# Import our server module
import transcribe_with_whisper.server_app as server_app

def test_progress_monitoring():
    """Test our progress monitoring on a real transcription"""
    
    # Set up fake job for testing
    server_app.jobs["test"] = {
        "status": "running", 
        "progress": 0,
        "message": "Starting test...",
        "filename": "test-audio.mp3"
    }
    
    print("Testing progress monitoring...")
    print("=" * 50)
    
    # Sample CLI output lines to test our parser
    test_lines = [
        "🔎 Running preflight checks...",
        "✅ ffmpeg found: ffmpeg version 4.4.2-0ubuntu0.22.04.1",
        "✅ All checks passed!",
        "Input #0, mp3, from '../examples/test-audio.mp3':",
        "size=   13676kB time=00:01:19.38 bitrate=1411.2kbits/s speed=1.13e+03x",
        "Detected speakers: ['SPEAKER_00', 'SPEAKER_01']",
        "Processing 0.wav",
        "Processing 1.wav", 
        "Processing 2.wav",
        "Script completed successfully! Output: ../test-audio.html"
    ]
    
    # Test each line
    for i, line in enumerate(test_lines):
        print(f"\nStep {i+1}: {line}")
        
        # Update progress
        server_app._update_progress_from_output("test", line)
        
        # Show current job status
        job = server_app.jobs["test"]
        print(f"  Progress: {job['progress']}%")
        print(f"  Message: {job['message']}")
        
        time.sleep(0.5)  # Brief pause to simulate real timing
    
    print("\n" + "=" * 50)
    print("Progress monitoring test completed!")
    
    final_job = server_app.jobs["test"]
    print(f"Final Progress: {final_job['progress']}%")
    print(f"Final Message: {final_job['message']}")

if __name__ == "__main__":
    test_progress_monitoring()
