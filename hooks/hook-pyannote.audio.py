from PyInstaller.utils.hooks import collect_submodules, collect_data_files

hiddenimports = collect_submodules('pyannote.audio')
datas = collect_data_files('pyannote.audio')
