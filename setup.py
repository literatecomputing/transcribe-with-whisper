from setuptools import setup, find_packages

setup(
    name="whisper-transcribe-to-html",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "pyannote.audio",
        "pydub",
        "faster-whisper",
        "webvtt-py",
        "huggingface_hub",
    ],
    entry_points={
        "console_scripts": [
            "whisper-transcribe=whisper_transcribe_to_html.main:main",
        ],
    },
    python_requires=">=3.8",
    include_package_data=True,
    description="Video transcription with speaker diarization and HTML output",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Your Name",
    url="https://github.com/literatecomputing/whisper-transcribe-to-html",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
)

