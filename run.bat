@echo off
rem Double-click to open the window, or drop an audio file on this .bat to start with it.
rem Standalone: without disco_sync.py next to it, runs the one from the latest GitHub release.
rem Console mode without the window: uv run disco_sync.py "<link or file>" songs
where uv >nul 2>nul || powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
where uv >nul 2>nul || set "PATH=%USERPROFILE%\.local\bin;%PATH%"
set "SCRIPT=%~dp0disco_sync.py"
if not exist "%SCRIPT%" set "SCRIPT=https://github.com/flipasd-108/dead-as-disco-sync/releases/latest/download/disco_sync.py"
chcp 65001 >nul
echo Dead as Disco Sync: окно сейчас откроется. Первый запуск качает около 1 ГБ, это несколько минут: не закрывай это окно.
echo Dead as Disco Sync: the window opens in a moment. The first run downloads about 1 GB, a few minutes: keep this open.
uv run "%SCRIPT%" --gui "%~dp0songs" "%~1"
if errorlevel 1 pause
