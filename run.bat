@echo off
chcp 65001 >nul
rem Standalone: without disco_sync.py next to it, runs the latest GitHub release (a copy is kept in songs for offline starts).
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
set "OFFLINE="
if exist "%SCRIPT%" goto run
rem the latest release is kept in songs\, so without internet the last downloaded version still starts
set "SCRIPT=%~dp0songs\%NAME%"
if not exist "%~dp0songs" mkdir "%~dp0songs"
curl -fsSL --max-time 60 -o "%SCRIPT%.new" "https://github.com/flipasd-108/dead-as-disco-sync/releases/latest/download/%NAME%"
if errorlevel 1 (
  del "%SCRIPT%.new" 2>nul
  set "OFFLINE=--offline"
) else (
  move /y "%SCRIPT%.new" "%SCRIPT%" >nul
)
rem Cyrillic echo lines stay outside ( ) blocks: with code page 65001 cmd misreads them inside one
if exist "%SCRIPT%" goto saved
echo Dead as Disco Sync: нет интернета, а сохранённой версии ещё нет. Первый запуск нужен с интернетом.
echo Dead as Disco Sync: no internet and no saved copy yet. The first start needs internet.
pause
exit /b 1
:saved
if not defined OFFLINE goto run
echo Dead as Disco Sync: нет связи с GitHub, запускаю сохранённую версию.
echo Dead as Disco Sync: GitHub is unreachable, starting the saved version.
:run
echo Dead as Disco Sync: окно сейчас откроется. Первый запуск качает около 1 ГБ, это несколько минут: не закрывай это окно.
echo Dead as Disco Sync: the window opens in a moment. The first run downloads about 1 GB, a few minutes: keep this open.
uv run %OFFLINE% "%SCRIPT%" --gui "%~dp0songs" "%~1"
if errorlevel 1 pause
