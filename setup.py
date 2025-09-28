from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="transcribe-with-whisper",
    version="0.3.0",
    packages=find_packages(),
    install_requires=[
        "pydub",
        "webvtt-py",
        "pyannote.audio",
        "huggingface_hub",
        "torch",
        "faster-whisper",
    ],
    extras_require={
        "web": [
            "fastapi",
            "uvicorn[standard]",
            "python-multipart",
        ]
    },
    entry_points={
        "console_scripts": [
            "transcribe-with-whisper=transcribe_with_whisper.main:main",
            "mercuryscribe=transcribe_with_whisper.mercuryscribe:main",
        ],
    },
    python_requires=">=3.8",
    include_package_data=True,
    description="Video transcription with speaker diarization and HTML output",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Jay Pfaffman",
    url="https://github.com/literatecomputing/transcribe-with-whisper",
    project_urls={
        "Homepage": "https://github.com/literatecomputing/transcribe-with-whisper",
        "Repository": "https://github.com/literatecomputing/transcribe-with-whisper",
        "Issues": "https://github.com/literatecomputing/transcribe-with-whisper/issues",
        # When you move the repo to mercuryscribe/mercuryscribe, update these URLs
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
)
