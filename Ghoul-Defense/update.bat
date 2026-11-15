@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if not exist "updater.py" (
    echo updater.py is missing. Extract the complete distribution package first.
    pause
    exit /b 1
)
if not exist ".venv\Scripts\pythonw.exe" (
    echo Preparing Python for the updater...
    call "%~dp0install.bat"
    if errorlevel 1 exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" "%~dp0updater.py" %*
exit /b 0
