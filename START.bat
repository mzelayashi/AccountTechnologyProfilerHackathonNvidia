@echo off
REM Launch SHI ATLAS (WebView2 / Edge Chromium shell)
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" "%~dp0atlas_web.py"
) else (
    start "" pythonw "%~dp0atlas_web.py"
)
