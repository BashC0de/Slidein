$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = Join-Path $scriptDir '.venv\Scripts\python.exe'
$python = if (Test-Path $venvPython) { $venvPython } else { 'python' }

try {
	$listening = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
	if ($listening) {
		exit 0
	}
} catch {
}

Start-Process -FilePath $python -ArgumentList @('server.py') -WorkingDirectory $scriptDir -WindowStyle Hidden
