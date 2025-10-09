import pytest
from huggingface_hub.utils import GatedRepoError

from transcribe_with_whisper import server_app


@pytest.fixture
def monkeypatched_hf(monkeypatch):
    """Helper to swap out HfApi with a controllable fake."""
    created = {}

    def factory():
        if "instance" not in created:
            raise RuntimeError("Test did not configure fake HfApi instance")
        return created["instance"]

    monkeypatch.setattr(server_app, "HfApi", factory)

    def configure(instance):
        created["instance"] = instance

    return configure


@pytest.fixture
def required_models(monkeypatch):
    models = [
        {
            "name": "pyannote/speaker-diarization-community-1",
            "url": "https://huggingface.co/pyannote/speaker-diarization-community-1",
            "description": "Speaker diarization checkpoints for pyannote.audio",
            "probe_filename": "config.yaml",
        },
        {
            "name": "pyannote/segmentation-3.0",
            "url": "https://huggingface.co/pyannote/segmentation-3.0",
            "description": "Voice activity segmentation backbone",
            "probe_filename": "config.yaml",
        },
    ]

    monkeypatch.setattr(server_app, "_get_required_hf_models", lambda: models)
    return models


def test_validate_token_success(monkeypatched_hf, required_models, monkeypatch):
    calls = []

    def fake_download(repo_id, filename, token=None, force_download=False, local_files_only=False, cache_dir=None):
        calls.append((repo_id, filename, token))
        return f"/tmp/{repo_id.replace('/', '_')}/{filename}"

    monkeypatch.setattr(server_app, "hf_hub_download", fake_download)

    class FakeHfApi:
        def whoami(self, token):
            assert token == "hf_valid_token"

        def model_info(self, model, token):
            # Should be called for every required model
            assert token == "hf_valid_token"

    monkeypatched_hf(FakeHfApi())

    result = server_app._validate_hf_token("hf_valid_token")
    assert result["valid"] is True
    assert result["missing_models"] == []
    assert "message" in result and "required models accessible" in result["message"].lower()
    assert len(calls) == len(required_models)


def test_validate_token_reports_missing_models(monkeypatched_hf, required_models, monkeypatch):
    missing = required_models[0]

    class FakeHfApi:
        def whoami(self, token):
            return {"name": "tester"}

        def model_info(self, model, token):
            if model == missing["name"]:
                raise Exception("403 Forbidden: access denied")

    monkeypatched_hf(FakeHfApi())

    def fake_download(repo_id, filename, token=None, force_download=False, local_files_only=False, cache_dir=None):
        raise GatedRepoError("access denied")

    monkeypatch.setattr(server_app, "hf_hub_download", fake_download)

    result = server_app._validate_hf_token("hf_without_access")
    assert result["valid"] is False
    assert result["requires_license_acceptance"] is True
    entry = next((m for m in result["missing_models"] if m["name"] == missing["name"]), None)
    assert entry is not None
    assert entry["reason"].startswith("access denied")
    assert missing["name"] in result["error"]


def test_validate_token_handles_repository_not_found(monkeypatched_hf, required_models, monkeypatch):
    calls = []

    def fake_download(repo_id, filename, token=None, force_download=False, local_files_only=False, cache_dir=None):
        calls.append((repo_id, filename, token))
        return f"/tmp/{repo_id.replace('/', '_')}/{filename}"

    monkeypatch.setattr(server_app, "hf_hub_download", fake_download)
    missing = required_models[1]

    class FakeHfApi:
        def whoami(self, token):
            return {"name": "tester"}

        def model_info(self, model, token):
            if model == missing["name"]:
                raise Exception("Repository Not Found")

    monkeypatched_hf(FakeHfApi())

    result = server_app._validate_hf_token("hf_missing_repo")
    assert result["valid"] is False
    assert result["requires_license_acceptance"] is False
    assert result["missing_models"] == [
        {
            "name": missing["name"],
            "url": missing["url"],
            "reason": "repository not found",
        }
    ]
    assert "repository not found" in result["error"].lower()
    # Our fake download should still run for the first model
    assert len(calls) == 1


def test_validate_token_with_invalid_prefix(monkeypatched_hf):
    result = server_app._validate_hf_token("invalid-token")
    assert result["valid"] is False
    assert "invalid token format" in result["error"].lower()


def test_required_models_switch_with_pyannote_major(monkeypatch):
    monkeypatch.setattr(server_app, "_REQUIRED_MODELS_CACHE", None)
    monkeypatch.setattr(server_app, "_determine_pyannote_major", lambda: 3)

    models = server_app._get_required_hf_models()
    assert models[0]["name"] == "pyannote/speaker-diarization-community-1"
    assert any(model["name"] == "pyannote/speaker-diarization-3.1" for model in models)
    assert any(model["name"] == "pyannote/segmentation-3.0" for model in models)
