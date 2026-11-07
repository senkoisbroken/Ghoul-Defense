@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Ghoul Defense Setup

set "GHOUL_ERROR=Unknown setup error."
set "GHOUL_PYINSTALLER=%TEMP%\ghoul-defense-python-3.13.17-amd64.exe"
set "PYTHON_LOCAL=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
set "PYTHON_CMD="

echo Ghoul Defense setup
echo.

if not exist "requirements.txt" (
    set "GHOUL_ERROR=requirements.txt was not found next to this launcher. Extract the whole folder and try again."
    goto :fail
)

if exist ".venv" goto :check_env
goto :find_python

:check_env
if not exist ".venv\Scripts\python.exe" (
    set "GHOUL_ERROR=The .venv folder is incomplete. Rename or delete it, then run this file again."
    goto :fail
)
".venv\Scripts\python.exe" -c "import sys, struct; sys.exit(0 if sys.version_info[:2] == (3, 13) and struct.calcsize('P') == 8 else 1)" >nul 2>&1
if errorlevel 1 (
    set "GHOUL_ERROR=The existing .venv is not 64-bit Python 3.13. Rename or delete the .venv folder, then run this file again."
    goto :fail
)
goto :dependencies

:find_python
echo Checking for 64-bit Python 3.13...
py -3.13 -c "import sys, struct; sys.exit(0 if sys.version_info[:2] == (3, 13) and struct.calcsize('P') == 8 else 1)" >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=py"
if defined PYTHON_CMD goto :create_env
if not exist "%PYTHON_LOCAL%" goto :download_python
"%PYTHON_LOCAL%" -c "import sys, struct; sys.exit(0 if sys.version_info[:2] == (3, 13) and struct.calcsize('P') == 8 else 1)" >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=local"
if defined PYTHON_CMD goto :create_env

:download_python
echo Python 3.13 was not found. Downloading Python 3.13.17 from python.org...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference = 'Stop'; try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -UseBasicParsing -Uri 'https://www.python.org/ftp/python/3.13.17/python-3.13.17-amd64.exe' -OutFile $env:GHOUL_PYINSTALLER } catch { Write-Host $_.Exception.Message; exit 1 }"
if errorlevel 1 (
    set "GHOUL_ERROR=Could not download Python 3.13.17. Check the internet connection and try again."
    goto :fail
)
if not exist "%GHOUL_PYINSTALLER%" (
    set "GHOUL_ERROR=The Python download did not create the expected file."
    goto :fail
)

echo Validating the downloaded installer signature...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$sig = Get-AuthenticodeSignature -LiteralPath $env:GHOUL_PYINSTALLER -ErrorAction Stop; if ($null -eq $sig -or $sig.Status -ne 'Valid' -or $null -eq $sig.SignerCertificate -or $sig.SignerCertificate.Subject -notmatch 'O=Python Software Foundation(,|$)') { Write-Host 'Installer signature validation failed.' -ForegroundColor Red; Write-Host ('Status: ' + $sig.Status); if ($null -ne $sig.SignerCertificate) { Write-Host ('Publisher: ' + $sig.SignerCertificate.Subject) }; exit 1 }; Write-Host ('Verified publisher: ' + $sig.SignerCertificate.Subject)"
if errorlevel 1 (
    set "GHOUL_ERROR=The Python installer did not pass Authenticode and publisher checks, so it was not run."
    goto :fail
)

echo Installing Python 3.13.17 for the current Windows user. No administrator install is needed.
"%GHOUL_PYINSTALLER%" /quiet InstallAllUsers=0 Include_launcher=0 PrependPath=0 Include_test=0 Include_pip=1 Include_tcltk=1
if errorlevel 1 (
    set "GHOUL_ERROR=The Python installer returned an error. Setup did not continue."
    goto :fail
)
del "%GHOUL_PYINSTALLER%" >nul 2>&1
if not exist "%PYTHON_LOCAL%" (
    set "GHOUL_ERROR=Python 3.13.17 was not found in the standard per-user install folder after setup."
    goto :fail
)
"%PYTHON_LOCAL%" -c "import sys, struct; sys.exit(0 if sys.version_info[:2] == (3, 13) and struct.calcsize('P') == 8 else 1)" >nul 2>&1
if errorlevel 1 (
    set "GHOUL_ERROR=The installed Python is not 64-bit Python 3.13."
    goto :fail
)
set "PYTHON_CMD=local"

:create_env
if not defined PYTHON_CMD (
    set "GHOUL_ERROR=No usable 64-bit Python 3.13 was found."
    goto :fail
)
echo Creating the local .venv...
if "%PYTHON_CMD%"=="local" (
    "%PYTHON_LOCAL%" -m venv .venv
) else (
    py -3.13 -m venv .venv
)
if errorlevel 1 (
    set "GHOUL_ERROR=Could not create the local .venv."
    goto :fail
)
if not exist ".venv\Scripts\python.exe" (
    set "GHOUL_ERROR=The local .venv was created without python.exe."
    goto :fail
)
".venv\Scripts\python.exe" -c "import sys, struct; sys.exit(0 if sys.version_info[:2] == (3, 13) and struct.calcsize('P') == 8 else 1)" >nul 2>&1
if errorlevel 1 (
    set "GHOUL_ERROR=The local .venv is not running 64-bit Python 3.13."
    goto :fail
)

:dependencies
if "%GHOUL_FORCE_SETUP%"=="1" goto :install_dependencies
".venv\Scripts\python.exe" -c "from pathlib import Path; import hashlib, sys; p=Path('.venv/ghoul-requirements.sha256'); digest=hashlib.sha256(Path('requirements.txt').read_bytes()).hexdigest(); sys.exit(0 if p.is_file() and p.read_text().strip()==digest else 1)" >nul 2>&1
if not errorlevel 1 goto :verify_imports

:install_dependencies
echo Installing required packages. Internet is required on the first setup...
".venv\Scripts\python.exe" -m pip --disable-pip-version-check install -r "requirements.txt"
if errorlevel 1 (
    set "GHOUL_ERROR=Package installation failed. Review the output above."
    goto :fail
)
echo Checking installed packages...
".venv\Scripts\python.exe" -m pip check
if errorlevel 1 (
    set "GHOUL_ERROR=pip check found a package problem. Review the output above."
    goto :fail
)
:verify_imports
echo Verifying imports...
".venv\Scripts\python.exe" -c "import tkinter, numpy, cv2, mss, onnxruntime, rapidocr_onnxruntime; import app; print('Imports OK.')"
if errorlevel 1 (
    set "GHOUL_ERROR=Import verification failed. Run install.bat to repair packages. Review the error above."
    goto :fail
)
if not exist ".venv\Scripts\pythonw.exe" (
    set "GHOUL_ERROR=.venv\Scripts\pythonw.exe is missing. Delete .venv and run setup again."
    goto :fail
)
".venv\Scripts\python.exe" -c "from pathlib import Path; import hashlib; Path('.venv/ghoul-requirements.sha256').write_text(hashlib.sha256(Path('requirements.txt').read_bytes()).hexdigest())"
if errorlevel 1 (
    set "GHOUL_ERROR=Could not save setup status. Check folder write access."
    goto :fail
)

if "%GHOUL_SETUP_ONLY%"=="1" (
    echo.
    echo Setup complete. GHOUL_SETUP_ONLY=1 is set, so the app was not launched.
    exit /b 0
)

if not exist "app.py" (
    set "GHOUL_ERROR=app.py was not found next to this launcher."
    goto :fail
)
echo Starting Ghoul Defense. Focus Roblox and press F8 to start or pause.
start "" ".venv\Scripts\pythonw.exe" "%~dp0app.py"
exit /b 0

:fail
echo.
echo Setup failed.
echo %GHOUL_ERROR%
echo.
echo Keep this window open and share the text above.
echo Check that the folder was fully extracted and that the internet connection works.
pause
exit /b 1
