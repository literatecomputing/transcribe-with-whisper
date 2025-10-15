@echo off
REM Start MercuryScribe (Windows one-folder bundle)
SETLOCAL
SET EXE_DIR=%~dp0
SET BUNDLE_EXE=%EXE_DIR%MercuryScribe.exe
IF NOT EXIST "%BUNDLE_EXE%" (
  echo Could not find %BUNDLE_EXE%
  pause
  exit /b 1
)
"%BUNDLE_EXE%"
ENDLOCAL
