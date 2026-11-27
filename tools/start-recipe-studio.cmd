@echo off
setlocal
rem Isolated RD6018 Recipe Studio. Close this window to stop it.
start "" powershell.exe -NoProfile -Command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:8768/studio'"
wsl.exe -d Ubuntu-24.04 --cd /mnt/e/CODEX/rd6018_bot -- /home/home-pc/.venvs/pcp-test/bin/python tools/recipe_studio_local.py --library-root /mnt/e/CODEX/rd6018_bot/.recipe-studio-local --port 8768
echo Recipe Studio stopped or could not start.
pause
