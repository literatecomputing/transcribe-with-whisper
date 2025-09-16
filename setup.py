from setuptools import setup, find_packages

setup(
    name="transcribe-with-whisper",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "pydub",
        "webvtt-py",
        "pyannote.audio",
        "huggingface_hub",
        "torch",            # default CPU version will be installed
        "faster-whisper",   # will use CPU if torch is CPU-only
    ],
    entry_points={
        "console_scripts": [
            "transcribe-with-whisper=transcribe_with_whisper.main:main",
        ],
    },
    python_requires=">=3.8",
    include_package_data=True,
    description="Video transcription with speaker diarization and HTML output",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Jay Pfaffman",
    url="https://github.com/literatecomputing/transcribe-with-whisper",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
)
