from PyInstaller.utils.hooks import collect_data_files, collect_submodules

hiddenimports = collect_submodules('torch._dynamo.polyfills')
datas = collect_data_files('torch._dynamo.polyfills')
