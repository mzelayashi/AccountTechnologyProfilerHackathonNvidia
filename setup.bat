@echo off
setlocal
cd /d "%~dp0"
echo ==================================================
echo    A.T.L.A.S. v1.0  -  Setup / Dependency Install
echo ==================================================
echo.
set "PYEXE="
where py >nul 2>nul && set "PYEXE=py"
if not defined PYEXE ( where python >nul 2>nul && set "PYEXE=python" )
if not defined PYEXE (
  echo [ERROR] Python 3.10+ was not found on this PC.
  echo         Install it from https://www.python.org/downloads/
  echo         ^(tick "Add Python to PATH" during install^), then run setup.bat again.
  echo.
  pause
  exit /b 1
)
echo Using Python launcher: %PYEXE%
echo.
echo [1/3] Creating virtual environment (.venv) ...
%PYEXE% -m venv ".venv"
if errorlevel 1 ( echo [ERROR] Could not create the virtual environment. & pause & exit /b 1 )
echo [2/3] Upgrading pip ...
".venv\Scripts\python.exe" -m pip install --upgrade pip
echo [3/3] Installing dependencies (this can take a few minutes) ...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 ( echo [ERROR] Dependency install failed. Check your internet connection and retry. & pause & exit /b 1 )
echo.
echo ==================================================
echo   Setup complete.  Double-click START.bat to run.
echo ==================================================
pause
