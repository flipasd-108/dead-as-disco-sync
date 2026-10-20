@echo off
rem Drop an audio file on this .bat, or double-click and paste a YouTube link.
where uv >nul 2>nul || powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
where uv >nul 2>nul || set "PATH=%USERPROFILE%\.local\bin;%PATH%"
set "SRC=%~1"
if "%SRC%"=="" set /p "SRC=YouTube link or audio file path: "
set "SRC=%SRC:"=%"
uv run "%~dp0disco_sync.py" "%SRC%" "%~dp0songs"
pause
