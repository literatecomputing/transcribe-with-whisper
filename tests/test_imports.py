import os
import sys


def test_server_app_imports():
    os.environ['SKIP_HF_STARTUP_CHECK'] = '1'
    sys.path.insert(0, os.getcwd())
    import importlib
    mod = importlib.import_module('transcribe_with_whisper.server_app')
    assert getattr(mod, 'app', None) is not None
