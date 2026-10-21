@echo off
rem Double-click to open the window, or drop an audio file on this .bat to start with it.
rem Standalone: without disco_sync.py next to it, runs the one from the latest GitHub release.
rem Console mode without the window: uv run disco_sync.py "<link or file>" songs
where uv >nul 2>nul || powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
where uv >nul 2>nul || set "PATH=%USERPROFILE%\.local\bin;%PATH%"
rem songs\gpu.txt = on: the window offered the NVIDIA build and the user agreed
set "GPU=off"
if exist "%~dp0songs\gpu.txt" set /p GPU=<"%~dp0songs\gpu.txt"
set "NAME=disco_sync.py"
if "%GPU%"=="on" set "NAME=disco_sync_gpu.py"
set "SCRIPT=%~dp0%NAME%"
if not exist "%SCRIPT%" set "SCRIPT=https://github.com/flipasd-108/dead-as-disco-sync/releases/latest/download/%NAME%"
chcp 65001 >nul
echo Dead as Disco Sync: окно сейчас откроется. Первый запуск качает около 1 ГБ, это несколько минут: не закрывай это окно.
echo Dead as Disco Sync: the window opens in a moment. The first run downloads about 1 GB, a few minutes: keep this open.
uv run "%SCRIPT%" --gui "%~dp0songs" "%~1"
if errorlevel 1 pause
