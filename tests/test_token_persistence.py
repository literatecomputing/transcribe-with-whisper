import os
from pathlib import Path

from transcribe_with_whisper import server_app


def test_save_and_load_hf_token_uses_transcription_dir(monkeypatch, tmp_path):
    """Verify that saving/loading HF token uses the runtime TRANSCRIPTION_DIR/.config/hf_token

    This test ensures no migration is performed and that tokens are persisted where the
    server reads them (the resolved TRANSCRIPTION_DIR).
    """
    # Point TRANSCRIPTION_DIR to a temporary directory for the purpose of the test
    monkeypatch.setattr(server_app, "TRANSCRIPTION_DIR", Path(tmp_path) / "mercuryscribe")
    # Ensure any dependent directories are created by the code under test
    server_app.TRANSCRIPTION_DIR.mkdir(parents=True, exist_ok=True)

    token_value = "hf_test_token_12345"

    # Save the token
    server_app._save_hf_token(token_value)

    # The token file should exist under TRANSCRIPTION_DIR/.config/hf_token
    cfg_dir = server_app.TRANSCRIPTION_DIR / ".config"
    token_file = cfg_dir / "hf_token"
    assert token_file.exists(), f"Expected token file at {token_file}"

    # Read back using the public helper
    loaded = server_app._load_hf_token()
    assert loaded == token_value

    # Also ensure the environment variable was populated
    assert os.getenv("HUGGING_FACE_AUTH_TOKEN") == token_value
