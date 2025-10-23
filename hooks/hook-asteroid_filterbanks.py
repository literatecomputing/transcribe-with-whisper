# PyInstaller hook for asteroid_filterbanks
# Ensures the package's submodules and any non-Python data are collected
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# Attempt to collect all submodules and data files from the installed
# `asteroid_filterbanks` package. On CI the package may not be installed
# (which is why a runtime ModuleNotFoundError was observed). Adding the
# package to the Windows build requirements ensures PyInstaller can collect
# the real package files during the build.
hiddenimports = []
datas = []

try:
    hiddenimports = collect_submodules('asteroid_filterbanks') or []
except Exception:
    hiddenimports = []

try:
    datas = collect_data_files('asteroid_filterbanks') or []
except Exception:
    datas = []

# Conservative fallback: if collect_submodules returned nothing (package not
# installed in the build environment), include the top-level import name so
# PyInstaller will still attempt to resolve it if later available.
if not hiddenimports:
    hiddenimports = ['asteroid_filterbanks']

__all__ = ['hiddenimports', 'datas']
