@echo off
rem Drop an audio file on this .bat, or double-click and paste a YouTube link / file path.
rem Standalone: without disco_sync.py next to it, runs the one from the latest GitHub release.
where uv >nul 2>nul || powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
where uv >nul 2>nul || set "PATH=%USERPROFILE%\.local\bin;%PATH%"
set "SCRIPT=%~dp0disco_sync.py"
if not exist "%SCRIPT%" set "SCRIPT=https://github.com/flipasd-108/dead-as-disco-sync/releases/latest/download/disco_sync.py"
set "SRC=%~1"
if "%SRC%"=="" set /p "SRC=YouTube link or audio file path: "
set "SRC=%SRC:"=%"
uv run "%SCRIPT%" "%SRC%" "%~dp0songs"
pause
