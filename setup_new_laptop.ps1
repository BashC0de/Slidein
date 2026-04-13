$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

if (-not (Test-Path '.venv')) {
  python -m venv .venv
}

. .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt

& "$scriptDir\install_startup_task.ps1"

Write-Host ''
Write-Host 'Setup complete.'
Write-Host 'Trackpad helper is now running in background and will auto-start on sign in.'
Write-Host 'If invite/discovery still fails, run .\allow_trackpad_firewall.ps1 as Administrator.'