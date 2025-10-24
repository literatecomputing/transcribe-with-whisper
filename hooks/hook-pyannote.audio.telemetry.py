from PyInstaller.utils.hooks import collect_data_files, collect_submodules

hiddenimports = collect_submodules('pyannote.audio.telemetry')
datas = collect_data_files('pyannote.audio.telemetry')
