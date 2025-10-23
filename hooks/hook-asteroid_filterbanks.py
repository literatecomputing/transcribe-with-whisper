# PyInstaller hook for asteroid_filterbanks
# Ensures the package's submodules and any non-Python data are collected
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

hiddenimports = []
datas = []

try:
    # collect all submodules under asteroid_filterbanks
    hiddenimports = collect_submodules('asteroid_filterbanks') or []
except Exception:
    hiddenimports = []

try:
    # collect package data files (e.g., compiled kernels or resource files)
    datas = collect_data_files('asteroid_filterbanks') or []
except Exception:
    datas = []

# Expose collected names to PyInstaller
__all__ = ['hiddenimports', 'datas']
