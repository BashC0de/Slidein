@echo off
setlocal
cd /d "%~dp0"

echo Starting Trackpad Pro...

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" server.py
  goto :eof
)

python server.py
