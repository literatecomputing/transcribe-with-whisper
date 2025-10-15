# Build helper for Windows (run on windows-latest or a Windows dev machine)
# - Creates a venv, installs deps, runs PyInstaller (onedir), and prepares a zip
# Usage: .\build_windows.ps1

param(
    [string]$PythonVersion = "3.11",
    [string]$OutputZip = "MercuryScribe-windows-x86_64.zip"
)

Write-Output "Setting up virtualenv..."
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
pip install pyinstaller

# Ensure packaging/ffmpeg contains ffmpeg.exe and ffprobe.exe (place them there manually or download prior to running)
if (-not (Test-Path packaging\\ffmpeg\\ffmpeg.exe)) {
    Write-Error "packaging\\ffmpeg\\ffmpeg.exe not found. Please place ffmpeg.exe and ffprobe.exe in packaging\\ffmpeg"
    exit 1
}

Write-Output "Running PyInstaller..."
# Add hidden-imports here if PyInstaller logs complain
pyinstaller --noconfirm --onedir --name MercuryScribe `
  --add-data "branding;branding" `
  --add-data "packaging/ffmpeg/ffmpeg.exe;." `
  --add-data "packaging/ffmpeg/ffprobe.exe;." `
  packaging/windows/run_windows.py

# Copy helper files into dist
Copy-Item packaging/windows/start-server.bat dist\\MercuryScribe\\start-server.bat -Force
Copy-Item packaging/windows/README_WINDOWS.txt dist\\MercuryScribe\\README_WINDOWS.txt -Force
Write-Output "Performing smoke test of built bundle..."

# Start the bundled exe in background
$exePath = Join-Path -Path (Join-Path $PWD 'dist') -ChildPath 'MercuryScribe\\MercuryScribe.exe'
if (-not (Test-Path $exePath)) {
  Write-Error "Built exe not found at $exePath"
  exit 1
}

Write-Output "Starting bundle: $exePath"
$proc = Start-Process -FilePath $exePath -ArgumentList '' -PassThru

# Wait for server to respond on /setup
$ok = $false
for ($i = 0; $i -lt 30; $i++) {
  try {
    $resp = Invoke-WebRequest -Uri 'http://127.0.0.1:5001/setup' -UseBasicParsing -TimeoutSec 5
    if ($resp.StatusCode -eq 200) { $ok = $true; break }
  } catch {
    Start-Sleep -Seconds 1
  }
}

if (-not $ok) {
  Write-Error "Smoke test failed: server did not respond on http://127.0.0.1:5001/setup within timeout"
  try { if ($proc -and -not $proc.HasExited) { $proc | Stop-Process -Force } } catch {}
  exit 1
}

Write-Output "Server responded; verifying bundled ffmpeg..."

# Run bundled ffmpeg -version
$ffmpegPath = Join-Path -Path (Join-Path $PWD 'dist\\MercuryScribe') -ChildPath 'ffmpeg.exe'
if (-not (Test-Path $ffmpegPath)) {
  Write-Error "ffmpeg.exe not found in bundle at $ffmpegPath"
  try { if ($proc -and -not $proc.HasExited) { $proc | Stop-Process -Force } } catch {}
  exit 1
}

Write-Output "Running: $ffmpegPath -version"
& $ffmpegPath -version
if ($LASTEXITCODE -ne 0) {
  Write-Error "ffmpeg returned non-zero exit code: $LASTEXITCODE"
  try { if ($proc -and -not $proc.HasExited) { $proc | Stop-Process -Force } } catch {}
  exit 1
}

Write-Output "ffmpeg check passed. Stopping server..."
try { if ($proc -and -not $proc.HasExited) { $proc | Stop-Process -Force } } catch {}

Write-Output "Zipping dist folder..."
if (Test-Path $OutputZip) { Remove-Item $OutputZip -Force }
Compress-Archive -Path dist\\MercuryScribe\\* -DestinationPath $OutputZip -Force

Write-Output "Build complete: $OutputZip"
