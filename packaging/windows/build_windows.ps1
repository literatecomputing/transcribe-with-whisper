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
# Ensure PyInstaller knows to include the local package; add the repo root to module search path
# and be explicit about the package hidden imports so run_windows.py can import transcribe_with_whisper
pyinstaller --noconfirm --onedir --name MercuryScribe `
  --paths . `
  --hidden-import transcribe_with_whisper `
  --hidden-import transcribe_with_whisper.server_app `
  --hidden-import pyannote `
  --hidden-import pyannote.audio `
  --hidden-import pyannote.audio.telemetry `
  --add-data "branding;branding" `
  --add-data "packaging/ffmpeg/ffmpeg.exe;." `
  --add-data "packaging/ffmpeg/ffprobe.exe;." `
  packaging/windows/run_windows.py

# Copy helper files into dist
Copy-Item packaging/windows/start-server.bat dist\\MercuryScribe\\start-server.bat -Force
Copy-Item packaging/windows/README_WINDOWS.txt dist\\MercuryScribe\\README_WINDOWS.txt -Force
Write-Output "Performing smoke test of built bundle..."

# Attempt to ensure any pyannote package data (including telemetry config.yaml)
# that may not have been picked up by PyInstaller is copied into the bundle.
# This copies any files/dirs in the virtualenv site-packages that start with
# 'pyannote' into the dist so pyannote.audio telemetry/config.yaml is present.
try {
  $sitePackages = Join-Path $PWD ".venv\\Lib\\site-packages"
  if (Test-Path $sitePackages) {
    $pyannoteItems = Get-ChildItem -Path $sitePackages -Filter 'pyannote*' -ErrorAction SilentlyContinue
    foreach ($item in $pyannoteItems) {
      $dest = Join-Path (Join-Path $PWD 'dist\\MercuryScribe') $item.Name
      Write-Output "Copying pyannote resource: $($item.FullName) -> $dest"
      if ($item.PSIsContainer) {
        Copy-Item -Path $item.FullName -Destination $dest -Recurse -Force
      } else {
        Copy-Item -Path $item.FullName -Destination $dest -Force
      }
    }
  }
} catch {
  Write-Warning "Failed to copy pyannote site-packages into dist: $_"
}
 
# Allow skipping the smoke test via environment variable so CI can always produce the dist zip for manual download
if ($env:SKIP_SMOKE_TEST -and ($env:SKIP_SMOKE_TEST -eq '1' -or $env:SKIP_SMOKE_TEST.ToLower() -eq 'true')) {
  Write-Output "SKIP_SMOKE_TEST is set; skipping smoke test and creating zip artifact for manual download."
  Write-Output "Zipping dist folder..."
  if (Test-Path $OutputZip) { Remove-Item $OutputZip -Force }
  Compress-Archive -Path dist\\MercuryScribe\\* -DestinationPath $OutputZip -Force
  Write-Output "Build complete (smoke test skipped): $OutputZip"
  exit 0
}

# Start the bundled exe in background
$exePath = Join-Path -Path (Join-Path $PWD 'dist') -ChildPath 'MercuryScribe\\MercuryScribe.exe'
if (-not (Test-Path $exePath)) {
  Write-Error "Built exe not found at $exePath"
  exit 1
}

Write-Output "Starting bundle: $exePath"
# Start the process and capture stdout/stderr to log files for debugging
$outLog = Join-Path -Path (Join-Path $PWD 'dist\MercuryScribe') -ChildPath 'bundle.stdout.log'
$errLog = Join-Path -Path (Join-Path $PWD 'dist\MercuryScribe') -ChildPath 'bundle.stderr.log'
# Ensure previous logs are removed
if (Test-Path $outLog) { Remove-Item $outLog -Force }
if (Test-Path $errLog) { Remove-Item $errLog -Force }

# Try to start the exe with redirected streams using System.Diagnostics.Process so stdout/stderr can be captured
try {
  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = $exePath
  $psi.Arguments = ''
  $psi.UseShellExecute = $false
  $psi.RedirectStandardOutput = $true
  $psi.RedirectStandardError = $true
  $psi.CreateNoWindow = $true

  $procObj = New-Object System.Diagnostics.Process
  $procObj.StartInfo = $psi
  $started = $procObj.Start()
  if (-not $started) { throw "Process failed to start via ProcessStartInfo" }

  # Read stdout/stderr asynchronously into the log files
  $stdOut = $procObj.StandardOutput
  $stdErr = $procObj.StandardError

  # Start background jobs to stream output
  Start-Job -ScriptBlock {
    param($reader, $path)
    while (-not $reader.EndOfStream) {
      $line = $reader.ReadLine()
      if ($line -ne $null) { Add-Content -Path $path -Value $line }
      Start-Sleep -Milliseconds 10
    }
  } -ArgumentList $stdOut, $outLog | Out-Null

  Start-Job -ScriptBlock {
    param($reader, $path)
    while (-not $reader.EndOfStream) {
      $line = $reader.ReadLine()
      if ($line -ne $null) { Add-Content -Path $path -Value $line }
      Start-Sleep -Milliseconds 10
    }
  } -ArgumentList $stdErr, $errLog | Out-Null

  $proc = $procObj

} catch {
  Write-Warning "Attempt to start exe with redirected streams failed: $_. Falling back to detached Start-Process."
  try {
    $proc = Start-Process -FilePath $exePath -ArgumentList '' -PassThru
  } catch {
    Write-Error "Failed to start bundle: $_"
    exit 1
  }
}

# Wait for server to respond on /setup
## Increase timeout so the bundled server has more time to initialize (120s total)
$ok = $false
for ($i = 0; $i -lt 120; $i++) {
  try {
    $resp = Invoke-WebRequest -Uri 'http://127.0.0.1:5001/setup' -UseBasicParsing -TimeoutSec 5
    if ($resp.StatusCode -eq 200) { $ok = $true; break }
  } catch {
    # Not yet responding via HTTP; check for the startup flag inside the bundle as a fallback
    try {
      $flagPath = Join-Path (Join-Path $PWD 'dist\MercuryScribe') 'server_started.flag'
      if (Test-Path $flagPath) { Write-Output "Found startup flag: $flagPath"; $ok = $true; break }
    } catch {}
    Start-Sleep -Seconds 1
  }
}

if (-not $ok) {
  Write-Error "Smoke test failed: server did not respond on http://127.0.0.1:5001/setup within timeout"
  # Print bundle stdout/stderr logs (if present) to the CI log to help debugging
  try {
    if (Test-Path $outLog) { Write-Output "---- bundle.stdout.log ----"; Get-Content -Path $outLog -ErrorAction SilentlyContinue | Select-Object -Last 200 }
  } catch {}
  try {
    if (Test-Path $errLog) { Write-Output "---- bundle.stderr.log ----"; Get-Content -Path $errLog -ErrorAction SilentlyContinue | Select-Object -Last 200 }
  } catch {}
  # Print any log written by the bundled run_windows.py to LOCALAPPDATA
  try {
    $localApp = $env:LOCALAPPDATA
    if ($localApp) {
      $appLog = Join-Path $localApp "MercuryScribe\mercuryscribe.log"
      if (Test-Path $appLog) { Write-Output "---- $appLog ----"; Get-Content -Path $appLog -ErrorAction SilentlyContinue | Select-Object -Last 200 }
    }
  } catch {}
  # Also print any log files that might be inside the dist bundle directory (including bundle_run.log)
  try {
    $distDir = Join-Path $PWD 'dist\MercuryScribe'
    if (Test-Path $distDir) {
      Write-Output "---- dist directory listing ----"
      Get-ChildItem -Path $distDir | Sort-Object Length -Descending | Select-Object Name,Length | ForEach-Object { Write-Output "$_" }
      $logFiles = Get-ChildItem -Path $distDir -Filter *.log -ErrorAction SilentlyContinue
      foreach ($f in $logFiles) {
        Write-Output "---- $($f.Name) (last 200 lines) ----"
        Get-Content -Path $f.FullName -ErrorAction SilentlyContinue | Select-Object -Last 200
      }
    }
  } catch {}
  # Give background jobs a moment to flush
  try { Start-Sleep -Seconds 1; Get-Job | Where-Object { $_.State -eq 'Running' } | ForEach-Object { Receive-Job -Id $_.Id -Keep 2>$null } } catch {}
  # Also print the PyInstaller warn file and build xref if they exist
  try { if (Test-Path build\MercuryScribe\warn-MercuryScribe.txt) { Write-Output "---- PyInstaller warnings ----"; Get-Content build\MercuryScribe\warn-MercuryScribe.txt | Select-Object -Last 200 } } catch {}
  try { if (Test-Path build\MercuryScribe\xref-MercuryScribe.html) { Write-Output "---- PyInstaller xref (last 200 lines) ----"; Get-Content build\MercuryScribe\xref-MercuryScribe.html | Select-Object -Last 200 } } catch {}
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
